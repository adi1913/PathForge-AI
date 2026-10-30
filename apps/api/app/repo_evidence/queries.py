from datetime import timezone

from sqlalchemy.orm import Session

from app.models.project import GithubRepository
from app.models.repo_evidence import RepositoryEvaluation, SkillEvidence
from app.repo_evidence.schemas import EvidenceListItem


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def latest_evaluation_ids(db: Session, user_id: str) -> dict[str, str]:
    """repository_id -> id of that repository's newest evaluation, for one user."""
    latest: dict[str, RepositoryEvaluation] = {}
    rows = (
        db.query(RepositoryEvaluation)
        .filter_by(user_id=user_id)
        .order_by(RepositoryEvaluation.evaluated_at, RepositoryEvaluation.id)
        .all()
    )
    for row in rows:
        latest[row.repository_id] = row
    return {repo_id: ev.id for repo_id, ev in latest.items()}


def evidence_for_user(db: Session, user_id: str, skill_ids: list[str] | None = None) -> list[EvidenceListItem]:
    """Evidence rows from each repository's latest evaluation only (older runs are history)."""
    evaluation_ids = list(latest_evaluation_ids(db, user_id).values())
    if not evaluation_ids:
        return []
    query = db.query(SkillEvidence).filter(SkillEvidence.evaluation_id.in_(evaluation_ids))
    if skill_ids is not None:
        query = query.filter(SkillEvidence.skill_id.in_(skill_ids))
    repos = {r.id: r.github_url for r in db.query(GithubRepository).filter_by(user_id=user_id)}
    items = [
        EvidenceListItem(
            repository=repos[e.repository_id].removeprefix("https://github.com/"),
            skill_slug=e.skill.slug,
            skill_name=e.skill.name,
            evidence_type=e.evidence_type,
            excerpt=e.excerpt,
            confidence=e.confidence,
            limitations=e.limitations,
            data_source=e.data_source,
            evaluated_at=_utc(e.evaluated_at),
        )
        for e in query.all()
    ]
    return sorted(items, key=lambda i: (i.skill_slug, -i.confidence, i.repository, i.evidence_type.value))
