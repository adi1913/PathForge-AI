from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Profile(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(255))
    # Free-text current goal (e.g. "AI Engineer") kept separately from the
    # normalized `target_roles` catalog — a user can type a goal before it
    # resolves to a catalog TargetRole.
    target_role: Mapped[str | None] = mapped_column(String(255))
    available_hours_per_day: Mapped[float | None] = mapped_column()
    target_duration_days: Mapped[int | None] = mapped_column(Integer)
    # Free-form structured preferences (pace, content format, etc.) — kept
    # as JSON rather than a rigid column set since this evolves fastest.
    learning_preferences: Mapped[dict | None] = mapped_column(JSON)
    timezone: Mapped[str | None] = mapped_column(String(64))

    user: Mapped["User"] = relationship(back_populates="profile")
