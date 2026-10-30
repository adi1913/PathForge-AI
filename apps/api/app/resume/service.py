"""
The single entry point for resume analysis: parse -> detect sections ->
extract -> normalize skills -> score evidence -> persist -> structured
response. Each stage is a separate module (parsers/, sections.py,
extraction/, skill_normalizer.py, evidence.py) — this class just wires
them together and owns the DB session.
"""

import hashlib
import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.assessments.rules import net_adjustment
from app.core.config import Settings, get_settings
from app.models.assessment import AssessmentEvidence
from app.models.document import Document, DocumentChunk
from app.models.enums import EvidenceSource, SkillLevel
from app.models.skill import UserSkill
from app.models.user import User
from app.resume.errors import ResumeError, ResumeTooLargeError
from app.resume.evidence import infer_proficiency
from app.resume.extraction.base import RawSkillMention
from app.resume.extraction.factory import get_resume_extractor
from app.resume.parsers.factory import get_resume_parser, resolve_content_type
from app.resume.schemas import (
    CertificationEntry,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ParserMetadata,
    ProjectEntry,
    ResumeAnalysis,
    SkillEvidence,
)
from app.resume.sections import detect_sections
from app.resume.skill_normalizer import SkillNormalizer

logger = logging.getLogger("pathforge.resume")

# Strongest-first, used to pick one representative evidence_type/text
# when multiple pieces of evidence exist for the same skill.
_EVIDENCE_STRENGTH_ORDER = ["demonstrated_usage", "work_experience", "certification", "explicit_mention", "inferred"]


@dataclass
class PersistenceSummary:
    document_id: str
    user_skills_created: int
    user_skills_updated: int


def _pick_representative(mentions: list[RawSkillMention]) -> RawSkillMention:
    for evidence_type in _EVIDENCE_STRENGTH_ORDER:
        for mention in mentions:
            if mention.evidence_type == evidence_type:
                return mention
    return mentions[0]


class ResumeAnalyzerService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()

    async def analyze(
        self,
        raw: bytes,
        filename: str | None = None,
        mime_type: str | None = None,
        user_id: str | None = None,
    ) -> tuple[ResumeAnalysis, PersistenceSummary]:
        start = time.monotonic()
        if len(raw) > self._settings.RESUME_MAX_UPLOAD_BYTES:
            raise ResumeTooLargeError(
                f"Resume is {len(raw)} bytes, exceeding the {self._settings.RESUME_MAX_UPLOAD_BYTES}-byte limit"
            )

        content_type = resolve_content_type(filename, mime_type)
        parser = get_resume_parser(content_type)
        parsed = parser.parse(raw)  # may raise ResumeParsingFailedError (invalid PDF)
        warnings = list(parsed.warnings)

        text = parsed.text
        truncated = False
        if len(text) > self._settings.RESUME_MAX_TEXT_CHARS:
            text = text[: self._settings.RESUME_MAX_TEXT_CHARS]
            truncated = True
            warnings.append(f"Resume text was truncated to {self._settings.RESUME_MAX_TEXT_CHARS} characters.")

        sections = detect_sections(text, max_sections=self._settings.RESUME_MAX_SECTIONS)

        try:
            extractor = get_resume_extractor(self._settings)
            raw_extraction = await extractor.extract(text, sections)
        except AgentError as exc:
            # Normalizes Phase 4's LLM error surface into this module's
            # own error type, so the API layer only ever needs to catch
            # ResumeError for this endpoint.
            raise ResumeError(exc.message, code=exc.code) from exc

        skills, unmatched_skills = self._normalize_and_score_skills(raw_extraction.skill_mentions)

        document, _chunks_created = self._persist_document(text, sections, filename, content_type, warnings, truncated)

        user_skills_created, user_skills_updated = 0, 0
        if user_id is not None:
            user = self._db.query(User).filter_by(id=user_id).one_or_none()
            if user is None:
                warnings.append(f"user_id '{user_id}' was not found — skills were extracted but not persisted.")
            else:
                user_skills_created, user_skills_updated = self._persist_user_skills(user_id, skills)

        self._db.commit()
        logger.info(
            "Resume analysis complete: parser=%s skills=%d warnings=%d duration_ms=%d",
            type(parser).__name__,
            len(skills),
            len(warnings),
            int((time.monotonic() - start) * 1000),
        )

        analysis = ResumeAnalysis(
            summary=raw_extraction.summary,
            contact=ContactInfo(
                name=raw_extraction.contact_name,
                email=raw_extraction.contact_email,
                phone=raw_extraction.contact_phone,
                location=raw_extraction.contact_location,
                links=raw_extraction.contact_links[:10],
            ),
            skills=skills[: self._settings.RESUME_MAX_SKILLS],
            unmatched_skills=unmatched_skills[: self._settings.RESUME_MAX_SKILLS],
            experience=[
                ExperienceEntry(**{k: v for k, v in e.items() if not k.startswith("_")})
                for e in raw_extraction.experience[: self._settings.RESUME_MAX_EXPERIENCES]
            ],
            education=[EducationEntry(**e) for e in raw_extraction.education],
            projects=[
                ProjectEntry(**{k: v for k, v in p.items() if not k.startswith("_")})
                for p in raw_extraction.projects[: self._settings.RESUME_MAX_PROJECTS]
            ],
            certifications=[CertificationEntry(**c) for c in raw_extraction.certifications],
            achievements=raw_extraction.achievements,
            warnings=warnings,
            parser_metadata=ParserMetadata(
                parser_used=type(parser).__name__,
                content_type=content_type,
                extracted_char_count=len(text),
                truncated=truncated,
            ),
        )
        summary = PersistenceSummary(
            document_id=document.id,
            user_skills_created=user_skills_created,
            user_skills_updated=user_skills_updated,
        )
        return analysis, summary

    def _normalize_and_score_skills(self, mentions: list[RawSkillMention]) -> tuple[list[SkillEvidence], list[str]]:
        normalizer = SkillNormalizer(self._db)
        groups: dict[str, list[RawSkillMention]] = {}
        matched_skill_by_key: dict[str, object] = {}
        unmatched_seen: dict[str, str] = {}  # lowercased -> original casing

        for mention in mentions:
            skill = normalizer.normalize(mention.skill_name)
            if skill is not None:
                key = skill.slug
                matched_skill_by_key[key] = skill
            else:
                key = f"unmatched:{mention.skill_name.lower()}"
                unmatched_seen.setdefault(mention.skill_name.lower(), mention.skill_name)
            groups.setdefault(key, []).append(mention)

        skills: list[SkillEvidence] = []
        for key, group_mentions in groups.items():
            if key.startswith("unmatched:"):
                continue
            skill = matched_skill_by_key[key]
            level, confidence, reasoning = infer_proficiency(group_mentions)
            representative = _pick_representative(group_mentions)
            skills.append(
                SkillEvidence(
                    skill_name=representative.skill_name,
                    normalized_skill=skill.slug,
                    evidence_text=representative.evidence_text[:500],
                    evidence_type=representative.evidence_type,
                    source_section=representative.source_section,
                    confidence=confidence,
                    inferred_level=level if level != SkillLevel.NONE else SkillLevel.BEGINNER,
                    reasoning=reasoning,
                )
            )

        return skills, list(unmatched_seen.values())

    def _persist_document(
        self,
        text: str,
        sections: dict[str, str],
        filename: str | None,
        content_type: str,
        warnings: list[str],
        truncated: bool,
    ) -> tuple[Document, int]:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = Document(
            title=f"Resume upload{f' ({filename})' if filename else ''}",
            source=filename or "upload",
            content_hash=content_hash,
            document_metadata={
                "document_type": "resume",
                "content_type": content_type,
                "warnings": warnings,
                "truncated": truncated,
            },
        )
        self._db.add(document)
        self._db.flush()

        chunks_created = 0
        for index, (section_name, section_text) in enumerate(sections.items()):
            if not section_text.strip():
                continue
            self._db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=section_text,
                    chunk_metadata={"section": section_name},
                )
            )
            chunks_created += 1
        self._db.flush()
        return document, chunks_created

    def _persist_user_skills(self, user_id: str, skills: list[SkillEvidence]) -> tuple[int, int]:
        from app.models.skill import Skill  # local import avoids a cycle with skill_normalizer

        created, updated = 0, 0
        for skill_evidence in skills:
            skill_row = self._db.query(Skill).filter_by(slug=skill_evidence.normalized_skill).one_or_none()
            if skill_row is None:
                continue
            existing = self._db.query(UserSkill).filter_by(user_id=user_id, skill_id=skill_row.id).one_or_none()
            evidence_payload = [
                {
                    "type": skill_evidence.evidence_type,
                    "text": skill_evidence.evidence_text[:300],
                    "section": skill_evidence.source_section,
                }
            ]
            # Phase 12: assessment results live in their own ledger and must survive re-analysis. Keep the
            # assessment entries already on the row and re-apply the ledger's net confidence adjustment.
            kept = [
                e
                for e in ((existing.evidence if existing else None) or [])
                if isinstance(e, dict) and e.get("type") == "assessment"
            ]
            deltas = [
                row.confidence_delta_applied
                for row in self._db.query(AssessmentEvidence).filter_by(user_id=user_id, skill_id=skill_row.id)
            ]
            confidence = max(0.0, min(1.0, skill_evidence.confidence + net_adjustment(deltas)))
            if existing is not None:
                existing.current_level = skill_evidence.inferred_level
                existing.confidence = confidence
                existing.source = EvidenceSource.RESUME
                existing.evidence = evidence_payload + kept
                updated += 1
            else:
                self._db.add(
                    UserSkill(
                        user_id=user_id,
                        skill_id=skill_row.id,
                        current_level=skill_evidence.inferred_level,
                        confidence=confidence,
                        source=EvidenceSource.RESUME,
                        evidence=evidence_payload,
                    )
                )
                created += 1
        self._db.flush()
        return created, updated
