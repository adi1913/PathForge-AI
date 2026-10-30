"""Gathers observable facts about a public repository by calling the GitHub MCP server through
the MCP client. Bounded (<= MAX_TOOL_CALLS), never touches GitHub directly, and turns every failure
into either a recorded limitation (optional parts) or a fixed-message RepoEvalError (required parts)."""

import logging
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.agent.errors import MCPConnectionError, ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from app.agent.mcp_client import MCPClientManager
from app.repo_evidence.errors import (
    GitHubMCPUnavailableError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
    RepositoryNotFoundError,
)
from app.repo_evidence.manifests import PARSERS, UNPARSED
from app.repo_evidence.mcp_models import (
    FileResult,
    LanguagesResult,
    ReadmeResult,
    RepoDetailsResult,
    StructureResult,
)

logger = logging.getLogger("pathforge.repo_evidence")

MAX_TOOL_CALLS = 12
MAX_MANIFESTS = 5
MAX_WORKFLOWS = 2
_MANIFEST_NAMES = (*PARSERS, *UNPARSED, "Dockerfile", "docker-compose.yml", "docker-compose.yaml")
_WORKFLOW_DIR = ".github/workflows"

T = TypeVar("T", bound=BaseModel)


class _Missing(Exception):
    """An optional resource does not exist (not an error for the evaluation)."""


@dataclass
class RepoSnapshot:
    details: RepoDetailsResult
    languages_bytes: dict[str, int] = field(default_factory=dict)
    readme: ReadmeResult | None = None
    root_entries: list[str] = field(default_factory=list)  # root-level names
    root_dirs: set[str] = field(default_factory=set)
    workflows: dict[str, str] = field(default_factory=dict)  # path -> content
    manifests: dict[str, str] = field(default_factory=dict)  # name -> content
    inspected: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    empty: bool = False
    tool_calls: int = 0


class RepositoryCollector:
    def __init__(self, manager: MCPClientManager):
        self._manager = manager
        self._calls = 0

    async def collect(self, owner: str, repo: str) -> RepoSnapshot:
        ref = {"owner": owner, "repo": repo}
        details = await self._call("get_github_repository", ref, RepoDetailsResult, required=True)
        snap = RepoSnapshot(details=details)
        snap.inspected.append("repository metadata")

        languages = await self._optional(snap, "languages", "get_repository_languages", ref, LanguagesResult)
        if languages is not None:
            snap.languages_bytes = {k: v for k, v in languages.languages_bytes.items() if v > 0}
            snap.inspected.append("language breakdown")

        readme = await self._optional(snap, "README", "get_repository_readme", ref, ReadmeResult)
        if readme is not None:
            snap.readme = readme
            snap.inspected.append("README")

        structure = await self._optional(snap, "root structure", "get_repository_structure", ref, StructureResult)
        if structure is not None:
            snap.inspected.append("root directory listing")
            snap.root_entries = [e.path for e in structure.entries]
            snap.root_dirs = {e.path for e in structure.entries if e.entry_type == "dir"}
            if structure.truncated:
                snap.limitations.append("The root directory listing was truncated; some files may be missing.")
        snap.empty = not snap.languages_bytes and not snap.root_entries
        if snap.empty:
            snap.limitations.append("The repository appears to be empty; no evidence could be derived.")
            snap.tool_calls = self._calls
            return snap

        if ".github" in snap.root_dirs:
            await self._collect_workflows(snap, ref)
        await self._collect_manifests(snap, ref)
        for name in UNPARSED:
            if name in snap.root_entries:
                snap.limitations.append(f"{name} was found but its dependencies are not parsed.")
        snap.tool_calls = self._calls
        return snap

    async def _collect_workflows(self, snap: RepoSnapshot, ref: dict) -> None:
        listing = await self._optional(
            snap, "CI workflow listing", "get_repository_structure", {**ref, "path": _WORKFLOW_DIR}, StructureResult
        )
        if listing is None:
            return
        paths = sorted(e.path for e in listing.entries if e.path.lower().endswith((".yml", ".yaml")))
        for path in paths[:MAX_WORKFLOWS]:
            file = await self._optional(snap, path, "get_repository_file", {**ref, "path": path}, FileResult)
            if file is not None:
                snap.workflows[path] = file.content
                snap.inspected.append(path)
        if len(paths) > MAX_WORKFLOWS:
            snap.limitations.append(f"Only the first {MAX_WORKFLOWS} CI workflow files were read.")

    async def _collect_manifests(self, snap: RepoSnapshot, ref: dict) -> None:
        present = [n for n in _MANIFEST_NAMES if n in snap.root_entries and n not in UNPARSED]
        for name in present[:MAX_MANIFESTS]:
            file = await self._optional(snap, name, "get_repository_file", {**ref, "path": name}, FileResult)
            if file is not None:
                snap.manifests[name] = file.content
                snap.inspected.append(name)
                if file.truncated:
                    snap.limitations.append(f"{name} was truncated; later entries were not read.")
        if len(present) > MAX_MANIFESTS:
            snap.limitations.append(f"Only the first {MAX_MANIFESTS} manifest files were read.")

    async def _optional(self, snap, label: str, tool: str, args: dict, model: type[T]) -> T | None:
        try:
            return await self._call(tool, args, model, required=False)
        except _Missing:
            snap.limitations.append(f"{label} was not found or is not available.")
        except GitHubUnavailableError:
            snap.limitations.append(f"{label} could not be read (unusable or malformed response).")
        return None

    async def _call(self, tool: str, args: dict, model: type[T], *, required: bool) -> T:
        if self._calls >= MAX_TOOL_CALLS:
            raise GitHubUnavailableError("Inspection call budget exhausted.")
        self._calls += 1
        try:
            result = await self._manager.call_tool(tool, args)
        except ToolNotFoundError as exc:
            raise GitHubMCPUnavailableError() from exc
        except (ToolTimeoutError, MCPConnectionError) as exc:
            logger.warning("GitHub MCP call failed: tool=%s type=%s", tool, type(exc).__name__)
            raise GitHubUnavailableError() from exc
        except ToolExecutionError as exc:
            message = exc.message.lower()
            if "rate limit" in message:
                raise GitHubRateLimitedError() from exc
            if "not found" in message:
                if required:
                    raise RepositoryNotFoundError() from exc
                raise _Missing from exc
            logger.warning("GitHub MCP tool error: tool=%s", tool)
            raise GitHubUnavailableError() from exc
        try:
            return model.model_validate(result.structured_content or {})
        except ValidationError as exc:
            logger.warning("Malformed GitHub MCP result: tool=%s", tool)
            raise GitHubUnavailableError() from exc
