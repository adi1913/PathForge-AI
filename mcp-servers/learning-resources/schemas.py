from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["demo", "live"]
ResourceType = Literal["course", "documentation", "tutorial", "project", "video", "article"]
Difficulty = Literal["beginner", "intermediate", "advanced"]


class LearningResourceItem(BaseModel):
    id: str
    title: str
    description: str
    url: str
    provider: str
    resource_type: ResourceType
    difficulty: Difficulty | None = None
    skills: list[str] = Field(default_factory=list)
    estimated_hours: float | None = None
    # Provider-reported quality/relevance signal, e.g. a rating out of 5.
    # Optional — not every provider has this, real or demo.
    quality_score: float | None = None


class SearchLearningResourcesResult(BaseModel):
    source: Source
    query: str | None = None
    skill: str | None = None
    resource_type: ResourceType | None = None
    results: list[LearningResourceItem]


class GetLearningResourceResult(BaseModel):
    source: Source
    resource: LearningResourceItem | None
    found: bool
