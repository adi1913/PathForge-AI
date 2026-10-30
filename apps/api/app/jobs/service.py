"""Single entry point for JD analysis + skill-gap computation:
parse -> sections -> extract -> normalize -> classify -> persist JD ->
compare against UserSkill -> gap engine -> persist SkillGap -> response.
Skill-gap numbers come only from app.jobs.gap_engine (deterministic)."""

import hashlib
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.core.config import Settings, get_settings
from app.jobs.errors import JDTooLargeError, JobDescriptionError
from app.jobs.extraction.base import RawJDSkillMention
from app.jobs.extraction.factory import get_jd_extractor
from app.jobs.gap_engine import (
    build_reasoning,
    classify_match,
    compute_overall_match_score,
    compute_priority_score,
    compute_severity,
)
from app.jobs.parsers import get_jd_parser, resolve_content_type
from app.jobs.requirement_classifier import classify_importance, infer_expected_level
from app.jobs.schemas import (
    JobDescriptionAnalysis,
    JobSkillRequirement,
    SkillGapResult,
    UserSkillSummary,
)
from app.jobs.sections import detect_sections
from app.models.enums import GapSeverity, ImportanceLevel, SkillGapStatus, SkillLevel, SkillMatchStatus
from app.models.job_description import JobDescription, JobDescriptionSkill
from app.models.skill import Skill, UserSkill
from app.models.skill_gap import SkillGap
from app.models.target_role import TargetRole
from app.models.user import User
from app.resume.schemas import ParserMetadata
from app.resume.skill_normalizer import SkillNormalizer

logger = logging.getLogger("pathforge.jobs")


@dataclass
class GapAnalysisExtras:
    job_description_id: str
    matched_skills: list[SkillGapResult] = field(default_factory=list)
    weak_skills: list[SkillGapResult] = field(default_factory=list)
    missing_skills: list[SkillGapResult] = field(default_factory=list)
    skill_gaps: list[SkillGapResult] = field(default_factory=list)  # weak + missing, priority desc
    user_skill_summary: UserSkillSummary = field(
        default_factory=lambda: UserSkillSummary(
            total_skills_evaluated=0, matched_count=0, weak_count=0, missing_count=0
        )
    )
    overall_match_score: float | None = None
    critical_gap_count: int = 0
    high_gap_count: int = 0


class JobDescriptionAnalyzerService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()

    async def analyze(
        self,
        raw: bytes,
        filename: str | None = None,
        mime_type: str | None = None,
        user_id: str | None = None,
        target_role_id: str | None = None,
    ) -> tuple[JobDescriptionAnalysis, GapAnalysisExtras]:
        start = time.monotonic()
        if len(raw) > self._settings.JD_MAX_UPLOAD_BYTES:
            raise JDTooLargeError(
                f"Job description is {len(raw)} bytes, exceeding the {self._settings.JD_MAX_UPLOAD_BYTES}-byte limit"
            )

        content_type = resolve_content_type(filename, mime_type)
        parser = get_jd_parser(content_type)
        parsed = parser.parse(raw)
        warnings = list(parsed.warnings)

        text = parsed.text
        truncated = False
        if len(text) > self._settings.JD_MAX_TEXT_CHARS:
            text = text[: self._settings.JD_MAX_TEXT_CHARS]
            truncated = True
            warnings.append(f"Job description was truncated to {self._settings.JD_MAX_TEXT_CHARS} characters.")
        if not text.strip():
            warnings.append("Job description text is empty; no requirements could be extracted.")

        sections = detect_sections(text, max_sections=self._settings.JD_MAX_SECTIONS)

        try:
            extraction = await get_jd_extractor(self._settings).extract(text, sections)
        except AgentError as exc:
            raise JobDescriptionError(exc.message, code=exc.code) from exc

        required, preferred, unmatched = self._classify_requirements(extraction.skill_mentions, text)
        requirements = (required + preferred)[: self._settings.JD_MAX_SKILLS]

        analysis = JobDescriptionAnalysis(
            title=extraction.title,
            company=extraction.company,
            role=extraction.role,
            summary=extraction.summary,
            responsibilities=extraction.responsibilities,
            required_skills=[r for r in requirements if r.requirement_type == "required"],
            preferred_skills=[r for r in requirements if r.requirement_type == "preferred"],
            unmatched_skills=unmatched[: self._settings.JD_MAX_SKILLS],
            experience_requirements=extraction.experience_requirements,
            education_requirements=extraction.education_requirements,
            certification_requirements=extraction.certification_requirements,
            tools_and_technologies=extraction.tools_and_technologies,
            warnings=warnings,
            parser_metadata=ParserMetadata(
                parser_used=type(parser).__name__,
                content_type=content_type,
                extracted_char_count=len(text),
                truncated=truncated,
            ),
        )

        effective_user_id = user_id
        if user_id is not None and self._db.query(User).filter_by(id=user_id).one_or_none() is None:
            analysis.warnings.append(f"user_id '{user_id}' was not found — analysis was not persisted against a user.")
            effective_user_id = None

        if target_role_id is not None and self._db.query(TargetRole).filter_by(id=target_role_id).one_or_none() is None:
            analysis.warnings.append(f"target_role_id '{target_role_id}' was not found and was ignored.")
            target_role_id = None

        jd = self._persist_job_description(text, analysis, effective_user_id, filename, target_role_id)
        self._persist_job_description_skills(jd, requirements)

        extras = GapAnalysisExtras(job_description_id=jd.id)
        if effective_user_id is not None:
            self._compare_against_user(effective_user_id, jd, requirements, extras)
        else:
            analysis.warnings.append("No user_id supplied — skill-gap comparison was skipped.")

        self._db.commit()
        logger.info(
            "JD analysis complete: parser=%s required=%d preferred=%d unmatched=%d gaps=%d warnings=%d "
            "duration_ms=%d",
            type(parser).__name__,
            len(analysis.required_skills),
            len(analysis.preferred_skills),
            len(unmatched),
            len(extras.skill_gaps),
            len(analysis.warnings),
            int((time.monotonic() - start) * 1000),
        )
        return analysis, extras

    # --- requirement classification -------------------------------------------------------------

    def _classify_requirements(
        self, mentions: list[RawJDSkillMention], full_text: str
    ) -> tuple[list[JobSkillRequirement], list[JobSkillRequirement], list[str]]:
        normalizer = SkillNormalizer(self._db)
        groups: dict[str, list[RawJDSkillMention]] = {}
        skills: dict[str, Skill] = {}
        unmatched: dict[str, str] = {}

        for mention in mentions:
            skill = normalizer.normalize(mention.skill_name)
            if skill is None:
                unmatched.setdefault(mention.skill_name.lower(), mention.skill_name)
                continue
            skills[skill.slug] = skill
            groups.setdefault(skill.slug, []).append(mention)

        required: list[JobSkillRequirement] = []
        preferred: list[JobSkillRequirement] = []
        for slug, group in groups.items():
            requirement_type = "required" if any(m.requirement_type == "required" for m in group) else "preferred"
            representative = next((m for m in group if m.requirement_type == requirement_type), group[0])
            importance = classify_importance(representative, group, full_text)
            expected_level = infer_expected_level(representative, requirement_type)
            skill = skills[slug]
            requirement = JobSkillRequirement(
                raw_name=representative.skill_name,
                normalized_skill_id=skill.id,
                normalized_skill_name=skill.name,
                requirement_type=requirement_type,
                importance=importance,
                expected_level=expected_level,
                evidence_text=representative.evidence_text[:500],
                confidence=min(1.0, 0.5 + 0.1 * len(group)),
                reasoning=(
                    f"{requirement_type.capitalize()} skill mentioned {len(group)} time(s); "
                    f"importance {importance.value}, expected level {expected_level.value}."
                ),
            )
            (required if requirement_type == "required" else preferred).append(requirement)
        return required, preferred, list(unmatched.values())

    # --- persistence ----------------------------------------------------------------------------

    def _persist_job_description(
        self,
        text: str,
        analysis: JobDescriptionAnalysis,
        user_id: str | None,
        filename: str | None,
        target_role_id: str | None,
    ) -> JobDescription:
        metadata = {
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "parser": analysis.parser_metadata.parser_used,
            "unmatched_skills": analysis.unmatched_skills,
            "experience_requirements": analysis.experience_requirements,
            "education_requirements": analysis.education_requirements,
            "certification_requirements": analysis.certification_requirements,
            "target_role_id": target_role_id,
            "warnings": list(analysis.warnings),
        }
        existing = None
        if user_id is not None:
            existing = self._db.query(JobDescription).filter_by(user_id=user_id, raw_text=text).one_or_none()
        if existing is not None:
            existing.title = analysis.title
            existing.company = analysis.company
            existing.analysis_metadata = metadata
            for old in list(existing.extracted_skills):
                self._db.delete(old)
            self._db.flush()
            return existing

        jd = JobDescription(
            user_id=user_id,
            title=analysis.title,
            company=analysis.company,
            raw_text=text,
            source="upload" if filename else "pasted",
            analysis_metadata=metadata,
        )
        self._db.add(jd)
        self._db.flush()
        return jd

    def _persist_job_description_skills(self, jd: JobDescription, requirements: list[JobSkillRequirement]) -> None:
        for requirement in requirements:
            self._db.add(
                JobDescriptionSkill(
                    job_description_id=jd.id,
                    skill_id=requirement.normalized_skill_id,
                    required_level=requirement.expected_level,
                    importance=(
                        ImportanceLevel.REQUIRED
                        if requirement.requirement_type == "required"
                        else ImportanceLevel.PREFERRED
                    ),
                    criticality=requirement.importance,
                    confidence=requirement.confidence,
                    reasoning=requirement.reasoning,
                    evidence=requirement.evidence_text,
                )
            )
        self._db.flush()

    # --- gap comparison -------------------------------------------------------------------------

    def _compare_against_user(
        self,
        user_id: str,
        jd: JobDescription,
        requirements: list[JobSkillRequirement],
        extras: GapAnalysisExtras,
    ) -> None:
        user_skills = {us.skill_id: us for us in self._db.query(UserSkill).filter_by(user_id=user_id).all()}
        skills_by_id = (
            {s.id: s for s in self._db.query(Skill).filter(Skill.id.in_([r.normalized_skill_id for r in requirements]))}
            if requirements
            else {}
        )

        # Pass 1: status per requirement (needed so pass 2 can count prerequisite gaps).
        statuses: dict[str, tuple[SkillMatchStatus, SkillLevel, float]] = {}
        for requirement in requirements:
            statuses[requirement.normalized_skill_id] = classify_match(
                requirement, user_skills.get(requirement.normalized_skill_id)
            )
        gap_skill_ids = {sid for sid, (status, _, _) in statuses.items() if status != SkillMatchStatus.MATCHED}

        evaluated = []
        results: list[SkillGapResult] = []
        for requirement in requirements:
            status, current, confidence = statuses[requirement.normalized_skill_id]
            skill = skills_by_id[requirement.normalized_skill_id]
            prerequisites = list(skill.prerequisites)
            prerequisite_gap_count = sum(1 for p in prerequisites if p.id in gap_skill_ids)
            severity = compute_severity(status, requirement.importance, requirement.expected_level, current)
            priority = compute_priority_score(
                requirement.requirement_type, requirement.importance, severity, prerequisite_gap_count
            )
            reasoning = build_reasoning(requirement, status, current, severity)
            result = SkillGapResult(
                skill_name=skill.name,
                skill_slug=skill.slug,
                match_status=status,
                severity=severity,
                importance=requirement.importance,
                requirement_type=requirement.requirement_type,
                expected_level=requirement.expected_level,
                current_level=current,
                confidence=max(0.0, min(1.0, confidence)),
                priority_score=priority,
                reasoning=reasoning,
                prerequisites=sorted(p.name for p in prerequisites),
            )
            results.append(result)
            evaluated.append((requirement, status, current))
            if status != SkillMatchStatus.MATCHED:
                self._upsert_skill_gap(user_id, jd.id, skill, result, requirement)
            else:
                self._close_resolved_gap(user_id, skill, result)

        extras.matched_skills = [r for r in results if r.match_status == SkillMatchStatus.MATCHED]
        extras.weak_skills = [r for r in results if r.match_status == SkillMatchStatus.WEAK]
        extras.missing_skills = [r for r in results if r.match_status == SkillMatchStatus.MISSING]
        extras.skill_gaps = sorted(
            extras.weak_skills + extras.missing_skills, key=lambda r: (-r.priority_score, r.skill_slug)
        )
        extras.user_skill_summary = UserSkillSummary(
            total_skills_evaluated=len(results),
            matched_count=len(extras.matched_skills),
            weak_count=len(extras.weak_skills),
            missing_count=len(extras.missing_skills),
        )
        extras.overall_match_score = compute_overall_match_score(evaluated)
        extras.critical_gap_count = sum(1 for r in extras.skill_gaps if r.severity == GapSeverity.CRITICAL)
        extras.high_gap_count = sum(1 for r in extras.skill_gaps if r.severity == GapSeverity.HIGH)

    def _upsert_skill_gap(
        self, user_id: str, jd_id: str, skill: Skill, result: SkillGapResult, requirement: JobSkillRequirement
    ) -> None:
        gap = self._db.query(SkillGap).filter_by(user_id=user_id, skill_id=skill.id).one_or_none()
        if gap is None:
            gap = SkillGap(user_id=user_id, skill_id=skill.id)
            self._db.add(gap)
        gap.current_level = result.current_level
        gap.target_level = result.expected_level
        gap.gap_score = result.priority_score
        gap.reason = result.reasoning
        gap.evidence = {
            "requirement_type": result.requirement_type,
            "evidence_text": requirement.evidence_text[:300],
            "prerequisites": result.prerequisites,
        }
        gap.match_status = result.match_status
        gap.severity = result.severity
        gap.importance = result.importance
        gap.confidence = result.confidence
        gap.priority_score = result.priority_score
        gap.source_job_description_id = jd_id
        if gap.status == SkillGapStatus.CLOSED:  # the gap has reappeared
            gap.status = SkillGapStatus.OPEN
        self._db.flush()

    def _close_resolved_gap(self, user_id: str, skill: Skill, result: SkillGapResult) -> None:
        """A previously recorded gap that this analysis now finds matched is
        closed in place (never deleted), so history stays and no stale
        'weak/missing' row lingers."""
        gap = self._db.query(SkillGap).filter_by(user_id=user_id, skill_id=skill.id).one_or_none()
        if gap is None:
            return
        gap.current_level = result.current_level
        gap.match_status = SkillMatchStatus.MATCHED
        gap.severity = GapSeverity.NONE
        gap.priority_score = 0.0
        gap.gap_score = 0.0
        gap.reason = result.reasoning
        gap.status = SkillGapStatus.CLOSED
        self._db.flush()
