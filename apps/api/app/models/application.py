from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin, utcnow
from app.models.enums import ApplicationEventType, ApplicationStatus


class JobApplication(UUIDPKMixin, TimestampMixin, Base):
    """One tracked application. Requirements/skills are never copied here;
    they stay on the linked JobDescription (nullable: manual applications
    and applications whose JD was later deleted keep their history)."""

    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_description_id", name="uq_application_user_jd"),
        Index("ix_job_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    job_description_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="SET NULL"), index=True
    )
    target_role_id: Mapped[str | None] = mapped_column(ForeignKey("target_roles.id", ondelete="SET NULL"), index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=20), default=ApplicationStatus.INTERESTED, nullable=False
    )
    applied_on: Mapped[date | None] = mapped_column(Date)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    job_description: Mapped["JobDescription | None"] = relationship()
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.occurred_at"
    )


class ApplicationEvent(UUIDPKMixin, Base):
    """Append-only activity history (never edited after insert)."""

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_app_time", "application_id", "occurred_at"),)

    application_id: Mapped[str] = mapped_column(ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[ApplicationEventType] = mapped_column(
        Enum(ApplicationEventType, native_enum=False, length=20), nullable=False
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(Enum(ApplicationStatus, native_enum=False, length=20))
    to_status: Mapped[ApplicationStatus | None] = mapped_column(Enum(ApplicationStatus, native_enum=False, length=20))
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    application: Mapped["JobApplication"] = relationship(back_populates="events")
