"""
Tests the real (non-demo) code path — GitHubClient's HTTP handling and
LiveGitHubProvider's normalization — entirely offline via
httpx.MockTransport. No test in this file makes a real network call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest
from client import GitHubClient
from providers.live import LiveGitHubProvider

from common.errors import RateLimitedError, UpstreamError


@pytest.fixture(autouse=True)
def _patch_httpx_client(monkeypatch):
    """GitHubClient.get/get_raw construct `httpx.AsyncClient(timeout=...)`
    directly. To inject a MockTransport without changing production code,
    patch httpx.AsyncClient for the duration of each test to pick up a
    transport set on the GitHubClient instance if present."""
    real_async_client = httpx.AsyncClient

    class PatchedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            transport = getattr(_patch_httpx_client, "_active_transport", None)
            if transport is not None:
                kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    yield
    _patch_httpx_client._active_transport = None


def _use_transport(handler):
    _patch_httpx_client._active_transport = httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_repository_normalizes_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/hello-world"
        return httpx.Response(
            200,
            json={
                "name": "hello-world",
                "full_name": "octocat/hello-world",
                "description": "My first repo",
                "html_url": "https://github.com/octocat/hello-world",
                "stargazers_count": 5,
                "forks_count": 1,
                "language": "Python",
                "topics": ["demo"],
                "updated_at": "2026-01-01T00:00:00Z",
                "default_branch": "main",
                "open_issues_count": 2,
                "license": {"spdx_id": "MIT"},
                "fork": False,
                "archived": False,
            },
        )

    _use_transport(handler)
    provider = LiveGitHubProvider(GitHubClient())
    result = await provider.get_repository("octocat", "hello-world")
    assert result.source == "live"
    assert result.repository.stars == 5
    assert result.license == "MIT"


@pytest.mark.asyncio
async def test_404_raises_upstream_error_without_leaking_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found", "internal_detail": "should-not-leak"})

    _use_transport(handler)
    provider = LiveGitHubProvider(GitHubClient())
    with pytest.raises(UpstreamError) as exc_info:
        await provider.get_repository("nobody", "nothing")
    assert "should-not-leak" not in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limited_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"},
            json={"message": "API rate limit exceeded"},
        )

    _use_transport(handler)
    provider = LiveGitHubProvider(GitHubClient())
    with pytest.raises(RateLimitedError):
        await provider.get_repository("octocat", "hello-world")


@pytest.mark.asyncio
async def test_token_never_appears_in_raised_error_message():
    def handler(request: httpx.Request) -> httpx.Response:
        # Confirm the header WAS sent (client works correctly)...
        assert request.headers.get("authorization") == "Bearer super-secret-token-123"
        # ...but a failure must never echo it back.
        return httpx.Response(500, text="internal error")

    _use_transport(handler)
    client = GitHubClient(token="super-secret-token-123")
    provider = LiveGitHubProvider(client)
    with pytest.raises(UpstreamError) as exc_info:
        await provider.get_repository("octocat", "hello-world")
    assert "super-secret-token-123" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_languages_are_normalized_to_percentages():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Python": 300, "HTML": 100})

    _use_transport(handler)
    provider = LiveGitHubProvider(GitHubClient())
    result = await provider.get_repository_languages("octocat", "hello-world")
    assert result.languages_percent["Python"] == 75.0
    assert result.languages_percent["HTML"] == 25.0


@pytest.mark.asyncio
async def test_readme_is_truncated_when_over_limit(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    monkeypatch.setenv("MCP_MAX_README_CHARS", "20")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 500)

    _use_transport(handler)
    provider = LiveGitHubProvider(GitHubClient())
    result = await provider.get_repository_readme("octocat", "hello-world")
    assert result.truncated is True
    assert len(result.content) == 20


@pytest.mark.asyncio
async def test_live_get_repository_file_bounded(monkeypatch):
    from providers.live import LiveGitHubProvider

    monkeypatch.setenv("MCP_MAX_FILE_CHARS", "10")

    class _Client:
        async def get_raw(self, path):
            assert path == "/repos/o/r/contents/package.json"
            return "x" * 50

    result = await LiveGitHubProvider(client=_Client()).get_repository_file("o", "r", "package.json")
    assert len(result.content) == 10 and result.truncated is True and result.source == "live"
