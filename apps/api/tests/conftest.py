"""
Shared test fixtures.

Every model/db test gets its own fresh in-memory SQLite database via the
`db_session` fixture below — never the developer's real `pathforge.db` or
whatever DATABASE_URL is configured. StaticPool keeps the same in-memory
DB alive across the single connection SQLAlchemy opens for it within one
test.
"""

import os

# Phases 1-11 tests call the HTTP API with a bare `user_id`; they run in the local/test-only trusted-caller mode.
# Enforcement is covered by tests/test_security/, which turns AUTH_REQUIRED on explicitly. Must be set before the
# settings are first read (the app caches them), hence at import time.
os.environ.setdefault("AUTH_REQUIRED", "false")

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - populates Base.metadata
from app.db.base import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
