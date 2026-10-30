"""
Deterministic demo data for the Learning Resources MCP server. Small,
fixed catalog covering the AI Engineer skill path from the Phase 2 seed
data (docs/architecture.md skill graph), so a demo roadmap has real
resources to point at once Phase 8 builds the roadmap generator.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import (
    Difficulty,
    GetLearningResourceResult,
    LearningResourceItem,
    ResourceType,
    SearchLearningResourcesResult,
)

from providers.base import LearningResourceProvider

_CATALOG: list[LearningResourceItem] = [
    LearningResourceItem(
        id="demo-course-python-advanced",
        title="Advanced Python for Backend Engineers",
        description="Deep dive into Python typing, async/await, and API design with FastAPI.",
        url="https://example.com/courses/advanced-python",
        provider="Demo Academy",
        resource_type="course",
        difficulty="intermediate",
        skills=["python", "fastapi"],
        estimated_hours=12.0,
        quality_score=4.6,
    ),
    LearningResourceItem(
        id="demo-doc-rag-overview",
        title="Retrieval-Augmented Generation: Official Concepts Guide",
        description="Conceptual documentation covering chunking, embeddings, and retrieval strategies.",
        url="https://example.com/docs/rag-overview",
        provider="Demo Docs",
        resource_type="documentation",
        difficulty="intermediate",
        skills=["rag", "embeddings", "vector-databases"],
        estimated_hours=2.0,
        quality_score=4.8,
    ),
    LearningResourceItem(
        id="demo-tutorial-mcp-first-server",
        title="Build Your First MCP Server",
        description="Step-by-step tutorial building a minimal MCP server with the official SDK.",
        url="https://example.com/tutorials/first-mcp-server",
        provider="Demo Tutorials",
        resource_type="tutorial",
        difficulty="beginner",
        skills=["mcp", "python"],
        estimated_hours=3.0,
        quality_score=4.5,
    ),
    LearningResourceItem(
        id="demo-project-agent-toolkit",
        title="Practice Project: Build a Multi-Tool AI Agent",
        description="Hands-on project building an agent that selects between three tools based on user goals.",
        url="https://example.com/projects/multi-tool-agent",
        provider="Demo Projects",
        resource_type="project",
        difficulty="advanced",
        skills=["ai-agents", "mcp"],
        estimated_hours=8.0,
        quality_score=4.4,
    ),
    LearningResourceItem(
        id="demo-course-deep-learning-foundations",
        title="Deep Learning Foundations",
        description="Neural network fundamentals: backprop, optimization, and regularization from first principles.",
        url="https://example.com/courses/deep-learning-foundations",
        provider="Demo Academy",
        resource_type="course",
        difficulty="intermediate",
        skills=["deep-learning", "machine-learning"],
        estimated_hours=20.0,
        quality_score=4.7,
    ),
]
_CATALOG_BY_ID = {item.id: item for item in _CATALOG}


class DemoLearningResourceProvider(LearningResourceProvider):
    async def search_resources(
        self,
        query: str | None,
        skill: str | None,
        level: Difficulty | None,
        resource_type: ResourceType | None,
        max_results: int,
    ) -> SearchLearningResourcesResult:
        matches = list(_CATALOG)
        if query:
            q = query.lower()
            matches = [
                r for r in matches if q in r.title.lower() or q in r.description.lower()
            ] or matches
        if skill:
            matches = [r for r in matches if skill.lower() in [s.lower() for s in r.skills]] or matches
        if level:
            matches = [r for r in matches if r.difficulty == level] or matches
        if resource_type:
            matches = [r for r in matches if r.resource_type == resource_type] or matches

        return SearchLearningResourcesResult(
            source="demo",
            query=query,
            skill=skill,
            resource_type=resource_type,
            results=matches[:max_results],
        )

    async def get_resource(self, resource_id: str) -> GetLearningResourceResult:
        item = _CATALOG_BY_ID.get(resource_id)
        return GetLearningResourceResult(source="demo", resource=item, found=item is not None)
