# Phase 13 — Testing, Docker, Deployment & Documentation Polish (spec)

Canonical **Phase 13 of 13** — the final phase. Not to be confused with `docs/phase13_spec.md` (the earlier *frontend
dashboard* delivery, canonical Phase 11). No Phase 14 exists. Delivered as `pathforge-ai-final.zip`.

## Goals
No new product features. Verify, harden the deployment path, and document.
- A. Full regression: API, three MCP suites, frontend.
- B. One end-to-end journey with real authentication across every feature.
- C. Dockerfiles and Compose that actually match how the code locates its pieces.
- D. Migration, persistence and production-configuration checks.
- E. Health/readiness/metrics/log checks in production mode.
- F. Frontend production build (including the standalone build used by the web image) and browser smoke test.
- G. Setup, testing, Docker, deployment, security and troubleshooting documentation; release hygiene.

## Audit findings that required fixes
| Finding | Fix |
|---|---|
| API image copied only `apps/api`, but the agent resolves MCP servers as `<repo root>/mcp-servers` | Build from the repo root; image mirrors the repo layout (`/srv/pathforge/apps/api`, `/srv/pathforge/mcp-servers`) |
| Compose ran `--reload` on a bind mount, published Postgres/Qdrant ports, used a fixed DB password, no migrations, no web service | Production-like `docker-compose.yml` (required secrets, no published db/qdrant, `ENVIRONMENT=production`, web service); hot-reload moved to `docker-compose.dev.yml`; entrypoint runs migrations |
| Container ran as root | Non-root user |
| `alembic` command might not be on `PATH` | Entrypoint uses `python -m alembic` |
| `alembic/env.py` disabled existing loggers when run in-process | `disable_existing_loggers=False` (fixed in the Phase 12 delivery) |
| README Docker snippet misplaced and stale; stale "Phase 14–17" wording in `docs/phase13_spec.md` | Rewritten; wording reconciled to the 13-phase plan |
| No `.gitignore` | Added (env files, databases, venvs, node_modules, build output, vector data) |

## Non-goals
New features, new dependencies, changing security behaviour, a CI service, Kubernetes manifests, load testing.

## Test requirements
Existing tests are not weakened. New: `tests/test_security/test_journey.py` (full journey with auth on, plus an HTTP-level
regression for the documented rule that `completion_percentage` is only accepted with `in_progress`).

## Verification matrix (results are recorded in the README "Release verification" section only after they were run)
API suite · MCP suites ×3 · Ruff check/format · Alembic up/down/up + drift · web typecheck/lint/tests/build · browser smoke
(register/login flow) · `docker compose config` (default and dev) · image-layout simulation (entrypoint migration, production
settings, MCP over stdio, auth, metrics token, unsafe-setting refusal) · standalone web server start · `docker build` and
`docker compose up` (**require pulling base images from Docker Hub; blocked in the authoring sandbox, so reported as
BLOCKED unless they ran**) · PostgreSQL migration (**NOT RUN without a Postgres instance**).

## Acceptance criteria
1. Every check in the matrix is either run and passing or explicitly marked BLOCKED/NOT RUN with the reason.
2. Compose refuses to start without `SECRET_KEY`/`POSTGRES_PASSWORD`; the API refuses unsafe production settings.
3. The README documents prerequisites, env setup, migrations, local dev, tests, Docker, production requirements, auth/admin
   setup, health/metrics and troubleshooting; the 13-phase table is intact; no Phase 14 anywhere.
4. Earlier ZIPs unchanged (checksums); no secrets in the archive.
