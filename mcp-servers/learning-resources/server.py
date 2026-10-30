"""
Learning Resources MCP server. Transport: stdio (see docs/architecture.md).

Provider selection:
    DEMO_MODE=true (default) -> DemoLearningResourceProvider
    DEMO_MODE=false          -> RealLearningResourceProvider; raises
                                ProviderUnavailableError with an actionable
                                message if LEARNING_PROVIDER_BASE_URL isn't set
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer
from providers.base import LearningResourceProvider
from providers.demo import DemoLearningResourceProvider
from providers.real import RealLearningResourceProvider
from schemas import Difficulty, GetLearningResourceResult, ResourceType, SearchLearningResourcesResult

from common import config
from common.errors import InvalidArgumentsError


def get_provider() -> LearningResourceProvider:
    if config.DEMO_MODE:
        return DemoLearningResourceProvider()
    return RealLearningResourceProvider()


mcp = MCPServer(
    name="pathforge-learning-resources-mcp",
    instructions=(
        "Provides candidate courses, documentation, tutorials, and practice projects "
        "for a given skill or query. The agent should use these tools when building or "
        "updating a learning roadmap, so recommended resources are traceable to a real "
        "source rather than invented URLs."
    ),
)


def _require_non_empty(value: str, field: str) -> str:
    if not value or not value.strip():
        raise InvalidArgumentsError(f"'{field}' must not be empty")
    return value.strip()


@mcp.tool(
    description=(
        "Search learning resources of any type (course, documentation, tutorial, "
        "project, video, article) by free-text query, target skill, and/or difficulty "
        "level. Use this as the general-purpose resource search; use search_courses or "
        "search_documentation instead when specifically only a course or only "
        "documentation is wanted."
    )
)
async def search_learning_resources(
    query: str | None = None,
    skill: str | None = None,
    level: Difficulty | None = None,
    resource_type: ResourceType | None = None,
    max_results: int | None = None,
) -> SearchLearningResourcesResult:
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_resources(query, skill, level, resource_type, bounded)


@mcp.tool(
    description=(
        "Fetch full metadata for one specific learning resource by its id (as returned "
        "by search_learning_resources/search_courses/search_documentation). Use this "
        "when a roadmap item references a resource id and full details (URL, provider, "
        "estimated hours) are needed."
    )
)
async def get_learning_resource(resource_id: str) -> GetLearningResourceResult:
    resource_id = _require_non_empty(resource_id, "resource_id")
    return await get_provider().get_resource(resource_id)


@mcp.tool(
    description=(
        "Search specifically for structured courses (not tutorials or docs) covering a "
        "skill or topic. Use this when building a roadmap item that calls for a "
        "multi-lesson course rather than a single article or reference page."
    )
)
async def search_courses(
    query: str | None = None, skill: str | None = None, level: Difficulty | None = None, max_results: int | None = None
) -> SearchLearningResourcesResult:
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_resources(query, skill, level, "course", bounded)


@mcp.tool(
    description=(
        "Search specifically for official documentation pages covering a skill or "
        "technology. Use this when the agent needs an authoritative reference rather "
        "than a tutorial or course — e.g. to link a roadmap item to primary-source docs."
    )
)
async def search_documentation(
    query: str | None = None, skill: str | None = None, max_results: int | None = None
) -> SearchLearningResourcesResult:
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_resources(query, skill, None, "documentation", bounded)


if __name__ == "__main__":
    mcp.run(transport="stdio")
