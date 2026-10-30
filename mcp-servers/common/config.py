"""
Shared configuration for every MCP server in this monorepo.

Deliberately reuses the exact DEMO_MODE philosophy from apps/api's
Settings (Phase 1/2) rather than inventing a second mocking system: when
DEMO_MODE is true, every server must be fully operable with zero external
credentials, returning deterministic data that is structurally identical
to what a real provider would return, clearly tagged as demo data.

This module has NO dependency on apps/api (MCP servers are standalone
processes/services — see docs/architecture.md "MCP client contract") and
reads its own environment directly.

Every setting is read live from `os.environ` on each access (via
module-level `__getattr__`, PEP 562) rather than frozen at import time.
This is deliberate, not just a testing convenience: `config.DEMO_MODE`
always reflects the environment at the moment a tool runs, so tests can
`monkeypatch.setenv(...)` per-test without import-order fragility, and a
long-running server process picks up config changes made before the
attribute is next read.
"""
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str) -> str | None:
    return os.environ.get(name) or None


_BOOL_SETTINGS = {"DEMO_MODE": ("DEMO_MODE", True)}
_STR_SETTINGS = {
    "GITHUB_TOKEN": "GITHUB_TOKEN",
    "SEARCH_PROVIDER_API_KEY": "SEARCH_PROVIDER_API_KEY",
    "SEARCH_PROVIDER_BASE_URL": "SEARCH_PROVIDER_BASE_URL",
    "LEARNING_PROVIDER_API_KEY": "LEARNING_PROVIDER_API_KEY",
    "LEARNING_PROVIDER_BASE_URL": "LEARNING_PROVIDER_BASE_URL",
}
_STR_WITH_DEFAULT_SETTINGS = {"GITHUB_API_BASE_URL": ("GITHUB_API_BASE_URL", "https://api.github.com")}
_INT_SETTINGS = {
    "DEFAULT_MAX_RESULTS": ("MCP_DEFAULT_MAX_RESULTS", 10),
    "HARD_MAX_RESULTS": ("MCP_HARD_MAX_RESULTS", 25),
    "MAX_README_CHARS": ("MCP_MAX_README_CHARS", 4000),
    "MAX_FILE_CHARS": ("MCP_MAX_FILE_CHARS", 20000),
    "MAX_TREE_ENTRIES": ("MCP_MAX_TREE_ENTRIES", 200),
    "HTTP_TIMEOUT_SECONDS_RAW": ("MCP_HTTP_TIMEOUT_SECONDS", 10),
}


def __getattr__(name: str):
    if name in _BOOL_SETTINGS:
        env_name, default = _BOOL_SETTINGS[name]
        return _env_bool(env_name, default)
    if name in _STR_SETTINGS:
        return _env_str(_STR_SETTINGS[name])
    if name in _STR_WITH_DEFAULT_SETTINGS:
        env_name, default = _STR_WITH_DEFAULT_SETTINGS[name]
        return os.environ.get(env_name, default)
    if name in _INT_SETTINGS:
        env_name, default = _INT_SETTINGS[name]
        return _env_int(env_name, default)
    if name == "HTTP_TIMEOUT_SECONDS":
        return float(__getattr__("HTTP_TIMEOUT_SECONDS_RAW"))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def clamp_max_results(requested: int | None) -> int:
    """Every tool that accepts max_results funnels it through here so no
    caller (agent or human) can ask for an unbounded result set."""
    if requested is None:
        return __getattr__("DEFAULT_MAX_RESULTS")
    return max(1, min(requested, __getattr__("HARD_MAX_RESULTS")))
