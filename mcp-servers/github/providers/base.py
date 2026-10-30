import sys
from abc import ABC, abstractmethod
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # github/ itself, for `import schemas`

from schemas import (
    LanguageBreakdown,
    RepositoryDetails,
    RepositoryFileResult,
    RepositoryReadmeResult,
    RepositoryStructureResult,
    SearchRepositoriesResult,
)


class GitHubProvider(ABC):
    """Everything the GitHub MCP server's tools need, independent of
    whether the answer comes from the real GitHub API or deterministic
    demo data. Tool functions in server.py depend only on this
    interface — swapping demo/live never touches tool definitions."""

    @abstractmethod
    async def search_repositories(
        self, query: str, language: str | None, topic: str | None, max_results: int
    ) -> SearchRepositoriesResult: ...

    @abstractmethod
    async def get_repository(self, owner: str, repo: str) -> RepositoryDetails: ...

    @abstractmethod
    async def get_repository_languages(self, owner: str, repo: str) -> LanguageBreakdown: ...

    @abstractmethod
    async def get_repository_structure(
        self, owner: str, repo: str, path: str
    ) -> RepositoryStructureResult: ...

    @abstractmethod
    async def get_repository_readme(self, owner: str, repo: str) -> RepositoryReadmeResult: ...

    @abstractmethod
    async def get_repository_file(self, owner: str, repo: str, path: str) -> RepositoryFileResult: ...
