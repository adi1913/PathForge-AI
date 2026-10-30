"""
Real-data GitHub provider. Talks to the GitHub REST API through
GitHubClient, normalizes every response into the shared schemas, and
bounds every list/text field per common/config.py limits before it ever
becomes a tool result.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # mcp-servers/ root, for `import common`

from client import GitHubClient
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

from common import config
from providers.base import GitHubProvider


def _to_summary(raw: dict) -> RepositorySummary:
    return RepositorySummary(
        name=raw.get("name", ""),
        full_name=raw.get("full_name", ""),
        description=raw.get("description"),
        url=raw.get("html_url", ""),
        stars=raw.get("stargazers_count", 0),
        forks=raw.get("forks_count", 0),
        language=raw.get("language"),
        topics=raw.get("topics", []) or [],
        updated_at=raw.get("updated_at"),
    )


class LiveGitHubProvider(GitHubProvider):
    def __init__(self, client: GitHubClient | None = None):
        self._client = client or GitHubClient()

    async def search_repositories(
        self, query: str, language: str | None, topic: str | None, max_results: int
    ) -> SearchRepositoriesResult:
        q = query
        if language:
            q += f" language:{language}"
        if topic:
            q += f" topic:{topic}"
        response = await self._client.get(
            "/search/repositories", params={"q": q, "per_page": max_results}
        )
        body = response.json()
        results = [_to_summary(item) for item in body.get("items", [])[:max_results]]
        return SearchRepositoriesResult(
            source="live", query=query, total_count=body.get("total_count", len(results)), results=results
        )

    async def get_repository(self, owner: str, repo: str) -> RepositoryDetails:
        response = await self._client.get(f"/repos/{owner}/{repo}")
        raw = response.json()
        license_info = raw.get("license") or {}
        return RepositoryDetails(
            source="live",
            repository=_to_summary(raw),
            default_branch=raw.get("default_branch"),
            open_issues=raw.get("open_issues_count"),
            license=license_info.get("spdx_id"),
            is_fork=bool(raw.get("fork", False)),
            is_archived=bool(raw.get("archived", False)),
        )

    async def get_repository_languages(self, owner: str, repo: str) -> LanguageBreakdown:
        response = await self._client.get(f"/repos/{owner}/{repo}/languages")
        bytes_map: dict[str, int] = response.json()
        total = sum(bytes_map.values()) or 1
        percent = {k: round(v / total * 100, 1) for k, v in bytes_map.items()}
        return LanguageBreakdown(
            source="live", owner=owner, repo=repo, languages_bytes=bytes_map, languages_percent=percent
        )

    async def get_repository_structure(
        self, owner: str, repo: str, path: str
    ) -> RepositoryStructureResult:
        response = await self._client.get(f"/repos/{owner}/{repo}/contents/{path}".rstrip("/"))
        raw = response.json()
        items = raw if isinstance(raw, list) else [raw]
        truncated = len(items) > config.MAX_TREE_ENTRIES
        bounded = items[: config.MAX_TREE_ENTRIES]
        entries = [
            StructureEntry(
                path=item.get("path", ""),
                entry_type="dir" if item.get("type") == "dir" else "file",
                size_bytes=item.get("size"),
            )
            for item in bounded
        ]
        return RepositoryStructureResult(
            source="live", owner=owner, repo=repo, path=path, entries=entries, truncated=truncated
        )

    async def get_repository_readme(self, owner: str, repo: str) -> RepositoryReadmeResult:
        text = await self._client.get_raw(f"/repos/{owner}/{repo}/readme")
        truncated = len(text) > config.MAX_README_CHARS
        bounded = text[: config.MAX_README_CHARS]
        return RepositoryReadmeResult(
            source="live", owner=owner, repo=repo, content=bounded, truncated=truncated
        )

    async def get_repository_file(self, owner: str, repo: str, path: str) -> RepositoryFileResult:
        text = await self._client.get_raw(f"/repos/{owner}/{repo}/contents/{path}")
        truncated = len(text) > config.MAX_FILE_CHARS
        return RepositoryFileResult(
            source="live",
            owner=owner,
            repo=repo,
            path=path,
            content=text[: config.MAX_FILE_CHARS],
            truncated=truncated,
        )
