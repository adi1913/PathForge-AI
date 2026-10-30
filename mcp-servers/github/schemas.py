"""
Structured output models for every GitHub MCP tool.

Every response model carries `source: "demo" | "live"` so a caller (the
future agent, or a test) always knows whether a result is real GitHub
data or DEMO_MODE sample data — never ambiguous, never silently
pretended to be real. See docs/architecture.md "DEMO_MODE behavior".
"""
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["demo", "live"]


class RepositorySummary(BaseModel):
    """Normalized repository metadata — never the raw GitHub API payload."""

    name: str
    full_name: str
    description: str | None = None
    url: str
    stars: int
    forks: int
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class SearchRepositoriesResult(BaseModel):
    source: Source
    query: str
    total_count: int = Field(description="Total matches upstream reported, before truncation to max_results")
    results: list[RepositorySummary]


class RepositoryDetails(BaseModel):
    source: Source
    repository: RepositorySummary
    default_branch: str | None = None
    open_issues: int | None = None
    license: str | None = None
    is_fork: bool = False
    is_archived: bool = False


class LanguageBreakdown(BaseModel):
    source: Source
    owner: str
    repo: str
    languages_bytes: dict[str, int] = Field(description="Raw byte counts per language, as GitHub reports them")
    languages_percent: dict[str, float] = Field(description="Same data normalized to percentages, sums to ~100")


class StructureEntry(BaseModel):
    path: str
    entry_type: Literal["file", "dir"]
    size_bytes: int | None = None


class RepositoryStructureResult(BaseModel):
    source: Source
    owner: str
    repo: str
    path: str = Field(description="The path listed; '' means repository root")
    entries: list[StructureEntry]
    truncated: bool = Field(description="True if the real tree had more entries than max_tree_entries")


class RepositoryReadmeResult(BaseModel):
    source: Source
    owner: str
    repo: str
    content: str = Field(description="README text, bounded to max_readme_chars")
    truncated: bool = Field(description="True if the real README was longer than max_readme_chars")


class RepositoryFileResult(BaseModel):
    source: Source
    owner: str
    repo: str
    path: str
    content: str = Field(description="File text, bounded to max_file_chars")
    truncated: bool = Field(description="True if the real file was longer than max_file_chars")
