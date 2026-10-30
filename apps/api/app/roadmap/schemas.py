from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Difficulty, RoadmapItemStatus, RoadmapItemType, RoadmapStatus


class RoadmapGenerateRequest(BaseModel):
    user_id: str
    target_role_id: str | None = None
    job_description_id: str | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=16)
    duration_days: int | None = Field(default=None, gt=0, le=1825)


class RoadmapItemOut(BaseModel):
    id: str
    order_index: int
    item_type: RoadmapItemType
    skill_slug: str | None
    title: str
    description: str | None
    week_number: int | None
    estimated_minutes: int | None
    difficulty: Difficulty | None
    status: RoadmapItemStatus
    completion_percentage: float
    prerequisite_item_ids: list[str]


class RoadmapSummary(BaseModel):
    total_estimated_minutes: int
    estimated_weeks: int
    deadline_days: int | None
    # Pace details are only known at generation time (the pace is not stored
    # on the roadmap), so they are null when an existing roadmap is fetched.
    estimated_days: int | None = None
    hours_per_day: float | None = None
    study_days_per_week: int | None = None
    fits_deadline: bool | None = None  # also null when no deadline is known


class RoadmapResponse(BaseModel):
    id: str
    user_id: str
    target_role_id: str | None
    title: str
    description: str | None
    status: RoadmapStatus
    generated_by: str
    created_at: datetime
    summary: RoadmapSummary
    items: list[RoadmapItemOut]
    warnings: list[str] = Field(default_factory=list)


class RoadmapListItem(BaseModel):
    id: str
    title: str
    status: RoadmapStatus
    generated_by: str
    duration_days: int | None
    created_at: datetime


# --- Phase 9: progress tracking + re-planning ---------------------------------------------------


class ProgressUpdateRequest(BaseModel):
    user_id: str
    status: RoadmapItemStatus
    completion_percentage: float | None = Field(default=None, ge=0, le=100)


class ItemProgress(BaseModel):
    item_id: str
    item_type: RoadmapItemType
    skill_slug: str | None
    title: str
    status: RoadmapItemStatus
    completion_percentage: float
    order_index: int
    week_number: int | None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProgressSummary(BaseModel):
    total_skills: int
    not_started: int
    in_progress: int
    blocked: int
    completed: int
    skipped: int
    percent_by_items: float  # completed / (total - skipped)
    percent_by_effort: float  # effort-weighted, partial progress counts


class ProgressEventOut(BaseModel):
    id: str
    event_type: str
    roadmap_item_id: str | None
    previous_value: str | None
    new_value: str | None
    created_at: datetime
    metadata: dict | None = None


class ProgressUpdateResponse(BaseModel):
    item: ItemProgress
    roadmap_status: RoadmapStatus
    summary: ProgressSummary
    warnings: list[str] = Field(default_factory=list)


class RoadmapProgressResponse(BaseModel):
    roadmap_id: str
    status: RoadmapStatus
    summary: ProgressSummary
    replan_count: int
    items: list[ItemProgress]
    recent_events: list[ProgressEventOut]


class ReplanRequest(BaseModel):
    user_id: str
    hours_per_day: float | None = Field(default=None, gt=0, le=16)
    duration_days: int | None = Field(default=None, gt=0, le=1825)


class ReplanSummary(BaseModel):
    remaining_skills: int
    resolved_skills: int
    remaining_minutes: int
    estimated_days: int
    estimated_weeks: int
    hours_per_day: float
    study_days_per_week: int
    deadline_days: int | None
    fits_deadline: bool | None
    stalled_skills: list[str]
    changed_items: int  # skill items whose order or week moved


class ReplanResponse(BaseModel):
    roadmap: RoadmapResponse
    replan: ReplanSummary
