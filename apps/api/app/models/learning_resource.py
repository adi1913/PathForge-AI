from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import Difficulty, ResourceType


class LearningResource(UUIDPKMixin, TimestampMixin, Base):
    """A candidate course/doc/tutorial/project, normally populated by the
    Learning Resource MCP server (Phase 3) — modeled now so RoadmapItem
    and the seed script have something real to reference."""

    __tablename__ = "learning_resources"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, native_enum=False, length=20), nullable=False
    )
    url: Mapped[str | None] = mapped_column(String(1000))
    provider: Mapped[str | None] = mapped_column(String(150))
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"), index=True)
    difficulty: Mapped[Difficulty | None] = mapped_column(Enum(Difficulty, native_enum=False, length=20))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    # provider-specific extras (rating, language, mock-vs-live source tag)
    resource_metadata: Mapped[dict | None] = mapped_column(JSON)

    skill: Mapped["Skill | None"] = relationship()
