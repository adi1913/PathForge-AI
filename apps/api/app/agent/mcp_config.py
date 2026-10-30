"""
Configuration for which MCP servers the agent connects to. This is
trusted application configuration ONLY — read from environment
variables at process startup, never influenced by a user request. That
boundary matters: letting user input reach a subprocess command/args
would be a command-injection vector.

Paths are computed relative to this repository's own layout
(apps/api/app/agent/mcp_config.py -> .../mcp-servers/<name>/server.py),
never a hardcoded machine-specific absolute path, so this works
unchanged on any checkout of the repo.
"""

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import get_settings

# apps/api/app/agent/mcp_config.py -> parents[4] is the repo root
# (mcp_config.py -> agent -> app -> api -> apps -> <repo root>)
_REPO_ROOT = Path(__file__).resolve().parents[4]
MCP_SERVERS_ROOT = _REPO_ROOT / "mcp-servers"

_SERVER_NAMES = ("github", "search", "learning-resources")


class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 20.0


def _env_key(name: str, suffix: str) -> str:
    return f"MCP_{name.upper().replace('-', '_')}_{suffix}"


def _server_config(name: str) -> MCPServerConfig:
    settings = get_settings()
    server_dir = MCP_SERVERS_ROOT / name

    # Default: spawn the server with the SAME interpreter running FastAPI.
    # apps/api's requirements.txt includes `mcp`, `httpx`, and `pydantic`
    # — exactly what every mcp-servers/*/server.py needs — so this works
    # with no separate venv required. Override via env var to point at a
    # different interpreter (e.g. a dedicated mcp-servers venv, or a
    # docker-compose service entrypoint) without touching this code.
    command = os.environ.get(_env_key(name, "COMMAND"), sys.executable)
    args_override = os.environ.get(_env_key(name, "ARGS"))
    args = args_override.split(",") if args_override else [str(server_dir / "server.py")]
    timeout = float(os.environ.get(_env_key(name, "TIMEOUT_SECONDS"), "20"))

    # Pass through only what the server needs: DEMO_MODE (mirrors this
    # app's own setting so the whole stack is demo/live consistently) and
    # a minimal PATH. Never pass through the full parent environment
    # wholesale — that would leak apps/api's DATABASE_URL, SECRET_KEY,
    # etc. into a child process that has no use for them.
    env = {
        "DEMO_MODE": "true" if settings.DEMO_MODE else "false",
        "PATH": os.environ.get("PATH", ""),
    }
    if name == "github" and not settings.DEMO_MODE:
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            env["GITHUB_TOKEN"] = github_token
    if name == "search" and not settings.DEMO_MODE:
        for key in ("SEARCH_PROVIDER_API_KEY", "SEARCH_PROVIDER_BASE_URL"):
            value = os.environ.get(key)
            if value:
                env[key] = value
    if name == "learning-resources" and not settings.DEMO_MODE:
        for key in ("LEARNING_PROVIDER_API_KEY", "LEARNING_PROVIDER_BASE_URL"):
            value = os.environ.get(key)
            if value:
                env[key] = value

    return MCPServerConfig(name=name, command=command, args=args, env=env, timeout_seconds=timeout)


def default_server_configs() -> list[MCPServerConfig]:
    return [_server_config(name) for name in _SERVER_NAMES]
