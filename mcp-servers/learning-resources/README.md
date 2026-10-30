# Learning Resources MCP Server

Supplies candidate courses, documentation, tutorials, and practice
projects for a skill or query, so roadmap recommendations (Phase 8) are
traceable to a real source rather than invented URLs.

**Status: implemented (Phase 3).** Built on the official MCP SDK
(`MCPServer`).

## Run it

```bash
cd mcp-servers/learning-resources
python server.py          # stdio transport, DEMO_MODE=true by default
```

## Test it

```bash
cd mcp-servers/learning-resources
pytest -q       # 9 tests, all protocol-level or offline-mocked
```

## Tools

| Tool | Inputs |
|---|---|
| `search_learning_resources` | `query?`, `skill?`, `level?`, `resource_type?`, `max_results?` |
| `get_learning_resource` | `resource_id` |
| `search_courses` | `query?`, `skill?`, `level?`, `max_results?` (pins `resource_type="course"`) |
| `search_documentation` | `query?`, `skill?`, `max_results?` (pins `resource_type="documentation"`) |

`search_courses`/`search_documentation` are thin wrappers over the same
`search_resources` provider method as `search_learning_resources` —
filtering logic lives in one place, not three. Schemas: `schemas.py`.

## Provider architecture

```
providers/base.py   LearningResourceProvider (ABC)
providers/demo.py    DemoLearningResourceProvider — 5-item fixed catalog
                      covering the AI Engineer skill path (Python, RAG,
                      MCP, AI Agents, Deep Learning), DEMO_MODE=true
providers/real.py    RealLearningResourceProvider — generic HTTP-backed
                      "BYO provider", same pattern as search/providers/real.py
```

## DEMO_MODE behavior

- `DEMO_MODE=true` (default): fixed 5-resource catalog, deterministic
  filtering by query/skill/level/resource_type.
- `DEMO_MODE=false`: requires `LEARNING_PROVIDER_BASE_URL` (and
  `LEARNING_PROVIDER_API_KEY` if needed). Missing configuration raises
  `ProviderUnavailableError` with an actionable message.

## Security

- `max_results` is server-side clamped regardless of caller input.
- No arbitrary-URL fetching — only the two fixed endpoint shapes
  documented in `providers/real.py`.
- API key, if configured, only goes in the outgoing `Authorization`
  header, never logged or echoed in an error.
