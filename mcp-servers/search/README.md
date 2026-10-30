# Search MCP Server

Provides general web search, job-listing search, and role/technology
requirement lookups — current external information the agent needs
rather than relying on an LLM's static training data.

**Status: implemented (Phase 3).** Built on the official MCP SDK
(`MCPServer`).

## Run it

```bash
cd mcp-servers/search
python server.py          # stdio transport, DEMO_MODE=true by default
```

## Test it

```bash
cd mcp-servers/search
pytest -q       # 9 tests, all protocol-level or offline-mocked
```

## Tools

| Tool | Inputs |
|---|---|
| `web_search` | `query`, `max_results?` |
| `search_jobs` | `role`, `location?`, `remote?`, `max_results?` |
| `search_technology_requirements` | `role`, `technology?`, `max_results?` |

Every result includes `"source": "demo" | "live"`. Schemas: `schemas.py`.

## Provider architecture

```
providers/base.py   SearchProvider (ABC)
providers/demo.py    DemoSearchProvider — fixed AI Engineer / Data Analyst
                      job & requirement data, DEMO_MODE=true
providers/real.py    RealSearchProvider — generic HTTP-backed "BYO provider"
```

**On `RealSearchProvider`:** there is no single canonical search/job-board
API this project is tied to — that varies by deployment. Rather than
hardcode one vendor or fabricate results, `RealSearchProvider` implements
a documented generic HTTP contract (see its module docstring in
`providers/real.py`): point `SEARCH_PROVIDER_BASE_URL` at any backend
that implements matching `GET /search`, `GET /jobs`, and
`GET /technology-requirements` endpoints. If `SEARCH_PROVIDER_BASE_URL`
is unset when `DEMO_MODE=false`, the provider raises
`ProviderUnavailableError` with an actionable message — it never
silently returns fake data.

## DEMO_MODE behavior

- `DEMO_MODE=true` (default): fixed, deterministic job/requirement data
  for "AI Engineer" and "Data Analyst" roles, small and clearly labeled.
- `DEMO_MODE=false`: requires `SEARCH_PROVIDER_BASE_URL` (and
  `SEARCH_PROVIDER_API_KEY` if the backend needs bearer auth). Missing
  configuration is a clear error, not a silent demo fallback.

## Security

- `max_results` is server-side clamped regardless of caller input.
- No arbitrary-URL fetching — only the three fixed endpoint shapes above.
- API key, if configured, only goes in the outgoing `Authorization`
  header, never logged or echoed in an error.
