import pytest

from app.agent.errors import ToolNotFoundError
from app.agent.mcp_client import MCPClientManager, bounded_result_summary


async def test_connects_to_all_three_servers():
    async with MCPClientManager() as manager:
        assert set(manager.connected_server_names()) == {"github", "search", "learning-resources"}


async def test_discovers_all_thirteen_tools():
    async with MCPClientManager() as manager:
        defs = manager.list_tool_definitions()
        names = {d.tool_name for d in defs}
        assert len(defs) == 13
        assert "search_github_repositories" in names
        assert "web_search" in names
        assert "search_learning_resources" in names
        for d in defs:
            assert d.description
            assert isinstance(d.input_schema, dict)


async def test_call_tool_success():
    async with MCPClientManager() as manager:
        result = await manager.call_tool("search_github_repositories", {"query": "rag"})
        assert result.is_error is False
        summary = bounded_result_summary(result)
        assert summary["data"]["source"] == "demo"


async def test_call_unknown_tool_raises_tool_not_found():
    async with MCPClientManager() as manager:
        with pytest.raises(ToolNotFoundError):
            await manager.call_tool("this_tool_does_not_exist", {})


async def test_manager_with_no_configs_connects_to_nothing():
    async with MCPClientManager(configs=[]) as manager:
        assert manager.connected_server_names() == []
        assert manager.list_tool_definitions() == []


async def test_bounded_result_summary_truncates_large_payloads():
    class FakeResult:
        def __init__(self):
            self.structured_content = {"data": "x" * 50_000}

    summary = bounded_result_summary(FakeResult())
    assert summary["truncated"] is True
    assert len(summary["preview"]) <= 20_000
