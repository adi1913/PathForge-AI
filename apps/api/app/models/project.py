from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ProjectStatus

_SCORE_RANGE = "0 <= {col} AND {col} <= 100"


class Project(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=20), default=ProjectStatus.PLANNED, nullable=False
    )
    repository_url: Mapped[str | None] = mapped_column(String(1000))

    user: Mapped["User"] = relationship(back_populates="projects")
    github_repository: Mapped["GithubRepository | None"] = relationship(back_populates="project", uselist=False)
    evaluations: Mapped[list["ProjectEvaluation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class GithubRepository(UUIDPKMixin, Base):
    """A GitHub repo the GitHub MCP server (Phase 3) has fetched evidence
    from. `project_id` is nullable/unique: a repo can be linked to one
    Project, or exist standalone (analyzed before being attached to a
    tracked project)."""

    __tablename__ = "github_repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_url", name="uq_github_repository_user_url"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), unique=True, index=True
    )
    github_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(100))
    repository_metadata: Mapped[dict | None] = mapped_column(JSON)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="github_repositories")
    project: Mapped["Project | None"] = relationship(back_populates="github_repository")


class ProjectEvaluation(UUIDPKMixin, TimestampMixin, Base):
    """A single scored evaluation run of a Project. Kept 1-to-many with
    Project (not overwritten in place) so evaluation history over time is
    preserved — useful once "did this project's evaluation improve after
    the user fixed testing?" matters."""

    __tablename__ = "project_evaluations"
    __table_args__ = (
        CheckConstraint(_SCORE_RANGE.format(col="overall_score"), name="ck_eval_overall_range"),
        CheckConstraint(_SCORE_RANGE.format(col="code_quality_score"), name="ck_eval_code_quality_range"),
        CheckConstraint(_SCORE_RANGE.format(col="architecture_score"), name="ck_eval_architecture_range"),
        CheckConstraint(_SCORE_RANGE.format(col="testing_score"), name="ck_eval_testing_range"),
        CheckConstraint(_SCORE_RANGE.format(col="documentation_score"), name="ck_eval_documentation_range"),
        CheckConstraint(_SCORE_RANGE.format(col="security_score"), name="ck_eval_security_range"),
        CheckConstraint(_SCORE_RANGE.format(col="deployment_score"), name="ck_eval_deployment_range"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    code_quality_score: Mapped[int | None] = mapped_column(Integer)
    architecture_score: Mapped[int | None] = mapped_column(Integer)
    testing_score: Mapped[int | None] = mapped_column(Integer)
    documentation_score: Mapped[int | None] = mapped_column(Integer)
    security_score: Mapped[int | None] = mapped_column(Integer)
    deployment_score: Mapped[int | None] = mapped_column(Integer)
    strengths: Mapped[list | None] = mapped_column(JSON)
    weaknesses: Mapped[list | None] = mapped_column(JSON)
    recommendations: Mapped[list | None] = mapped_column(JSON)

    project: Mapped["Project"] = relationship(back_populates="evaluations")
