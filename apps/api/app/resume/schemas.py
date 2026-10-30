"""
The Resume Analyzer's core contract: every extraction stage produces or
consumes these validated Pydantic models — never free-form LLM text
passed straight through. See docs/architecture.md "Resume ingestion" for
the full pipeline this feeds into.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import SkillLevel

EvidenceType = Literal["explicit_mention", "demonstrated_usage", "work_experience", "certification", "inferred"]


class ContactInfo(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class SkillEvidence(BaseModel):
    """One skill claim, always traceable to the text that justified it.
    `normalized_skill` is the catalog slug if a match was found — never
    populated with a guess; an unmatched skill instead shows up in
    ResumeAnalysis.unmatched_skills, never silently dropped or invented
    into the catalog."""

    skill_name: str
    normalized_skill: str | None = None
    evidence_text: str
    evidence_type: EvidenceType
    source_section: str
    confidence: float = Field(ge=0.0, le=1.0)
    inferred_level: SkillLevel
    reasoning: str


class ExperienceEntry(BaseModel):
    company: str | None = None
    role: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    coursework: list[str] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
    credential_url: str | None = None


class ParserMetadata(BaseModel):
    parser_used: str
    content_type: str
    extracted_char_count: int
    truncated: bool = False


class ResumeAnalysis(BaseModel):
    summary: str | None = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    skills: list[SkillEvidence] = Field(default_factory=list)
    unmatched_skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser_metadata: ParserMetadata
