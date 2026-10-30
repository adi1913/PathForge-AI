# GitHub MCP Server

Exposes evidence about a user's real development experience from GitHub,
so the agent (Phase 4) can ground claimed skills in actual repository
content instead of trusting self-reported skill lists.

**Status: implemented (Phase 3).** Built on the official MCP Python SDK
(`mcp` package, `MCPServer` — the current SDK's name for what earlier
versions of the SDK called `FastMCP`; see `server.py`'s docstring).

## Run it

```bash
cd mcp-servers
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd github
python server.py          # stdio transport, DEMO_MODE=true by default
```

## Test it

```bash
cd mcp-servers/github
pytest -q
```

28 tests (Phase 3: 14; Phase 11 added 14 for `get_repository_file`, the allow-list and name validation): 8 protocol-level (real `mcp.Client` over in-memory transport —
tool discovery, demo-mode responses, `max_results` bounding, input
validation) + 6 offline HTTP-mocked tests of `GitHubClient`/
`LiveGitHubProvider` (normalization, 404 handling, rate-limit detection,
token-never-leaks, README truncation) via `httpx.MockTransport` — no
live network calls in the test suite.

## Tools

| Tool | Inputs | Notes |
|---|---|---|
| `search_github_repositories` | `query`, `language?`, `topic?`, `max_results?` | |
| `get_github_repository` | `owner`, `repo` | |
| `get_repository_languages` | `owner`, `repo` | Byte counts + normalized percentages |
| `get_repository_structure` | `owner`, `repo`, `path?` | Bounded to `MCP_MAX_TREE_ENTRIES` (default 200) |
| `get_repository_readme` | `owner`, `repo` | Bounded to `MCP_MAX_README_CHARS` (default 4000) |
| `get_repository_file` | `owner`, `repo`, `path` | Phase 11. Allow-listed manifest/CI paths only (`requirements.txt`, `pyproject.toml`, `package.json`, `Pipfile`, `go.mod`, `Cargo.toml`, `pom.xml`, `Dockerfile`, `docker-compose.y(a)ml`, `.github/workflows/<name>.y(a)ml`); anything else is rejected. Bounded to `MCP_MAX_FILE_CHARS` (default 20000) |

All repo tools validate `owner`/`repo` against GitHub's name charset (no path traversal into the API URL).

Every result includes `"source": "demo" | "live"` — never ambiguous
about whether data is real. Full input/output schemas: `schemas.py`.

## Provider architecture

```
providers/base.py    GitHubProvider (ABC)
providers/demo.py     DemoGitHubProvider   — fixed catalog, DEMO_MODE=true
providers/live.py     LiveGitHubProvider   — real GitHub REST API, via client.py
client.py              GitHubClient        — reusable HTTP client: auth, timeout,
                                              404/rate-limit/error handling
```

`server.py`'s tool functions depend only on the `GitHubProvider`
interface — swapping demo/live never touches a tool definition.

## DEMO_MODE behavior

- `DEMO_MODE=true` (default): `DemoGitHubProvider`, zero credentials, a
  small fixed catalog of ~4 sample repositories, deterministic filtering.
- `DEMO_MODE=false`: `LiveGitHubProvider`, calls the real GitHub REST
  API. `GITHUB_TOKEN` is optional — GitHub's public API works
  unauthenticated, just at a much lower rate limit. A rate-limit hit
  raises a clear `RateLimitedError` (with `retry_after_seconds` when
  GitHub reports a reset time), never a silent fallback to fake data.

## Security

- Token, if configured, only ever goes in the outgoing `Authorization`
  header — never logged, never in an exception message (tested).
- Every response is bounded: `max_results` is server-side clamped
  (`common/config.py`, default 10 / hard cap 25) regardless of what a
  caller asks for; README and repo-structure responses are truncated
  with a `truncated: true` flag rather than returned unbounded.
- No arbitrary-URL fetching tool exists — only the fixed GitHub REST
  endpoints above, called with a bounded timeout.
- 404s and other upstream errors are translated into clean messages;
  raw response bodies are never echoed back.

## Future MCP client contract (FastAPI side — not implemented yet)

See `docs/architecture.md` → "MCP client contract" for how the Phase 4
agent's MCP client is expected to connect to this server.
