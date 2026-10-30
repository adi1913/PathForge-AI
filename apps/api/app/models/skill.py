from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EvidenceSource, SkillLevel


class Skill(UUIDPKMixin, TimestampMixin, Base):
    """Shared skill catalog. A single row per skill (e.g. "RAG") is
    referenced by user_skills, target_role_skills, job_description_skills,
    roadmap_items, etc. — never duplicated as free-form strings."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    category: Mapped[str | None] = mapped_column(String(100), index=True)

    user_skills: Mapped[list["UserSkill"]] = relationship(back_populates="skill")

    # Self-referential prerequisite graph: rows in `skill_prerequisites`
    # where this skill is the *dependent* one.
    prerequisites: Mapped[list["Skill"]] = relationship(
        secondary="skill_prerequisites",
        primaryjoin="Skill.id == SkillPrerequisite.skill_id",
        secondaryjoin="Skill.id == SkillPrerequisite.prerequisite_skill_id",
        viewonly=True,
    )
    # Reverse direction: skills that list *this* skill as a prerequisite.
    unlocks: Mapped[list["Skill"]] = relationship(
        secondary="skill_prerequisites",
        primaryjoin="Skill.id == SkillPrerequisite.prerequisite_skill_id",
        secondaryjoin="Skill.id == SkillPrerequisite.skill_id",
        viewonly=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Skill {self.slug}>"


class SkillPrerequisite(Base):
    """Association table for the skill dependency graph:
    `skill_id` requires `prerequisite_skill_id` to be learned first.
    Kept as an explicit mapped class (not Table()) so it can carry future
    columns like `strength`/`notes` without a migration rewrite."""

    __tablename__ = "skill_prerequisites"
    __table_args__ = (
        UniqueConstraint("skill_id", "prerequisite_skill_id", name="uq_skill_prerequisite_pair"),
        CheckConstraint("skill_id != prerequisite_skill_id", name="ck_skill_prerequisite_not_self"),
    )

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


class UserSkill(TimestampMixin, Base):
    """A user's self/system-assessed level on one skill, with the
    evidence that backs the claim — this is what stops the system from
    ever silently asserting "user knows Python" with nothing behind it."""

    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)

    current_level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=20),
        default=SkillLevel.NONE,
        nullable=False,
    )
    # 0.0-1.0 confidence in current_level, independent of the level itself
    # (e.g. "intermediate, low confidence" vs "intermediate, high confidence").
    confidence: Mapped[float | None] = mapped_column()
    # Structured evidence list, e.g. [{"type": "github", "repo": "...", "note": "..."}]
    evidence: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[EvidenceSource] = mapped_column(
        Enum(EvidenceSource, native_enum=False, length=30),
        default=EvidenceSource.MANUAL,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="user_skills")
    skill: Mapped["Skill"] = relationship(back_populates="user_skills")
