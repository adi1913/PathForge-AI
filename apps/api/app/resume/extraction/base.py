from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class RawSkillMention(BaseModel):
    """A skill name as it literally appeared, with just enough context
    for later evidence scoring — normalization/evidence/proficiency
    happen downstream in app.resume.skill_normalizer / evidence.py, not
    here."""

    skill_name: str
    evidence_text: str
    evidence_type: str  # matches resume.schemas.EvidenceType values
    source_section: str


class RawExtraction(BaseModel):
    """Pre-normalization extraction output — both DemoResumeExtractor
    and RealResumeExtractor produce this same shape, so
    ResumeAnalyzerService's downstream steps (skill normalization,
    evidence scoring, persistence) never know which one ran."""

    summary: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_location: str | None = None
    contact_links: list[str] = Field(default_factory=list)
    skill_mentions: list[RawSkillMention] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    certifications: list[dict] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ResumeExtractor(ABC):
    @abstractmethod
    async def extract(self, text: str, sections: dict[str, str]) -> RawExtraction: ...
