from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import GapSeverity, SkillImportance, SkillLevel, SkillMatchStatus
from app.resume.schemas import ParserMetadata

RequirementType = Literal["required", "preferred"]


class JobSkillRequirement(BaseModel):
    raw_name: str
    normalized_skill_id: str | None = None
    normalized_skill_name: str | None = None
    requirement_type: RequirementType
    importance: SkillImportance
    expected_level: SkillLevel
    evidence_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class JobDescriptionAnalysis(BaseModel):
    title: str | None = None
    company: str | None = None
    role: str | None = None
    summary: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[JobSkillRequirement] = Field(default_factory=list)
    preferred_skills: list[JobSkillRequirement] = Field(default_factory=list)
    unmatched_skills: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certification_requirements: list[str] = Field(default_factory=list)
    tools_and_technologies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_metadata: ParserMetadata


class SkillGapResult(BaseModel):
    skill_name: str
    skill_slug: str
    match_status: SkillMatchStatus
    severity: GapSeverity
    importance: SkillImportance
    requirement_type: RequirementType
    expected_level: SkillLevel
    current_level: SkillLevel
    confidence: float = Field(ge=0.0, le=1.0)
    priority_score: float = Field(ge=0.0, le=100.0)
    reasoning: str
    prerequisites: list[str] = Field(default_factory=list)


class UserSkillSummary(BaseModel):
    total_skills_evaluated: int
    matched_count: int
    weak_count: int
    missing_count: int
