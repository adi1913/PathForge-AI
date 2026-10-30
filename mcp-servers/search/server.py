"""
Search MCP server. Transport: stdio (see docs/architecture.md).

Provider selection:
    DEMO_MODE=true (default) -> DemoSearchProvider, zero credentials needed
    DEMO_MODE=false          -> RealSearchProvider; raises
                                ProviderUnavailableError with an actionable
                                message if SEARCH_PROVIDER_BASE_URL isn't set
                                (never silently falls back to fake data)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer
from providers.base import SearchProvider
from providers.demo import DemoSearchProvider
from providers.real import RealSearchProvider
from schemas import SearchJobsResult, SearchTechnologyRequirementsResult, WebSearchResult

from common import config
from common.errors import InvalidArgumentsError


def get_provider() -> SearchProvider:
    if config.DEMO_MODE:
        return DemoSearchProvider()
    return RealSearchProvider()  # raises ProviderUnavailableError if unconfigured


mcp = MCPServer(
    name="pathforge-search-mcp",
    instructions=(
        "Provides general web search, job-listing search, and role/technology "
        "requirement lookups. Use these tools when the agent needs current external "
        "information — e.g. what a target role typically requires, or example job "
        "postings — rather than relying on the LLM's own training data, which may be "
        "outdated."
    ),
)


def _require_non_empty(value: str, field: str) -> str:
    if not value or not value.strip():
        raise InvalidArgumentsError(f"'{field}' must not be empty")
    return value.strip()


@mcp.tool(
    description=(
        "Run a general web search and return normalized results (title, url, snippet). "
        "Use this for open-ended research questions that aren't specifically about job "
        "listings or role requirements — e.g. looking up how a technology works or "
        "finding a tutorial."
    )
)
async def web_search(query: str, max_results: int | None = None) -> WebSearchResult:
    query = _require_non_empty(query, "query")
    bounded = config.clamp_max_results(max_results)
    return await get_provider().web_search(query, bounded)


@mcp.tool(
    description=(
        "Search job listings for a target role, optionally filtered by location or "
        "remote status. Use this to ground a roadmap or readiness assessment in real "
        "current job-market listings rather than assumptions about what a role needs."
    )
)
async def search_jobs(
    role: str, location: str | None = None, remote: bool | None = None, max_results: int | None = None
) -> SearchJobsResult:
    role = _require_non_empty(role, "role")
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_jobs(role, location, remote, bounded)


@mcp.tool(
    description=(
        "Look up which technologies/skills are commonly required for a target role, "
        "with how frequently each appears and how important it typically is (required "
        "vs preferred vs nice-to-have). Optionally filter to a specific technology to "
        "check its relevance to the role. Use this before generating a skill-gap "
        "analysis or roadmap, so requirements reflect current market signal rather than "
        "the LLM's static training data."
    )
)
async def search_technology_requirements(
    role: str, technology: str | None = None, max_results: int | None = None
) -> SearchTechnologyRequirementsResult:
    role = _require_non_empty(role, "role")
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_technology_requirements(role, technology, bounded)


if __name__ == "__main__":
    mcp.run(transport="stdio")
