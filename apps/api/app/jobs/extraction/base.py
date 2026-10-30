from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class RawJDSkillMention(BaseModel):
    skill_name: str
    evidence_text: str
    requirement_type: str  # "required" | "preferred"
    source_section: str


class RawJDExtraction(BaseModel):
    """Pre-normalization output shared by the demo and real extractors."""

    title: str | None = None
    company: str | None = None
    role: str | None = None
    summary: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    skill_mentions: list[RawJDSkillMention] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certification_requirements: list[str] = Field(default_factory=list)
    tools_and_technologies: list[str] = Field(default_factory=list)


class JobDescriptionExtractor(ABC):
    @abstractmethod
    async def extract(self, text: str, sections: dict[str, str]) -> RawJDExtraction: ...
