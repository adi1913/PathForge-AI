"""
Shared declarative base and mixins for every ORM model.

Design decisions (see docs/architecture.md for the full writeup):
- IDs are UUID4 strings stored as CHAR(36). A native TypeDecorator that
  swaps in Postgres UUID vs SQLite CHAR(36) was considered and rejected
  for Phase 2: plain strings work identically on both backends with zero
  custom type code, at the cost of a few bytes per row. Revisit only if
  profiling ever shows PK size mattering.
- Enums are stored with `native_enum=False` (see app/models/enums.py)
  so they become portable VARCHAR + CHECK constraints instead of
  Postgres-only native ENUM types that Alembic/SQLite handle awkwardly
  on downgrade.
- Every table gets created_at/updated_at in UTC via TimestampMixin.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Shared declarative base. All models must inherit from this so
    Alembic's autogenerate and Base.metadata.create_all() see them."""


class UUIDPKMixin:
    """Adds a UUID4-string primary key named `id`."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class TimestampMixin:
    """Adds created_at/updated_at, both UTC, updated_at auto-refreshed."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
