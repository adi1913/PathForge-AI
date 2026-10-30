from app.agent.llm.demo import DemoLLMProvider
from app.agent.mcp_client import MCPToolDefinition
from app.agent.state import AgentState, ToolCallRecord

_ALL_TOOLS = [
    MCPToolDefinition("github", "search_github_repositories", "Search GitHub repos", {}),
    MCPToolDefinition("github", "get_github_repository", "Get repo details", {}),
    MCPToolDefinition("github", "get_repository_languages", "Get languages", {}),
    MCPToolDefinition("github", "get_repository_structure", "Get structure", {}),
    MCPToolDefinition("github", "get_repository_readme", "Get readme", {}),
    MCPToolDefinition("search", "web_search", "General web search", {}),
    MCPToolDefinition("search", "search_jobs", "Search job listings", {}),
    MCPToolDefinition("search", "search_technology_requirements", "Search tech requirements", {}),
    MCPToolDefinition("learning-resources", "search_learning_resources", "Search learning resources", {}),
    MCPToolDefinition("learning-resources", "get_learning_resource", "Get one resource", {}),
    MCPToolDefinition("learning-resources", "search_courses", "Search courses", {}),
    MCPToolDefinition("learning-resources", "search_documentation", "Search docs", {}),
]


async def test_github_intent_selects_github_search():
    provider = DemoLLMProvider()
    state = AgentState(user_request="Find good RAG projects on GitHub")
    plan = await provider.plan(state, _ALL_TOOLS, max_tool_calls=5)
    assert any(item.tool_name == "search_github_repositories" for item in plan)
    # Must NOT call every available tool by default.
    assert len(plan) < len(_ALL_TOOLS)


async def test_career_intent_selects_requirements_and_resources():
    provider = DemoLLMProvider()
    state = AgentState(user_request="What should I learn to become an AI Engineer?")
    plan = await provider.plan(state, _ALL_TOOLS, max_tool_calls=5)
    names = {item.tool_name for item in plan}
    assert "search_technology_requirements" in names
    assert "search_learning_resources" in names
    assert "search_github_repositories" not in names


async def test_job_intent_selects_search_jobs():
    provider = DemoLLMProvider()
    state = AgentState(user_request="Find AI engineer jobs that are remote")
    plan = await provider.plan(state, _ALL_TOOLS, max_tool_calls=5)
    assert any(item.tool_name == "search_jobs" for item in plan)


async def test_fallback_intent_uses_web_search():
    provider = DemoLLMProvider()
    state = AgentState(user_request="asdkjaslkdj random gibberish query")
    plan = await provider.plan(state, _ALL_TOOLS, max_tool_calls=5)
    assert len(plan) == 1
    assert plan[0].tool_name == "web_search"


async def test_plan_respects_max_tool_calls():
    provider = DemoLLMProvider()
    state = AgentState(
        user_request="I want to learn skills for a career as an AI Engineer with GitHub projects and jobs"
    )
    plan = await provider.plan(state, _ALL_TOOLS, max_tool_calls=1)
    assert len(plan) <= 1


async def test_plan_only_selects_tools_that_are_available():
    provider = DemoLLMProvider()
    state = AgentState(user_request="Find good RAG projects on GitHub")
    # github tools deliberately excluded from the available set
    limited_tools = [t for t in _ALL_TOOLS if t.server_name != "github"]
    plan = await provider.plan(state, limited_tools, max_tool_calls=5)
    assert all(item.tool_name != "search_github_repositories" for item in plan)


async def test_synthesize_with_no_tool_calls():
    provider = DemoLLMProvider()
    state = AgentState(user_request="hello")
    answer = await provider.synthesize(state)
    assert "wasn't able to find a relevant tool" in answer


async def test_synthesize_summarizes_successful_calls():
    provider = DemoLLMProvider()
    state = AgentState(user_request="Find RAG projects on GitHub")
    state.tool_calls.append(
        ToolCallRecord(
            server_name="github",
            tool_name="search_github_repositories",
            arguments={"query": "rag"},
            success=True,
            result_summary={"truncated": False, "data": {"results": [{"name": "rag-demo"}]}},
        )
    )
    answer = await provider.synthesize(state)
    assert "search_github_repositories" in answer
    assert "1 result" in answer


async def test_synthesize_acknowledges_failures():
    provider = DemoLLMProvider()
    state = AgentState(user_request="Find RAG projects on GitHub")
    state.tool_calls.append(
        ToolCallRecord(
            server_name="github",
            tool_name="search_github_repositories",
            arguments={"query": "rag"},
            success=False,
            error="timed out",
        )
    )
    answer = await provider.synthesize(state)
    assert "failed" in answer.lower()
    assert "timed out" in answer
