from sqlalchemy import text


def test_db_session_can_execute_query(db_session):
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_db_session_tables_exist(db_session):
    from sqlalchemy import inspect

    tables = set(inspect(db_session.get_bind()).get_table_names())
    # Spot-check a representative slice rather than every table by name.
    for expected in {"users", "skills", "roadmaps", "assessments", "mcp_tool_logs"}:
        assert expected in tables
