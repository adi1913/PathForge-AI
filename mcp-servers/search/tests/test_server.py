import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest
import server
from mcp import Client
from providers.real import RealSearchProvider

from common.errors import ProviderUnavailableError


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")


@pytest.mark.asyncio
async def test_all_three_tools_discoverable():
    async with Client(server.mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {"web_search", "search_jobs", "search_technology_requirements"}


@pytest.mark.asyncio
async def test_web_search_demo_mode():
    async with Client(server.mcp) as client:
        result = await client.call_tool("web_search", {"query": "RAG pipelines"})
        assert result.is_error is False
        assert result.structured_content["source"] == "demo"
        assert len(result.structured_content["results"]) == 10  # default max_results


@pytest.mark.asyncio
async def test_web_search_respects_max_results():
    async with Client(server.mcp) as client:
        result = await client.call_tool("web_search", {"query": "x", "max_results": 2})
        assert len(result.structured_content["results"]) == 2


@pytest.mark.asyncio
async def test_empty_query_rejected():
    async with Client(server.mcp) as client:
        result = await client.call_tool("web_search", {"query": ""})
        assert result.is_error is True
        assert "must not be empty" in result.content[0].text


@pytest.mark.asyncio
async def test_search_jobs_filters_by_remote():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_jobs", {"role": "AI Engineer", "remote": True})
        assert result.is_error is False
        assert all(job["remote"] is True for job in result.structured_content["results"])


@pytest.mark.asyncio
async def test_technology_requirements_filters_by_technology():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "search_technology_requirements", {"role": "AI Engineer", "technology": "RAG"}
        )
        assert result.is_error is False
        assert all("RAG" in r["technology"] for r in result.structured_content["requirements"])


@pytest.mark.asyncio
async def test_unknown_role_falls_back_to_default_demo_set_not_empty():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_technology_requirements", {"role": "Underwater Basket Weaver"})
        assert result.is_error is False
        assert len(result.structured_content["requirements"]) > 0


def test_real_provider_raises_actionable_error_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SEARCH_PROVIDER_BASE_URL", raising=False)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        RealSearchProvider()
    assert "SEARCH_PROVIDER_BASE_URL" in str(exc_info.value)
    assert "DEMO_MODE=true" in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_provider_calls_configured_backend(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        return httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "https://example.com", "snippet": "S"}]},
        )

    real_async_client = httpx.AsyncClient

    class PatchedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    provider = RealSearchProvider(base_url="https://search.example.com", api_key="k")
    result = await provider.web_search("test", 5)
    assert result.source == "live"
    assert result.results[0].title == "T"
