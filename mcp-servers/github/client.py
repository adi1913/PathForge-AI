"""
A single reusable async HTTP client for the GitHub REST API. Every real
(non-demo) GitHub call goes through this — no ad hoc httpx calls scattered
through providers/live.py.

Security notes:
- The token (if configured) is only ever placed in the Authorization
  header of the outgoing request. It is never logged, never included in
  a raised exception message, and never echoed back in a tool response.
- All requests carry a bounded timeout (HTTP_TIMEOUT_SECONDS).
- Non-2xx responses are translated into the common.errors exception
  types with sanitized messages — never a raw response body dump.
"""
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for `import common`
from common import config
from common.errors import RateLimitedError, UpstreamError, safe_log_exception


class GitHubClient:
    def __init__(self, token: str | None = None, base_url: str | None = None):
        self._token = token if token is not None else config.GITHUB_TOKEN
        self._base_url = (base_url or config.GITHUB_API_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            safe_log_exception("github_client.get timeout", exc)
            raise UpstreamError(f"GitHub API request to {path} timed out") from exc
        except httpx.HTTPError as exc:
            safe_log_exception("github_client.get network error", exc)
            raise UpstreamError(f"GitHub API request to {path} failed: network error") from exc

        self._raise_for_rate_limit(response)

        if response.status_code == 404:
            raise UpstreamError(f"GitHub resource not found: {path}")
        if response.status_code >= 400:
            # Deliberately do not include response.text: GitHub error bodies
            # are usually safe, but we don't want a policy exception to
            # trust that in perpetuity.
            raise UpstreamError(f"GitHub API returned HTTP {response.status_code} for {path}")

        return response

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Like `get`, but requests the raw content representation (used
        for READMEs) and returns decoded text instead of a Response."""
        url = f"{self._base_url}{path}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.raw+json"
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            safe_log_exception("github_client.get_raw timeout", exc)
            raise UpstreamError(f"GitHub API request to {path} timed out") from exc
        except httpx.HTTPError as exc:
            safe_log_exception("github_client.get_raw network error", exc)
            raise UpstreamError(f"GitHub API request to {path} failed: network error") from exc

        self._raise_for_rate_limit(response)
        if response.status_code == 404:
            raise UpstreamError(f"GitHub resource not found: {path}")
        if response.status_code >= 400:
            raise UpstreamError(f"GitHub API returned HTTP {response.status_code} for {path}")
        return response.text

    def _raise_for_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        if response.status_code == 403 and remaining == "0":
            reset_header = response.headers.get("x-ratelimit-reset")
            retry_after = None
            if reset_header and reset_header.isdigit():
                import time

                retry_after = max(0, int(reset_header) - int(time.time()))
            hint = "" if self._token else " (unauthenticated — set GITHUB_TOKEN for a higher limit)"
            raise RateLimitedError(f"GitHub API rate limit exceeded{hint}", retry_after_seconds=retry_after)
