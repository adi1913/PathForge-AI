from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ImportanceLevel, SkillLevel


class TargetRole(UUIDPKMixin, TimestampMixin, Base):
    """Catalog of roles the roadmap engine knows how to target, e.g.
    "AI Engineer". Kept separate from a user's free-text goal on
    Profile.target_role so the same role definition can be reused and
    versioned across users."""

    __tablename__ = "target_roles"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))

    required_skills: Mapped[list["TargetRoleSkill"]] = relationship(
        back_populates="target_role", cascade="all, delete-orphan"
    )
    roadmaps: Mapped[list["Roadmap"]] = relationship(back_populates="target_role")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TargetRole {self.slug}>"


class TargetRoleSkill(Base):
    """One row per (role, skill) requirement, e.g. AI Engineer -> RAG
    (required, advanced)."""

    __tablename__ = "target_role_skills"
    __table_args__ = (UniqueConstraint("target_role_id", "skill_id", name="uq_target_role_skill"),)

    target_role_id: Mapped[str] = mapped_column(ForeignKey("target_roles.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)

    required_level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=20), default=SkillLevel.INTERMEDIATE, nullable=False
    )
    importance: Mapped[ImportanceLevel] = mapped_column(
        Enum(ImportanceLevel, native_enum=False, length=20), default=ImportanceLevel.REQUIRED, nullable=False
    )

    target_role: Mapped["TargetRole"] = relationship(back_populates="required_skills")
    skill: Mapped["Skill"] = relationship()
