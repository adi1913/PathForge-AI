from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ApplicationEventType, ApplicationStatus, GapSeverity, SkillLevel, SkillMatchStatus
from app.repo_evidence.schemas import GithubEvidenceRef

_NOTE_MAX = 2000


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class _UserScoped(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)


class ApplicationCreateRequest(_UserScoped):
    job_description_id: str | None = Field(default=None, max_length=36)
    target_role_id: str | None = Field(default=None, max_length=36)
    company: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=_NOTE_MAX)

    _strip = field_validator("company", "job_title", "notes", mode="after")(_clean)


class StatusUpdateRequest(_UserScoped):
    status: ApplicationStatus
    applied_on: date | None = None
    scheduled_at: datetime | None = None
    note: str | None = Field(default=None, max_length=_NOTE_MAX)

    _strip = field_validator("note", mode="after")(_clean)


class NoteRequest(_UserScoped):
    note: str = Field(min_length=1, max_length=_NOTE_MAX)

    _strip = field_validator("note", mode="after")(_clean)

    @field_validator("note")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("note must not be blank")
        return value


class ApplicationEventOut(BaseModel):
    id: str
    event_type: ApplicationEventType
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus | None
    note: str | None
    occurred_at: datetime


class ApplicationOut(BaseModel):
    id: str
    job_description_id: str | None
    target_role_id: str | None
    company: str | None
    job_title: str
    status: ApplicationStatus
    applied_on: date | None
    scheduled_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationOut):
    events: list[ApplicationEventOut]


class ApplicationListResponse(BaseModel):
    items: list[ApplicationOut]
    total: int
    limit: int
    offset: int


class ReadinessSkill(BaseModel):
    skill_name: str
    requirement_type: str
    importance: str
    expected_level: SkillLevel
    current_level: SkillLevel
    match_status: SkillMatchStatus
    severity: GapSeverity
    priority_score: float
    confidence: float
    data_kind: str  # measured | estimated | none
    evidence_source: str | None
    reasoning: str
    # Observations from evaluated repositories; informational only, never part of the score.
    github_evidence: list[GithubEvidenceRef] = Field(default_factory=list)


class RoadmapProgressRef(BaseModel):
    roadmap_id: str
    title: str
    percent_by_effort: float
    data_kind: str = "measured"


class ReadinessResponse(BaseModel):
    application_id: str
    status: str  # computed | unavailable
    reason: str | None = None
    overall_match_score: float | None = None
    matched_count: int = 0
    weak_count: int = 0
    missing_count: int = 0
    critical_gap_count: int = 0
    high_gap_count: int = 0
    skills: list[ReadinessSkill] = Field(default_factory=list)
    unmatched_requirements: list[str] = Field(default_factory=list)
    jd_analyzed_at: datetime | None = None
    skills_last_updated: datetime | None = None
    persisted_gaps_may_be_stale: bool = False
    roadmap: RoadmapProgressRef | None = None
    factors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str
