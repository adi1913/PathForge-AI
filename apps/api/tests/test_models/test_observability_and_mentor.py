from app.models import (
    MCPToolLog,
    MentorMessage,
    MentorSession,
    ProgressEvent,
    User,
)
from app.models.enums import MCPToolStatus, MentorMessageRole, ProgressEventType


def make_user(db, email="obs@example.com"):
    user = User(email=email, password_hash="hashed")
    db.add(user)
    db.flush()
    return user


def test_progress_event_records_state_transition(db_session):
    user = make_user(db_session)
    db_session.add(
        ProgressEvent(
            user_id=user.id,
            event_type=ProgressEventType.ITEM_COMPLETED,
            previous_value="in_progress",
            new_value="completed",
            event_metadata={"roadmap_item_title": "Vector Databases"},
        )
    )
    db_session.commit()

    saved = db_session.query(ProgressEvent).filter_by(user_id=user.id).one()
    assert saved.event_type == ProgressEventType.ITEM_COMPLETED
    assert saved.event_metadata["roadmap_item_title"] == "Vector Databases"
    assert saved.created_at is not None


def test_mentor_session_and_message_ordering(db_session):
    user = make_user(db_session, "mentor@example.com")
    session = MentorSession(user_id=user.id, title="RAG questions")
    db_session.add(session)
    db_session.flush()

    db_session.add(MentorMessage(session_id=session.id, role=MentorMessageRole.USER, content="Explain embeddings."))
    db_session.add(MentorMessage(session_id=session.id, role=MentorMessageRole.MENTOR, content="Embeddings are ..."))
    db_session.commit()

    db_session.refresh(session)
    assert len(session.messages) == 2
    assert session.messages[0].role == MentorMessageRole.USER


def test_mcp_tool_log_stores_no_secret_like_fields(db_session):
    user = make_user(db_session, "mcp@example.com")
    log = MCPToolLog(
        user_id=user.id,
        run_id="run-123",
        server_name="github-mcp",
        tool_name="get_user_repositories",
        input_metadata={"username": "octocat"},
        output_metadata={"repo_count": 12},
        status=MCPToolStatus.SUCCESS,
        latency_ms=245,
    )
    db_session.add(log)
    db_session.commit()

    saved = db_session.query(MCPToolLog).filter_by(run_id="run-123").one()
    assert saved.status == MCPToolStatus.SUCCESS
    assert saved.output_metadata["repo_count"] == 12

    # Structural guard: the model must not expose any column whose name
    # suggests it's meant to hold a credential.
    forbidden_substrings = ("token", "api_key", "password", "secret", "authorization")
    column_names = [c.name for c in MCPToolLog.__table__.columns]
    for name in column_names:
        for bad in forbidden_substrings:
            assert bad not in name.lower(), f"MCPToolLog has a suspicious column: {name}"


def test_mcp_tool_log_records_failure_status(db_session):
    log = MCPToolLog(
        run_id="run-456",
        server_name="search-mcp",
        tool_name="search_jobs",
        status=MCPToolStatus.TIMEOUT,
        error_type="ToolTimeoutError",
        latency_ms=5000,
    )
    db_session.add(log)
    db_session.commit()

    saved = db_session.query(MCPToolLog).filter_by(run_id="run-456").one()
    assert saved.status == MCPToolStatus.TIMEOUT
    assert saved.error_type == "ToolTimeoutError"
    assert saved.user_id is None
