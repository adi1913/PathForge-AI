"""Evaluates a public repository (via the GitHub MCP server) and stores observations as skill
evidence. Never writes UserSkill / SkillGap / roadmaps."""

import logging
import time
from datetime import timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent.mcp_client import MCPClientManager
from app.models.project import GithubRepository
from app.models.repo_evidence import RepositoryEvaluation, SkillEvidence
from app.models.skill import Skill
from app.models.user import User
from app.repo_evidence.analysis import (
    GLOBAL_LIMITATIONS,
    LIMITATION,
    aggregate_confidence,
    compute_signals,
    extract_candidates,
    language_percent,
)
from app.repo_evidence.collector import RepositoryCollector, RepoSnapshot
from app.repo_evidence.errors import EvaluationNotFoundError, UserNotFoundError
from app.repo_evidence.queries import _utc, evidence_for_user, latest_evaluation_ids
from app.repo_evidence.schemas import (
    EvaluateRequest,
    EvaluationResponse,
    EvidenceItem,
    RepositoryListItem,
    RepositoryOut,
    SkillEvidenceGroup,
)
from app.repo_evidence.url import parse_repository_ref
from app.resume.skill_normalizer import SkillNormalizer

logger = logging.getLogger("pathforge.repo_evidence")


class RepositoryEvaluationService:
    def __init__(self, db: Session, manager: MCPClientManager):
        self._db = db
        self._manager = manager

    async def evaluate(self, request: EvaluateRequest) -> EvaluationResponse:
        owner, repo = parse_repository_ref(request.repository_url)
        if self._db.get(User, request.user_id) is None:
            raise UserNotFoundError()

        started = time.monotonic()
        snap = await RepositoryCollector(self._manager).collect(owner, repo)
        data_source = snap.details.source if snap.details.source in ("demo", "live") else "live"

        full_name = snap.details.repository.full_name or f"{owner}/{repo}"
        github_url = f"https://github.com/{full_name}"
        repository, reused = self._upsert_repository(request.user_id, github_url, full_name, snap)

        evaluation, unrecognized = self._build_evaluation(request.user_id, repository, snap, data_source)
        try:
            self._db.add(evaluation)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        logger.info(
            "Repository evaluated: source=%s tool_calls=%d evidence_rows=%d duration_ms=%d",
            data_source,
            snap.tool_calls,
            len(evaluation.evidence),
            int((time.monotonic() - started) * 1000),
        )
        return self._response(evaluation, repository, reused, unrecognized)

    def get_evaluation(self, evaluation_id: str, user_id: str) -> EvaluationResponse:
        evaluation = self._db.query(RepositoryEvaluation).filter_by(id=evaluation_id, user_id=user_id).one_or_none()
        if evaluation is None:
            raise EvaluationNotFoundError()
        unrecognized = (evaluation.languages or {}).get("unrecognized", [])
        return self._response(evaluation, evaluation.repository, False, unrecognized)

    def list_repositories(self, user_id: str) -> list[RepositoryListItem]:
        latest = latest_evaluation_ids(self._db, user_id)
        rows = self._db.query(GithubRepository).filter_by(user_id=user_id).order_by(GithubRepository.github_url).all()
        return [
            RepositoryListItem(
                id=r.id,
                github_url=r.github_url,
                last_analyzed_at=_utc(r.last_analyzed_at),
                latest_evaluation_id=latest.get(r.id),
            )
            for r in rows
        ]

    def list_evidence(self, user_id: str, skill: str | None):
        skill_ids = None
        if skill:
            row = self._db.query(Skill).filter_by(slug=skill.strip().lower()).one_or_none()
            skill_ids = [row.id] if row else []
        return evidence_for_user(self._db, user_id, skill_ids)

    # --- internals ---------------------------------------------------------------------------

    def _upsert_repository(self, user_id: str, github_url: str, full_name: str, snap: RepoSnapshot):
        repository = (
            self._db.query(GithubRepository)
            .filter(GithubRepository.user_id == user_id, func.lower(GithubRepository.github_url) == github_url.lower())
            .one_or_none()
        )
        reused = repository is not None
        owner, name = full_name.split("/", 1) if "/" in full_name else ("", full_name)
        if repository is None:
            repository = GithubRepository(user_id=user_id, github_url=github_url, owner=owner, repository_name=name)
            self._db.add(repository)
        summary = snap.details.repository
        repository.default_branch = snap.details.default_branch
        repository.repository_metadata = {
            "description": summary.description,
            "language": summary.language,
            "topics": summary.topics[:20],
            "stars": summary.stars,
            "license": snap.details.license,
            "is_fork": snap.details.is_fork,
            "is_archived": snap.details.is_archived,
        }
        from app.db.base import utcnow

        repository.last_analyzed_at = utcnow()
        self._db.flush()
        return repository, reused

    def _build_evaluation(self, user_id: str, repository: GithubRepository, snap: RepoSnapshot, data_source: str):
        normalizer = SkillNormalizer(self._db)
        candidates, parse_limits = extract_candidates(snap)
        limitations = [*GLOBAL_LIMITATIONS, *snap.limitations, *parse_limits]
        if snap.details.is_fork:
            limitations.append(
                "This repository is a fork; evidence may reflect upstream code rather than this user's work."
            )
        if snap.details.is_archived:
            limitations.append("This repository is archived; it may not reflect current practice.")
        if data_source == "demo":
            limitations.append("DEMO data: derived from fixture content, not from the real repository.")

        evaluation = RepositoryEvaluation(
            repository_id=repository.id,
            user_id=user_id,
            data_source=data_source,
            signals=compute_signals(snap),
            inspected=snap.inspected,
        )
        unmatched: dict[str, str] = {}
        seen: set[tuple[str, str]] = set()
        unrecognized_languages: list[str] = []
        for cand in candidates:
            skill = normalizer.normalize(cand.technology)
            if skill is None:
                if cand.evidence_type.value == "language_share":
                    unrecognized_languages.append(cand.technology)
                unmatched.setdefault(cand.technology.lower(), cand.technology)
                continue
            key = (skill.id, cand.evidence_type.value)
            if key in seen:
                continue
            seen.add(key)
            evaluation.evidence.append(
                SkillEvidence(
                    repository_id=repository.id,
                    user_id=user_id,
                    skill_id=skill.id,
                    evidence_type=cand.evidence_type,
                    excerpt=cand.excerpt[:300],
                    confidence=cand.confidence,
                    limitations=LIMITATION[cand.evidence_type],
                    data_source=data_source,
                )
            )
        if unrecognized_languages:
            limitations.append(
                "Languages not in the skill catalog were not turned into evidence: "
                + ", ".join(sorted(unrecognized_languages))
                + "."
            )
        evaluation.languages = {
            "percent": language_percent(snap.languages_bytes),
            "unrecognized": sorted(unrecognized_languages),
        }
        evaluation.limitations = limitations
        evaluation.unmatched_technologies = sorted(unmatched.values(), key=str.lower)
        return evaluation, sorted(unrecognized_languages)

    def _response(
        self, evaluation: RepositoryEvaluation, repository: GithubRepository, reused: bool, unrecognized: list[str]
    ) -> EvaluationResponse:
        meta = repository.repository_metadata or {}
        groups: dict[str, list[SkillEvidence]] = {}
        for row in evaluation.evidence:
            groups.setdefault(row.skill_id, []).append(row)
        evidence = []
        for rows in groups.values():
            rows = sorted(rows, key=lambda r: (-r.confidence, r.evidence_type.value))
            evidence.append(
                SkillEvidenceGroup(
                    skill_id=rows[0].skill_id,
                    skill_name=rows[0].skill.name,
                    skill_slug=rows[0].skill.slug,
                    aggregate_confidence=aggregate_confidence({r.evidence_type: r.confidence for r in rows}),
                    items=[
                        EvidenceItem(
                            evidence_type=r.evidence_type,
                            excerpt=r.excerpt,
                            confidence=r.confidence,
                            limitations=r.limitations,
                        )
                        for r in rows
                    ],
                )
            )
        evidence.sort(key=lambda g: (-g.aggregate_confidence, g.skill_slug))
        evaluated_at = evaluation.evaluated_at
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
        return EvaluationResponse(
            evaluation_id=evaluation.id,
            repository=RepositoryOut(
                id=repository.id,
                github_url=repository.github_url,
                full_name=f"{repository.owner}/{repository.repository_name}",
                description=meta.get("description"),
                default_branch=repository.default_branch,
                stars=meta.get("stars", 0),
                license=meta.get("license"),
                is_fork=meta.get("is_fork", False),
                is_archived=meta.get("is_archived", False),
            ),
            data_source=evaluation.data_source,
            evaluated_at=evaluated_at,
            reused_repository=reused,
            signals=evaluation.signals,
            languages_percent=(evaluation.languages or {}).get("percent", {}),
            unrecognized_languages=unrecognized,
            evidence=evidence,
            unmatched_technologies=evaluation.unmatched_technologies or [],
            inspected=evaluation.inspected or [],
            limitations=evaluation.limitations or [],
        )
