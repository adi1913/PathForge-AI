from app.agent.errors import ToolExecutionError, ToolNotFoundError
from app.agent.llm.base import LLMProvider, ToolCallPlanItem
from app.agent.mcp_client import MCPToolDefinition
from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import AgentState, AgentStatus
from app.models import MCPToolLog


class FakeMCPManager:
    """Implements just enough of MCPClientManager's interface to drive
    the orchestrator deterministically, with controllable failures —
    faster and more precise than always spinning real subprocesses for
    every orchestrator-logic test. Real-subprocess coverage lives in
    test_mcp_client.py and test_api_agent_endpoint.py."""

    def __init__(self, tools: list[MCPToolDefinition], responses: dict, failures: dict | None = None):
        self._tools = tools
        self._responses = responses
        self._failures = failures or {}

    def list_tool_definitions(self):
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict):
        if tool_name in self._failures:
            raise self._failures[tool_name]
        if tool_name not in self._responses:
            raise ToolNotFoundError(tool_name)
        return self._responses[tool_name]


class FakeCallToolResult:
    def __init__(self, data: dict):
        self.is_error = False
        self.structured_content = data


class FixedPlanLLMProvider(LLMProvider):
    """Always returns a fixed plan, regardless of the request — lets
    orchestrator tests control exactly which tools get called."""

    def __init__(self, plan: list[ToolCallPlanItem], answer: str = "done"):
        self._plan = plan
        self._answer = answer

    async def plan(self, state, available_tools, max_tool_calls):
        return self._plan

    async def synthesize(self, state):
        return self._answer

    async def generate_structured(self, system, user, schema):
        raise NotImplementedError("not exercised by orchestrator tests")


_TOOLS = [MCPToolDefinition("github", "search_github_repositories", "desc", {})]


async def test_successful_run_marks_completed_and_records_tool_call(db_session):
    manager = FakeMCPManager(
        tools=_TOOLS,
        responses={"search_github_repositories": FakeCallToolResult({"source": "demo", "results": []})},
    )
    plan = [ToolCallPlanItem(tool_name="search_github_repositories", arguments={"query": "rag"}, reason="test")]
    orchestrator = AgentOrchestrator(manager, FixedPlanLLMProvider(plan), db=db_session)

    state = await orchestrator.run(AgentState(user_request="find rag repos"))

    assert state.status == AgentStatus.COMPLETED
    assert len(state.tool_calls) == 1
    assert state.tool_calls[0].success is True
    assert state.tool_calls[0].server_name == "github"
    assert state.final_response == "done"


async def test_tool_not_found_is_recorded_as_failed_call_not_a_crash(db_session):
    manager = FakeMCPManager(tools=_TOOLS, responses={})
    plan = [ToolCallPlanItem(tool_name="search_github_repositories", arguments={}, reason="test")]
    orchestrator = AgentOrchestrator(manager, FixedPlanLLMProvider(plan), db=db_session)

    state = await orchestrator.run(AgentState(user_request="x"))

    assert state.status == AgentStatus.COMPLETED  # the run itself still completes
    assert state.tool_calls[0].success is False
    assert "search_github_repositories" in state.tool_calls[0].error


async def test_tool_execution_error_is_recorded_safely(db_session):
    manager = FakeMCPManager(
        tools=_TOOLS,
        responses={},
        failures={"search_github_repositories": ToolExecutionError("upstream said no")},
    )
    plan = [ToolCallPlanItem(tool_name="search_github_repositories", arguments={}, reason="test")]
    orchestrator = AgentOrchestrator(manager, FixedPlanLLMProvider(plan), db=db_session)

    state = await orchestrator.run(AgentState(user_request="x"))

    assert state.tool_calls[0].success is False
    assert state.tool_calls[0].error == "upstream said no"
    assert state.status == AgentStatus.COMPLETED


async def test_max_tool_calls_truncates_oversized_plan(db_session):
    manager = FakeMCPManager(
        tools=_TOOLS,
        responses={"search_github_repositories": FakeCallToolResult({"source": "demo"})},
    )
    oversized_plan = [
        ToolCallPlanItem(tool_name="search_github_repositories", arguments={"query": str(i)}, reason="test")
        for i in range(10)
    ]
    orchestrator = AgentOrchestrator(manager, FixedPlanLLMProvider(oversized_plan), db=db_session, max_tool_calls=3)

    state = await orchestrator.run(AgentState(user_request="x"))

    assert len(state.tool_calls) == 3
    assert any("truncated" in e for e in state.errors)


async def test_tool_call_is_persisted_to_mcp_tool_log(db_session):
    from app.models import User

    user = User(email="agent-test@example.com", password_hash="hashed")
    db_session.add(user)
    db_session.commit()

    manager = FakeMCPManager(
        tools=_TOOLS,
        responses={"search_github_repositories": FakeCallToolResult({"source": "demo"})},
    )
    plan = [ToolCallPlanItem(tool_name="search_github_repositories", arguments={"query": "rag"}, reason="test")]
    orchestrator = AgentOrchestrator(manager, FixedPlanLLMProvider(plan), db=db_session)

    state = await orchestrator.run(AgentState(user_id=user.id, user_request="x"))

    logged = db_session.query(MCPToolLog).filter_by(run_id=state.run_id).all()
    assert len(logged) == 1
    assert logged[0].tool_name == "search_github_repositories"
    assert logged[0].server_name == "github"
    assert logged[0].user_id == user.id


class _AlwaysRaisesLLM(LLMProvider):
    async def plan(self, state, available_tools, max_tool_calls):
        raise RuntimeError("boom")

    async def synthesize(self, state):
        return "unreachable"

    async def generate_structured(self, system, user, schema):
        raise NotImplementedError("not exercised by orchestrator tests")


async def test_unexpected_exception_fails_gracefully_without_leaking_internals(db_session):
    manager = FakeMCPManager(tools=_TOOLS, responses={})
    orchestrator = AgentOrchestrator(manager, _AlwaysRaisesLLM(), db=db_session)

    state = await orchestrator.run(AgentState(user_request="x"))

    assert state.status == AgentStatus.FAILED
    assert "boom" not in (state.final_response or "")
    assert "boom" not in " ".join(state.errors)
