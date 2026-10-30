import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest
import server
from mcp import Client
from providers.real import RealLearningResourceProvider

from common.errors import ProviderUnavailableError


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


@pytest.mark.asyncio
async def test_all_four_tools_discoverable():
    async with Client(server.mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {
            "search_learning_resources",
            "get_learning_resource",
            "search_courses",
            "search_documentation",
        }


@pytest.mark.asyncio
async def test_search_by_skill_filters_results():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_learning_resources", {"skill": "mcp"})
        assert result.is_error is False
        for item in result.structured_content["results"]:
            assert "mcp" in [s.lower() for s in item["skills"]]


@pytest.mark.asyncio
async def test_search_courses_only_returns_courses():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_courses", {})
        assert result.is_error is False
        assert all(item["resource_type"] == "course" for item in result.structured_content["results"])


@pytest.mark.asyncio
async def test_search_documentation_only_returns_docs():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_documentation", {})
        assert result.is_error is False
        assert all(item["resource_type"] == "documentation" for item in result.structured_content["results"])


@pytest.mark.asyncio
async def test_get_resource_found():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_learning_resource", {"resource_id": "demo-course-python-advanced"})
        assert result.is_error is False
        assert result.structured_content["found"] is True
        assert result.structured_content["resource"]["id"] == "demo-course-python-advanced"


@pytest.mark.asyncio
async def test_get_resource_not_found_is_not_an_error():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_learning_resource", {"resource_id": "does-not-exist"})
        assert result.is_error is False
        assert result.structured_content["found"] is False
        assert result.structured_content["resource"] is None


@pytest.mark.asyncio
async def test_empty_resource_id_rejected():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_learning_resource", {"resource_id": "  "})
        assert result.is_error is True
        assert "must not be empty" in result.content[0].text


def test_real_provider_raises_actionable_error_when_unconfigured(monkeypatch):
    monkeypatch.delenv("LEARNING_PROVIDER_BASE_URL", raising=False)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        RealLearningResourceProvider()
    assert "LEARNING_PROVIDER_BASE_URL" in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_provider_get_resource_not_found_maps_404(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    real_async_client = httpx.AsyncClient

    class PatchedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    provider = RealLearningResourceProvider(base_url="https://learn.example.com")
    result = await provider.get_resource("nope")
    assert result.found is False
    assert result.source == "live"
