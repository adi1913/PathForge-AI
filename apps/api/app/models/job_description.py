from sqlalchemy import JSON, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ImportanceLevel, SkillImportance, SkillLevel


class JobDescription(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "job_descriptions"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))  # e.g. "pasted", "upload", "url"
    analysis_metadata: Mapped[dict | None] = mapped_column(JSON)

    user: Mapped["User | None"] = relationship(back_populates="job_descriptions")
    extracted_skills: Mapped[list["JobDescriptionSkill"]] = relationship(
        back_populates="job_description", cascade="all, delete-orphan"
    )


class JobDescriptionSkill(Base):
    """A skill extracted from a JobDescription, resolved against the
    shared skills catalog rather than kept as a free-form string, with
    the source snippet preserved as evidence for why it was extracted."""

    __tablename__ = "job_description_skills"
    __table_args__ = (UniqueConstraint("job_description_id", "skill_id", name="uq_job_description_skill"),)

    job_description_id: Mapped[str] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)

    required_level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=20), default=SkillLevel.INTERMEDIATE, nullable=False
    )
    importance: Mapped[ImportanceLevel] = mapped_column(
        Enum(ImportanceLevel, native_enum=False, length=20), default=ImportanceLevel.REQUIRED, nullable=False
    )
    evidence: Mapped[str | None] = mapped_column(Text)  # snippet of raw_text that justified extraction
    # Phase 7: deterministic severity-style score, distinct from `importance`
    # (which is the requirement type: required/preferred).
    criticality: Mapped[SkillImportance] = mapped_column(
        Enum(SkillImportance, native_enum=False, length=20), default=SkillImportance.MEDIUM, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)

    job_description: Mapped["JobDescription"] = relationship(back_populates="extracted_skills")
    skill: Mapped["Skill"] = relationship()
