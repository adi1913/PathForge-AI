"""
Real (non-demo) learning-resource provider. Same "BYO provider" pattern
as search/providers/real.py: configure LEARNING_PROVIDER_BASE_URL (and
LEARNING_PROVIDER_API_KEY if needed) to point at a backend implementing:

    GET {base_url}/resources?query=...&skill=...&level=...&resource_type=...&max_results=...
        -> {"results": [<LearningResourceItem fields>, ...]}
    GET {base_url}/resources/{resource_id}
        -> <LearningResourceItem fields> or 404

If unconfigured, raises ProviderUnavailableError with an actionable
message rather than fabricating results.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from schemas import (
    Difficulty,
    GetLearningResourceResult,
    LearningResourceItem,
    ResourceType,
    SearchLearningResourcesResult,
)

from common import config
from common.errors import ProviderUnavailableError, UpstreamError, safe_log_exception
from providers.base import LearningResourceProvider


class RealLearningResourceProvider(LearningResourceProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._base_url = base_url if base_url is not None else config.LEARNING_PROVIDER_BASE_URL
        self._api_key = api_key if api_key is not None else config.LEARNING_PROVIDER_API_KEY
        if not self._base_url:
            raise ProviderUnavailableError(
                "No live learning-resource provider is configured (LEARNING_PROVIDER_BASE_URL "
                "is unset). Set LEARNING_PROVIDER_BASE_URL (and LEARNING_PROVIDER_API_KEY if "
                "required), or set DEMO_MODE=true to use demo data instead."
            )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        url = f"{self._base_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as exc:
            safe_log_exception("learning_provider.get timeout", exc)
            raise UpstreamError(f"Learning resource provider request to {path} timed out") from exc
        except httpx.HTTPError as exc:
            safe_log_exception("learning_provider.get network error", exc)
            raise UpstreamError(f"Learning resource provider request to {path} failed: network error") from exc
        if response.status_code >= 400 and response.status_code != 404:
            raise UpstreamError(f"Learning resource provider returned HTTP {response.status_code} for {path}")
        return response

    async def search_resources(
        self,
        query: str | None,
        skill: str | None,
        level: Difficulty | None,
        resource_type: ResourceType | None,
        max_results: int,
    ) -> SearchLearningResourcesResult:
        response = await self._get(
            "/resources",
            {
                "query": query,
                "skill": skill,
                "level": level,
                "resource_type": resource_type,
                "max_results": max_results,
            },
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise UpstreamError("Learning resource provider returned a malformed response") from exc
        items = [LearningResourceItem(**item) for item in body.get("results", [])[:max_results]]
        return SearchLearningResourcesResult(
            source="live", query=query, skill=skill, resource_type=resource_type, results=items
        )

    async def get_resource(self, resource_id: str) -> GetLearningResourceResult:
        response = await self._get(f"/resources/{resource_id}")
        if response.status_code == 404:
            return GetLearningResourceResult(source="live", resource=None, found=False)
        try:
            body = response.json()
        except ValueError as exc:
            raise UpstreamError("Learning resource provider returned a malformed response") from exc
        return GetLearningResourceResult(source="live", resource=LearningResourceItem(**body), found=True)
