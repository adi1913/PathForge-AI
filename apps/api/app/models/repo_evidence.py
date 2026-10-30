from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, utcnow
from app.models.enums import RepoEvidenceType


class RepositoryEvaluation(UUIDPKMixin, Base):
    """One inspection run of a GithubRepository (history is kept). Holds observed
    signals and limitations only — no quality grades."""

    __tablename__ = "repository_evaluations"

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    data_source: Mapped[str] = mapped_column(String(10), nullable=False)  # demo | live
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    signals: Mapped[dict] = mapped_column(JSON, nullable=False)
    languages: Mapped[dict | None] = mapped_column(JSON)
    inspected: Mapped[list | None] = mapped_column(JSON)
    limitations: Mapped[list | None] = mapped_column(JSON)
    unmatched_technologies: Mapped[list | None] = mapped_column(JSON)

    repository: Mapped["GithubRepository"] = relationship()
    evidence: Mapped[list["SkillEvidence"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")


class SkillEvidence(UUIDPKMixin, Base):
    """Evidence that a repository relates to a catalog skill. Deliberately separate from
    UserSkill: this is an observation, not verified proficiency."""

    __tablename__ = "skill_evidence"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "skill_id", "evidence_type", name="uq_skill_evidence_row"),
        Index("ix_skill_evidence_user_skill", "user_id", "skill_id"),
    )

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("repository_evaluations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("github_repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[RepoEvidenceType] = mapped_column(
        Enum(RepoEvidenceType, native_enum=False, length=30), nullable=False
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    data_source: Mapped[str] = mapped_column(String(10), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    evaluation: Mapped["RepositoryEvaluation"] = relationship(back_populates="evidence")
    skill: Mapped["Skill"] = relationship()
