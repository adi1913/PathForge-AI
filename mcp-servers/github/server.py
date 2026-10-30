"""
GitHub MCP server.

Transport: stdio by default (see docs/architecture.md "MCP transport" —
this is the practical choice for local development today; switching to
Streamable HTTP for a containerized deployment later is a one-line change
to the `mcp.run(...)` call at the bottom of this file, nothing else).

Run standalone:
    python server.py

Provider selection:
    DEMO_MODE=true (default)  -> DemoGitHubProvider, zero credentials needed
    DEMO_MODE=false           -> LiveGitHubProvider (GITHUB_TOKEN optional —
                                  GitHub's public API works unauthenticated,
                                  just at a much lower rate limit)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # mcp-servers/ root

from mcp.server.mcpserver import MCPServer
from providers.base import GitHubProvider
from providers.demo import DemoGitHubProvider
from providers.live import LiveGitHubProvider
from schemas import (
    LanguageBreakdown,
    RepositoryDetails,
    RepositoryFileResult,
    RepositoryReadmeResult,
    RepositoryStructureResult,
    SearchRepositoriesResult,
)

from common import config
from common.errors import InvalidArgumentsError


def get_provider() -> GitHubProvider:
    if config.DEMO_MODE:
        return DemoGitHubProvider()
    return LiveGitHubProvider()


mcp = MCPServer(
    name="pathforge-github-mcp",
    instructions=(
        "Exposes evidence about a user's real development experience from GitHub: "
        "repositories, languages used, project structure, and READMEs. The agent "
        "should use these tools to ground claimed skills in actual code rather than "
        "trusting self-reported skill lists."
    ),
)


def _require_non_empty(value: str, field: str) -> str:
    if not value or not value.strip():
        raise InvalidArgumentsError(f"'{field}' must not be empty")
    return value.strip()


_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
# Only manifests/CI files the evaluator needs: root-level names and workflow files. Nothing else.
_ALLOWED_ROOT_FILES = frozenset(
    {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "Pipfile",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
)
_WORKFLOW_RE = re.compile(r"^\.github/workflows/[A-Za-z0-9._-]{1,100}\.ya?ml$")


def _require_repo_ref(value: str, field: str) -> str:
    value = _require_non_empty(value, field)
    if not _REPO_NAME_RE.match(value) or value in {".", ".."}:
        raise InvalidArgumentsError(f"'{field}' is not a valid GitHub name")
    return value


def _require_allowed_file(path: str) -> str:
    path = _require_non_empty(path, "path")
    if path not in _ALLOWED_ROOT_FILES and not _WORKFLOW_RE.match(path):
        raise InvalidArgumentsError(
            "'path' must be a known manifest/CI file (e.g. requirements.txt, pyproject.toml, package.json, "
            "Dockerfile, .github/workflows/<name>.yml)"
        )
    return path


@mcp.tool(
    description=(
        "Search public GitHub repositories to find implementation examples, learning "
        "projects, or reference architectures relevant to a requested technology, "
        "skill, or topic. Use this when you need evidence of how a technology is used "
        "in practice, or to find repositories to recommend as practice projects. "
        "Optionally filter by primary language or topic tag."
    )
)
async def search_github_repositories(
    query: str, language: str | None = None, topic: str | None = None, max_results: int | None = None
) -> SearchRepositoriesResult:
    query = _require_non_empty(query, "query")
    bounded = config.clamp_max_results(max_results)
    return await get_provider().search_repositories(query, language, topic, bounded)


@mcp.tool(
    description=(
        "Get normalized metadata for one specific GitHub repository (stars, forks, "
        "primary language, topics, description, license, open issue count). Use this "
        "when you already know the owner/repo (e.g. from a user's profile or a prior "
        "search) and need details to evaluate or describe that project."
    )
)
async def get_github_repository(owner: str, repo: str) -> RepositoryDetails:
    owner = _require_repo_ref(owner, "owner")
    repo = _require_repo_ref(repo, "repo")
    return await get_provider().get_repository(owner, repo)


@mcp.tool(
    description=(
        "Get the language breakdown (byte counts and percentages) for one GitHub "
        "repository. Use this to verify which languages a project actually uses — "
        "e.g. to confirm a claimed 'Python' skill is backed by a Python-majority repo, "
        "not a repo that merely contains one Python file."
    )
)
async def get_repository_languages(owner: str, repo: str) -> LanguageBreakdown:
    owner = _require_repo_ref(owner, "owner")
    repo = _require_repo_ref(repo, "repo")
    return await get_provider().get_repository_languages(owner, repo)


@mcp.tool(
    description=(
        "List the file/directory structure of a GitHub repository at a given path "
        "(defaults to the repository root). Use this to assess project organization "
        "and architecture, or to locate specific files (e.g. a requirements.txt or "
        "Dockerfile) before deciding whether to inspect them further. The result is "
        "bounded to a maximum number of entries and is not a full recursive tree."
    )
)
async def get_repository_structure(owner: str, repo: str, path: str | None = None) -> RepositoryStructureResult:
    owner = _require_repo_ref(owner, "owner")
    repo = _require_repo_ref(repo, "repo")
    return await get_provider().get_repository_structure(owner, repo, path or "")


@mcp.tool(
    description=(
        "Fetch the README content of a GitHub repository. Use this to understand what "
        "a project does, how it's structured, and what technologies it claims to use, "
        "when repository metadata alone isn't enough context. Content is bounded in "
        "length; a very long README will be truncated."
    )
)
async def get_repository_readme(owner: str, repo: str) -> RepositoryReadmeResult:
    owner = _require_repo_ref(owner, "owner")
    repo = _require_repo_ref(repo, "repo")
    return await get_provider().get_repository_readme(owner, repo)


@mcp.tool(
    description=(
        "Fetch the text of ONE allow-listed dependency or CI file from a GitHub repository: "
        "requirements.txt, pyproject.toml, package.json, Pipfile, go.mod, Cargo.toml, pom.xml, "
        "Dockerfile, docker-compose.yml/.yaml, or .github/workflows/<name>.yml. Use this after "
        "get_repository_structure shows the file exists, to see which libraries a project declares "
        "or whether it has CI. Arbitrary paths are rejected; content is bounded in length."
    )
)
async def get_repository_file(owner: str, repo: str, path: str) -> RepositoryFileResult:
    owner = _require_repo_ref(owner, "owner")
    repo = _require_repo_ref(repo, "repo")
    path = _require_allowed_file(path)
    return await get_provider().get_repository_file(owner, repo, path)


if __name__ == "__main__":
    mcp.run(transport="stdio")
