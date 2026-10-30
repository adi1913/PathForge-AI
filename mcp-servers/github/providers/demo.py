"""
Deterministic demo data for the GitHub MCP server. Used whenever
DEMO_MODE=true (see common/config.py). Every response is structurally
identical to what LiveGitHubProvider returns — same schemas, same
fields — just fixed sample content, and every result is tagged
`source="demo"` so nothing pretends to be real.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import (
    LanguageBreakdown,
    RepositoryDetails,
    RepositoryFileResult,
    RepositoryReadmeResult,
    RepositoryStructureResult,
    RepositorySummary,
    SearchRepositoriesResult,
    StructureEntry,
)

from providers.base import GitHubProvider

# A small, fixed catalog — enough to exercise filtering logic without
# being a "huge fake dataset."
_DEMO_REPOSITORIES: list[RepositorySummary] = [
    RepositorySummary(
        name="rag-demo",
        full_name="octocat/rag-demo",
        description="A small retrieval-augmented generation example using FastAPI and pgvector.",
        url="https://github.com/octocat/rag-demo",
        stars=42,
        forks=6,
        language="Python",
        topics=["rag", "fastapi", "python", "vector-database"],
        updated_at="2026-06-01T00:00:00Z",
    ),
    RepositorySummary(
        name="mcp-agent-toolkit",
        full_name="octocat/mcp-agent-toolkit",
        description="Reference MCP servers and an agent orchestrator built on the official SDK.",
        url="https://github.com/octocat/mcp-agent-toolkit",
        stars=120,
        forks=18,
        language="Python",
        topics=["mcp", "agents", "python"],
        updated_at="2026-07-10T00:00:00Z",
    ),
    RepositorySummary(
        name="react-dashboard-starter",
        full_name="octocat/react-dashboard-starter",
        description="A TypeScript + Next.js starter for SaaS dashboards.",
        url="https://github.com/octocat/react-dashboard-starter",
        stars=310,
        forks=54,
        language="TypeScript",
        topics=["react", "nextjs", "dashboard"],
        updated_at="2026-05-20T00:00:00Z",
    ),
    RepositorySummary(
        name="ml-skill-gap-notebook",
        full_name="octocat/ml-skill-gap-notebook",
        description="Notebooks exploring skill-gap scoring with scikit-learn.",
        url="https://github.com/octocat/ml-skill-gap-notebook",
        stars=15,
        forks=2,
        language="Jupyter Notebook",
        topics=["machine-learning", "education"],
        updated_at="2026-04-02T00:00:00Z",
    ),
]

_DEMO_README = (
    "# Demo Repository\n\n"
    "This is deterministic DEMO_MODE content returned by PathForge AI's "
    "GitHub MCP server because DEMO_MODE=true (or no GITHUB_TOKEN is "
    "configured). It is not fetched from GitHub.\n\n"
    "## Features\n- Example feature one\n- Example feature two\n"
)

_DEMO_STRUCTURE: list[StructureEntry] = [
    StructureEntry(path="README.md", entry_type="file", size_bytes=512),
    StructureEntry(path="pyproject.toml", entry_type="file", size_bytes=210),
    StructureEntry(path="Dockerfile", entry_type="file", size_bytes=120),
    StructureEntry(path="LICENSE", entry_type="file", size_bytes=1070),
    StructureEntry(path=".github", entry_type="dir"),
    StructureEntry(path="app", entry_type="dir"),
    StructureEntry(path="app/main.py", entry_type="file", size_bytes=1024),
    StructureEntry(path="tests", entry_type="dir"),
]

# Fixed fixture files for the allow-listed get_repository_file tool. Demo only: these describe the
# fixture, never a real repository.
_DEMO_FILES: dict[str, str] = {
    "pyproject.toml": (
        "[project]\nname = \"demo\"\ndependencies = [\"fastapi>=0.110\", \"pydantic\", \"qdrant-client\"]\n"
    ),
    "requirements.txt": "fastapi>=0.110\npydantic\nqdrant-client\n",
    "Dockerfile": "FROM python:3.12-slim\nCOPY . /app\nCMD [\"uvicorn\", \"app.main:app\"]\n",
    ".github/workflows/ci.yml": "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
}


class DemoGitHubProvider(GitHubProvider):
    async def search_repositories(
        self, query: str, language: str | None, topic: str | None, max_results: int
    ) -> SearchRepositoriesResult:
        query_lower = query.lower()
        matches = [
            r
            for r in _DEMO_REPOSITORIES
            if query_lower in r.name.lower()
            or query_lower in (r.description or "").lower()
            or query_lower in r.topics
            or any(query_lower in t for t in r.topics)
        ]
        if not matches:
            # Deterministic fallback so a demo search never returns empty
            # and looks broken — mirrors "best effort" real search UX.
            matches = list(_DEMO_REPOSITORIES)
        if language:
            matches = [r for r in matches if (r.language or "").lower() == language.lower()] or matches
        if topic:
            matches = [r for r in matches if topic.lower() in r.topics] or matches

        limited = matches[:max_results]
        return SearchRepositoriesResult(
            source="demo", query=query, total_count=len(matches), results=limited
        )

    async def get_repository(self, owner: str, repo: str) -> RepositoryDetails:
        found = next((r for r in _DEMO_REPOSITORIES if r.name == repo), None)
        summary = found or RepositorySummary(
            name=repo,
            full_name=f"{owner}/{repo}",
            description="Demo repository details (not fetched from GitHub).",
            url=f"https://github.com/{owner}/{repo}",
            stars=7,
            forks=1,
            language="Python",
            topics=["demo"],
            updated_at="2026-01-01T00:00:00Z",
        )
        return RepositoryDetails(
            source="demo",
            repository=summary,
            default_branch="main",
            open_issues=3,
            license="MIT",
            is_fork=False,
            is_archived=False,
        )

    async def get_repository_languages(self, owner: str, repo: str) -> LanguageBreakdown:
        bytes_map = {"Python": 45000, "TypeScript": 12000, "Shell": 800}
        total = sum(bytes_map.values())
        percent = {k: round(v / total * 100, 1) for k, v in bytes_map.items()}
        return LanguageBreakdown(
            source="demo", owner=owner, repo=repo, languages_bytes=bytes_map, languages_percent=percent
        )

    async def get_repository_structure(
        self, owner: str, repo: str, path: str
    ) -> RepositoryStructureResult:
        entries = _DEMO_STRUCTURE
        if path:
            entries = [e for e in _DEMO_STRUCTURE if e.path.startswith(path)]
        return RepositoryStructureResult(
            source="demo", owner=owner, repo=repo, path=path, entries=entries, truncated=False
        )

    async def get_repository_readme(self, owner: str, repo: str) -> RepositoryReadmeResult:
        return RepositoryReadmeResult(
            source="demo", owner=owner, repo=repo, content=_DEMO_README, truncated=False
        )

    async def get_repository_file(self, owner: str, repo: str, path: str) -> RepositoryFileResult:
        from common.errors import UpstreamError

        content = _DEMO_FILES.get(path)
        if content is None:
            raise UpstreamError(f"GitHub resource not found: {path}")
        return RepositoryFileResult(
            source="demo", owner=owner, repo=repo, path=path, content=content, truncated=False
        )
