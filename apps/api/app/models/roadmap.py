from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import Difficulty, RoadmapItemStatus, RoadmapItemType, RoadmapStatus


class Roadmap(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roadmaps"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_role_id: Mapped[str | None] = mapped_column(ForeignKey("target_roles.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[RoadmapStatus] = mapped_column(
        Enum(RoadmapStatus, native_enum=False, length=20), default=RoadmapStatus.DRAFT, nullable=False
    )
    # "agent" once Phase 4 generates roadmaps automatically; "manual" or
    # "seed" for anything created outside the agent (e.g. this phase's
    # seed script), so provenance is always visible.
    generated_by: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)

    user: Mapped["User"] = relationship(back_populates="roadmaps")
    target_role: Mapped["TargetRole | None"] = relationship(back_populates="roadmaps")
    items: Mapped[list["RoadmapItem"]] = relationship(
        back_populates="roadmap", cascade="all, delete-orphan", order_by="RoadmapItem.order_index"
    )


class RoadmapItem(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roadmap_items"
    __table_args__ = (UniqueConstraint("roadmap_id", "order_index", name="uq_roadmap_item_order"),)

    roadmap_id: Mapped[str] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"), index=True)

    item_type: Mapped[RoadmapItemType] = mapped_column(
        Enum(RoadmapItemType, native_enum=False, length=30), default=RoadmapItemType.SKILL, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Deterministic global ordering within the roadmap (unique per roadmap,
    # enforced above). week_number is a derived display grouping.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int | None] = mapped_column(Integer)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[Difficulty | None] = mapped_column(Enum(Difficulty, native_enum=False, length=20))
    status: Mapped[RoadmapItemStatus] = mapped_column(
        Enum(RoadmapItemStatus, native_enum=False, length=20),
        default=RoadmapItemStatus.NOT_STARTED,
        nullable=False,
    )
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # IDs of other RoadmapItem rows that must be completed first. Kept as
    # a JSON list rather than a self-referential association table: within
    # one roadmap, order_index + skill prerequisites already give a
    # deterministic order, so this is advisory metadata for the adaptive
    # re-planner, not a constraint the DB needs to enforce.
    prerequisite_item_ids: Mapped[list | None] = mapped_column(JSON)

    roadmap: Mapped["Roadmap"] = relationship(back_populates="items")
    skill: Mapped["Skill | None"] = relationship()
