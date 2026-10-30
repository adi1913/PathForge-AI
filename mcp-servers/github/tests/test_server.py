"""
Protocol-level tests: exercises the real MCP server through mcp.Client
over in-memory transport (not by calling Python functions directly), so
these tests prove the tools are actually reachable over MCP, not just
that the underlying Python code works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import server
from mcp import Client


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


@pytest.mark.asyncio
async def test_all_six_tools_are_discoverable():
    async with Client(server.mcp) as client:
        tools = (await client.list_tools()).tools
        names = {t.name for t in tools}
        assert names == {
            "search_github_repositories",
            "get_github_repository",
            "get_repository_languages",
            "get_repository_structure",
            "get_repository_readme",
            "get_repository_file",
        }
        # Every tool must have a real, agent-oriented description, not a
        # one-liner like "Searches GitHub."
        for tool in tools:
            assert tool.description and len(tool.description) > 40


@pytest.mark.asyncio
async def test_search_repositories_demo_mode_tags_source():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_github_repositories", {"query": "rag"})
        assert result.is_error is False
        assert result.structured_content["source"] == "demo"
        assert len(result.structured_content["results"]) >= 1


@pytest.mark.asyncio
async def test_search_repositories_respects_max_results():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "search_github_repositories", {"query": "o", "max_results": 1}
        )
        assert len(result.structured_content["results"]) <= 1


@pytest.mark.asyncio
async def test_search_repositories_max_results_is_hard_capped():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "search_github_repositories", {"query": "o", "max_results": 999}
        )
        # Hard cap from common/config.py, even if the caller asks for more.
        assert len(result.structured_content["results"]) <= 25


@pytest.mark.asyncio
async def test_empty_query_is_rejected_with_safe_message():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_github_repositories", {"query": "  "})
        assert result.is_error is True
        text = result.content[0].text
        assert "must not be empty" in text
        # And nothing resembling a stack trace / internal path leaks through.
        assert "Traceback" not in text
        assert "site-packages" not in text


@pytest.mark.asyncio
async def test_get_repository_returns_normalized_fields():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_github_repository", {"owner": "octocat", "repo": "mcp-agent-toolkit"})
        assert result.is_error is False
        repo = result.structured_content["repository"]
        for field in ("name", "full_name", "description", "url", "stars", "forks", "language", "topics", "updated_at"):
            assert field in repo


@pytest.mark.asyncio
async def test_repository_structure_is_bounded_and_marked():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "get_repository_structure", {"owner": "octocat", "repo": "rag-demo"}
        )
        assert result.is_error is False
        assert "truncated" in result.structured_content
        assert isinstance(result.structured_content["entries"], list)


@pytest.mark.asyncio
async def test_readme_is_bounded_and_marked():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_repository_readme", {"owner": "octocat", "repo": "rag-demo"})
        assert result.is_error is False
        assert "truncated" in result.structured_content
        assert isinstance(result.structured_content["content"], str)


@pytest.mark.asyncio
async def test_get_repository_file_allowlisted_demo():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "get_repository_file", {"owner": "octocat", "repo": "rag-demo", "path": "pyproject.toml"}
        )
        assert result.is_error is False
        assert result.structured_content["source"] == "demo"
        assert "fastapi" in result.structured_content["content"]
        workflow = await client.call_tool(
            "get_repository_file", {"owner": "octocat", "repo": "r", "path": ".github/workflows/ci.yml"}
        )
        assert workflow.is_error is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["app/main.py", "../etc/passwd", ".env", ".github/workflows/../../secrets.yml", "/etc/passwd", ""]
)
async def test_get_repository_file_rejects_non_allowlisted_paths(path):
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "get_repository_file", {"owner": "octocat", "repo": "rag-demo", "path": path}
        )
        assert result.is_error is True


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["..", "a/b", "oct cat", "x" * 101, "a?b=c"])
async def test_repo_tools_reject_invalid_owner(owner):
    async with Client(server.mcp) as client:
        for tool, extra in [
            ("get_github_repository", {}),
            ("get_repository_languages", {}),
            ("get_repository_readme", {}),
            ("get_repository_file", {"path": "Dockerfile"}),
        ]:
            result = await client.call_tool(tool, {"owner": owner, "repo": "r", **extra})
            assert result.is_error is True


@pytest.mark.asyncio
async def test_missing_demo_file_is_a_clean_error():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "get_repository_file", {"owner": "o", "repo": "r", "path": "package.json"}
        )
        assert result.is_error is True
