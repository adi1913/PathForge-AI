from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import GapSeverity, SkillGapStatus, SkillImportance, SkillLevel, SkillMatchStatus


class SkillGap(UUIDPKMixin, TimestampMixin, Base):
    """One row per (user, skill) gap the agent has identified — the
    output of comparing UserSkill against a TargetRole/JobDescription
    requirement. Populated by the Skill Gap Agent in Phase 4/7, not here."""

    __tablename__ = "skill_gaps"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill_gap"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False)

    current_level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=20), default=SkillLevel.NONE, nullable=False
    )
    target_level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=20), default=SkillLevel.INTERMEDIATE, nullable=False
    )
    # Numeric distance derived from (target_level - current_level) plus
    # importance weighting — used to sort/prioritize, not a display value.
    gap_score: Mapped[float | None] = mapped_column()
    priority: Mapped[int | None] = mapped_column(Integer)  # lower = more urgent
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[SkillGapStatus] = mapped_column(
        Enum(SkillGapStatus, native_enum=False, length=20), default=SkillGapStatus.OPEN, nullable=False
    )

    # Phase 7 fields
    match_status: Mapped[SkillMatchStatus] = mapped_column(
        Enum(SkillMatchStatus, native_enum=False, length=20), default=SkillMatchStatus.MISSING, nullable=False
    )
    severity: Mapped[GapSeverity] = mapped_column(
        Enum(GapSeverity, native_enum=False, length=20), default=GapSeverity.NONE, nullable=False
    )
    importance: Mapped[SkillImportance] = mapped_column(
        Enum(SkillImportance, native_enum=False, length=20), default=SkillImportance.MEDIUM, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    priority_score: Mapped[float | None] = mapped_column(Float)  # 0-100, higher = more urgent
    source_job_description_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="SET NULL"), index=True, nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="skill_gaps")
    source_job_description: Mapped["JobDescription | None"] = relationship()
    skill: Mapped["Skill"] = relationship()
