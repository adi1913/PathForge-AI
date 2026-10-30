from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, utcnow
from app.models.enums import ProgressEventType


class ProgressEvent(UUIDPKMixin, Base):
    """Append-only log of everything that changes a user's roadmap state
    (completion, quiz result, skip, re-plan, streak). This — not mutating
    RoadmapItem in place with no history — is what lets the adaptive
    re-planning agent look back at *why* the plan changed.

    Deliberately uses only `created_at` (no `updated_at`): rows here are
    never edited after insert, so TimestampMixin's onupdate half doesn't
    apply and is left out rather than added and ignored."""

    __tablename__ = "progress_events"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    roadmap_item_id: Mapped[str | None] = mapped_column(ForeignKey("roadmap_items.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[ProgressEventType] = mapped_column(
        Enum(ProgressEventType, native_enum=False, length=30), nullable=False
    )
    previous_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    event_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="progress_events")
