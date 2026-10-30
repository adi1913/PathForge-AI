from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RepoEvidenceType


class EvaluateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    repository_url: str = Field(min_length=3, max_length=300)


class EvidenceItem(BaseModel):
    evidence_type: RepoEvidenceType
    excerpt: str
    confidence: float
    limitations: str


class SkillEvidenceGroup(BaseModel):
    skill_id: str
    skill_name: str
    skill_slug: str
    aggregate_confidence: float
    items: list[EvidenceItem]


class RepositoryOut(BaseModel):
    id: str
    github_url: str
    full_name: str
    description: str | None
    default_branch: str | None
    stars: int
    license: str | None
    is_fork: bool
    is_archived: bool


class EvaluationResponse(BaseModel):
    evaluation_id: str
    repository: RepositoryOut
    data_source: str  # demo | live
    evaluated_at: datetime
    reused_repository: bool = False
    signals: dict
    languages_percent: dict[str, float]
    unrecognized_languages: list[str]
    evidence: list[SkillEvidenceGroup]
    unmatched_technologies: list[str]
    inspected: list[str]
    limitations: list[str]
    note: str = (
        "Repository evidence is separate from your recorded skill levels. It never changes UserSkill and is "
        "not verified proficiency."
    )


class RepositoryListItem(BaseModel):
    id: str
    github_url: str
    last_analyzed_at: datetime | None
    latest_evaluation_id: str | None


class EvidenceListItem(BaseModel):
    repository: str
    skill_slug: str
    skill_name: str
    evidence_type: RepoEvidenceType
    excerpt: str
    confidence: float
    limitations: str
    data_source: str
    evaluated_at: datetime


class GithubEvidenceRef(BaseModel):
    """Compact form embedded in the application readiness report."""

    repository: str
    evidence_type: RepoEvidenceType
    excerpt: str
    confidence: float
    limitations: str
    data_source: str
    evaluated_at: datetime
