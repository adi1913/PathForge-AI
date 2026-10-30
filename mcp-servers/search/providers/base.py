import sys
from abc import ABC, abstractmethod
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import SearchJobsResult, SearchTechnologyRequirementsResult, WebSearchResult


class SearchProvider(ABC):
    """Everything the Search MCP server's tools need, independent of
    whether results come from a real configured search/job-board API or
    deterministic demo data. See providers/demo.py and providers/real.py."""

    @abstractmethod
    async def web_search(self, query: str, max_results: int) -> WebSearchResult: ...

    @abstractmethod
    async def search_jobs(
        self, role: str, location: str | None, remote: bool | None, max_results: int
    ) -> SearchJobsResult: ...

    @abstractmethod
    async def search_technology_requirements(
        self, role: str, technology: str | None, max_results: int
    ) -> SearchTechnologyRequirementsResult: ...
