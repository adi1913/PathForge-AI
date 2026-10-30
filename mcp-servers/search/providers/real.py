"""
Real (non-demo) search provider.

There is no single canonical "the" web/job search API this project is
tied to — search/job-board providers vary by deployment. Rather than
hardcode one vendor (or worse, fabricate results), this implements a
generic HTTP contract: configure SEARCH_PROVIDER_BASE_URL to point at
any backend that implements the three GET endpoints below, and
SEARCH_PROVIDER_API_KEY if it requires bearer auth. If neither is
configured, this provider refuses to run with a clear, actionable error
rather than silently returning fake data — that fallback is DemoSearchProvider,
selected explicitly in server.py, never implicitly from within this class.

Expected upstream contract (documented in README.md too):
    GET {base_url}/search?q=...&max_results=...
        -> {"results": [{"title", "url", "snippet"}, ...]}
    GET {base_url}/jobs?role=...&location=...&remote=...&max_results=...
        -> {"results": [{"title","company","location","remote","url","posted_at","summary"}, ...]}
    GET {base_url}/technology-requirements?role=...&technology=...&max_results=...
        -> {"requirements": [{"technology","frequency_percent","importance"}, ...]}
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from schemas import (
    JobListing,
    SearchJobsResult,
    SearchTechnologyRequirementsResult,
    TechnologyRequirement,
    WebSearchResult,
    WebSearchResultItem,
)

from common import config
from common.errors import ProviderUnavailableError, UpstreamError, safe_log_exception
from providers.base import SearchProvider


class RealSearchProvider(SearchProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._base_url = base_url if base_url is not None else config.SEARCH_PROVIDER_BASE_URL
        self._api_key = api_key if api_key is not None else config.SEARCH_PROVIDER_API_KEY
        if not self._base_url:
            raise ProviderUnavailableError(
                "No live search provider is configured (SEARCH_PROVIDER_BASE_URL is unset). "
                "Set SEARCH_PROVIDER_BASE_URL (and SEARCH_PROVIDER_API_KEY if required), "
                "or set DEMO_MODE=true to use demo data instead."
            )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _get(self, path: str, params: dict) -> dict:
        url = f"{self._base_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            safe_log_exception("search_provider.get timeout", exc)
            raise UpstreamError(f"Search provider request to {path} timed out") from exc
        except httpx.HTTPError as exc:
            safe_log_exception("search_provider.get network error", exc)
            raise UpstreamError(f"Search provider request to {path} failed: network error") from exc

        if response.status_code >= 400:
            raise UpstreamError(f"Search provider returned HTTP {response.status_code} for {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(f"Search provider returned a malformed response for {path}") from exc

    async def web_search(self, query: str, max_results: int) -> WebSearchResult:
        body = await self._get("/search", {"q": query, "max_results": max_results})
        items = [WebSearchResultItem(**item) for item in body.get("results", [])[:max_results]]
        return WebSearchResult(source="live", query=query, results=items)

    async def search_jobs(
        self, role: str, location: str | None, remote: bool | None, max_results: int
    ) -> SearchJobsResult:
        body = await self._get(
            "/jobs", {"role": role, "location": location, "remote": remote, "max_results": max_results}
        )
        listings = [JobListing(**item) for item in body.get("results", [])[:max_results]]
        return SearchJobsResult(source="live", role=role, results=listings)

    async def search_technology_requirements(
        self, role: str, technology: str | None, max_results: int
    ) -> SearchTechnologyRequirementsResult:
        body = await self._get(
            "/technology-requirements",
            {"role": role, "technology": technology, "max_results": max_results},
        )
        reqs = [TechnologyRequirement(**item) for item in body.get("requirements", [])[:max_results]]
        return SearchTechnologyRequirementsResult(
            source="live", role=role, technology_filter=technology, requirements=reqs
        )
