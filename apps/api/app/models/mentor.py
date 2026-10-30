from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin, utcnow
from app.models.enums import MentorMessageRole


class MentorSession(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "mentor_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="mentor_sessions")
    messages: Mapped[list["MentorMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="MentorMessage.created_at"
    )


class MentorMessage(UUIDPKMixin, Base):
    """No TimestampMixin here either — a chat message's created_at is
    also its natural ordering key and is never updated in place."""

    __tablename__ = "mentor_messages"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("mentor_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[MentorMessageRole] = mapped_column(
        Enum(MentorMessageRole, native_enum=False, length=20), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Never place API keys/secrets here — this is for things like which
    # roadmap item or skill the message referenced.
    message_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped["MentorSession"] = relationship(back_populates="messages")
