from app.agent.state import AgentState, AgentStatus, ToolCallRecord


def test_agent_state_defaults():
    state = AgentState(user_request="hello")
    assert state.status == AgentStatus.PENDING
    assert state.tool_calls == []
    assert state.errors == []
    assert state.run_id  # auto-generated, non-empty
    assert state.final_response is None


def test_agent_state_is_extensible_for_later_phases():
    # These fields do nothing yet in Phase 4 but must exist so later
    # phases don't require a state-shape migration.
    state = AgentState(
        user_request="become an AI engineer",
        target_role="AI Engineer",
        identified_skills=["python"],
        gathered_evidence=[{"type": "resume", "note": "n/a"}],
    )
    assert state.target_role == "AI Engineer"
    assert state.identified_skills == ["python"]
    assert state.gathered_evidence[0]["type"] == "resume"


def test_tool_call_record_defaults():
    record = ToolCallRecord(server_name="github", tool_name="search_github_repositories", arguments={"query": "x"})
    assert record.success is None
    assert record.started_at is not None
    assert record.completed_at is None
