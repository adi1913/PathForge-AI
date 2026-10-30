"""The API's own validation models for GitHub MCP tool results. Deliberately not imported from
mcp-servers/: the MCP protocol is the boundary, and the shape is validated here, not trusted."""

from pydantic import BaseModel, ConfigDict, Field


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RepoSummaryResult(_Loose):
    name: str
    full_name: str
    description: str | None = None
    url: str = ""
    stars: int = 0
    language: str | None = None
    topics: list[str] = Field(default_factory=list)


class RepoDetailsResult(_Loose):
    source: str
    repository: RepoSummaryResult
    default_branch: str | None = None
    license: str | None = None
    is_fork: bool = False
    is_archived: bool = False


class LanguagesResult(_Loose):
    languages_bytes: dict[str, int] = Field(default_factory=dict)


class StructureEntryResult(_Loose):
    path: str
    entry_type: str


class StructureResult(_Loose):
    entries: list[StructureEntryResult] = Field(default_factory=list)
    truncated: bool = False


class ReadmeResult(_Loose):
    content: str = ""
    truncated: bool = False


class FileResult(_Loose):
    path: str
    content: str = ""
    truncated: bool = False
