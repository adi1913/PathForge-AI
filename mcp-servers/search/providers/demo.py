"""
Deterministic demo data for the Search MCP server. Used whenever
DEMO_MODE=true, or whenever DEMO_MODE=false but no real provider is
configured would instead raise ProviderUnavailableError from
providers/real.py — this module never runs in that second case.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import (
    JobListing,
    SearchJobsResult,
    SearchTechnologyRequirementsResult,
    TechnologyRequirement,
    WebSearchResult,
    WebSearchResultItem,
)

from providers.base import SearchProvider

_DEMO_TECH_REQUIREMENTS: dict[str, list[TechnologyRequirement]] = {
    "ai engineer": [
        TechnologyRequirement(technology="Python", frequency_percent=92.0, importance="required"),
        TechnologyRequirement(technology="RAG", frequency_percent=68.0, importance="required"),
        TechnologyRequirement(technology="AI Agents", frequency_percent=55.0, importance="required"),
        TechnologyRequirement(technology="MCP", frequency_percent=21.0, importance="preferred"),
        TechnologyRequirement(technology="Docker", frequency_percent=61.0, importance="preferred"),
        TechnologyRequirement(technology="AWS", frequency_percent=58.0, importance="preferred"),
    ],
    "data analyst": [
        TechnologyRequirement(technology="SQL", frequency_percent=95.0, importance="required"),
        TechnologyRequirement(technology="Power BI", frequency_percent=48.0, importance="preferred"),
        TechnologyRequirement(technology="Python", frequency_percent=52.0, importance="preferred"),
        TechnologyRequirement(technology="Excel", frequency_percent=80.0, importance="required"),
    ],
}

_DEMO_JOBS: dict[str, list[JobListing]] = {
    "ai engineer": [
        JobListing(
            title="AI Engineer",
            company="Northwind Analytics (demo)",
            location="Remote",
            remote=True,
            url="https://example.com/jobs/demo-ai-engineer-1",
            posted_at="2026-08-15",
            summary="Build and ship RAG pipelines and agentic tooling for internal products.",
        ),
        JobListing(
            title="Applied AI Engineer",
            company="Fabrikam Labs (demo)",
            location="Bengaluru, India",
            remote=False,
            url="https://example.com/jobs/demo-ai-engineer-2",
            posted_at="2026-08-20",
            summary="Own the agent orchestration layer for a career-tech platform.",
        ),
    ]
}


class DemoSearchProvider(SearchProvider):
    async def web_search(self, query: str, max_results: int) -> WebSearchResult:
        base = [
            WebSearchResultItem(
                title=f"Demo result {i + 1} for '{query}'",
                url=f"https://example.com/demo-search/{i + 1}",
                snippet=(
                    f"This is deterministic DEMO_MODE content for the query '{query}'. "
                    "It is not fetched from a real search engine."
                ),
            )
            for i in range(max_results)
        ]
        return WebSearchResult(source="demo", query=query, results=base)

    async def search_jobs(
        self, role: str, location: str | None, remote: bool | None, max_results: int
    ) -> SearchJobsResult:
        listings = _DEMO_JOBS.get(role.lower(), _DEMO_JOBS["ai engineer"])
        if location:
            listings = [j for j in listings if location.lower() in (j.location or "").lower()] or listings
        if remote is not None:
            listings = [j for j in listings if j.remote == remote] or listings
        return SearchJobsResult(source="demo", role=role, results=listings[:max_results])

    async def search_technology_requirements(
        self, role: str, technology: str | None, max_results: int
    ) -> SearchTechnologyRequirementsResult:
        reqs = _DEMO_TECH_REQUIREMENTS.get(role.lower(), _DEMO_TECH_REQUIREMENTS["ai engineer"])
        if technology:
            reqs = [r for r in reqs if technology.lower() in r.technology.lower()] or reqs
        return SearchTechnologyRequirementsResult(
            source="demo", role=role, technology_filter=technology, requirements=reqs[:max_results]
        )
