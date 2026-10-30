# PathForge AI — Agentic Career & Learning Platform

An MCP-first platform that turns "I know Python, I want to be an AI
Engineer in 4 months" into an evidence-grounded skill-gap analysis and an
adaptive, re-planning learning roadmap — built around an explicit
multi-node agent that calls out to MCP servers and a RAG pipeline rather
than a single chatbot prompt.

**Status: all 13 canonical phases complete** (final: Testing, Docker, Deployment & Documentation Polish). See
[Phases](#development-phases) below.

## Why MCP, specifically

The agent never talks to GitHub, a job-search API, or a learning-content
API directly. Each of those capabilities is exposed as a standardized
MCP server with a typed tool contract. The agent's job is to look at the
user's goal and current state, decide *which* tools it needs, call them
through the MCP client, and reason over the results — the same shape as
an agent using MCP against Google Drive or Slack in production. This is
what makes "the agent dynamically selects tools" true rather than
aspirational: swapping the GitHub server for a different provider, or
adding a fourth MCP server, requires no change to the agent's reasoning
code, only its tool registry.

## Architecture

```
Frontend (Next.js)
        |
        v
Backend API (FastAPI)
        |
        v
Agent Orchestrator (explicit graph, not one prompt)
        |
   +----+-------------------+
   |                        |
   v                        v
MCP Client               RAG Pipeline
   |                        |
   v                        v
MCP Servers            Vector DB (pgvector/Qdrant)
   |
   +----------------+----------------+
   v                v                v
GitHub MCP      Search MCP     Learning-Resource MCP
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui | Standard modern SaaS stack, added in Phase 13 |
| Backend | FastAPI + Pydantic + SQLAlchemy | Async-friendly, typed, minimal ceremony |
| Database | PostgreSQL (SQLite locally with zero setup) | Real FK/relational needs (roadmap graph, prerequisites) |
| Agent | Explicit graph of nodes (LangGraph-style), added Phase 4 | Auditable, testable stages instead of one giant prompt |
| RAG | pgvector by default, Qdrant optional | pgvector needs no extra service; Qdrant swap-in via provider interface |
| MCP | Official MCP SDK, 3 servers | Required by the project brief; see servers below |
| Infra | Docker Compose | One-command local spin-up |

## Repository structure

```
pathforge-ai/
├── apps/
│   ├── api/            # FastAPI backend
│   │   ├── app/
│   │   │   ├── models/    # SQLAlchemy 2.x models (Phase 2)
│   │   │   ├── schemas/   # Pydantic API schemas (agent.py added Phase 4)
│   │   │   ├── agent/     # orchestrator, MCP client, LLM providers (Phase 4)
│   │   │   ├── rag/       # parsers, chunker, embeddings, vector store, retrieval (Phase 5)
│   │   │   ├── resume/    # parsers, section detection, extraction, skill normalization (Phase 6)
│   │   │   ├── jobs/      # JD parsing, requirement classification, skill-gap engine (Phase 7)
│   │   │   ├── applications/  # job application tracking + readiness (Phase 10)
│   │   │   ├── roadmap/   # planner + services: roadmap generation (Phase 8), progress tracking + re-planning (Phase 9)
│   │   │   ├── db/        # Base, mixins, session/engine
│   │   │   ├── api/       # FastAPI routers (agent.py added Phase 4)
│   │   │   └── core/      # settings/config
│   │   ├── alembic/       # migrations (Phase 2)
│   │   ├── scripts/       # seed.py (Phase 2)
│   │   └── tests/
│   └── web/             # Next.js frontend (App Router, Tailwind, shadcn/ui-style components) — Phase 13
├── mcp-servers/
│   ├── common/            # shared DEMO_MODE config + secret-safe errors
│   ├── github/             # 5 tools, real GitHub REST API + demo provider
│   ├── search/             # 3 tools, BYO-backend real provider + demo provider
│   └── learning-resources/ # 4 tools, BYO-backend real provider + demo provider
├── agent/                # graph/nodes/tools/prompts/state — added Phase 4
├── rag/                  # ingestion/retrieval/embeddings — added Phase 5
├── docs/
├── .env.example
├── docker-compose.yml
└── README.md
```

## Development phases

The canonical plan has **exactly 13 phases**. Status: **all 13 phases complete** (Phase 13 is the final phase; there is no Phase 14).

| # | Canonical phase | Status |
|---|---|---|
| 1 | Architecture & repository setup | ✅ |
| 2 | Database & backend foundation | ✅ |
| 3 | MCP infrastructure | ✅ |
| 4 | AI agent | ✅ |
| 5 | RAG — ingestion, retrieval & reranking | ✅ |
| 6 | Resume & skill extraction | ✅ |
| 7 | Job description analysis & skill-gap engine | ✅ |
| 8 | Roadmap generation & adaptive re-planning | ✅ |
| 9 | GitHub project evaluator & skill evidence | ✅ |
| 10 | Mentor, assessments & job application tracking | ✅ |
| 11 | Frontend dashboard | ✅ |
| 12 | Observability, authentication & security | ✅ (see [docs/phase12_security_spec.md](docs/phase12_security_spec.md)) |
| 13 | Testing, Docker, deployment & documentation polish | ✅ (see [docs/phase13_final_spec.md](docs/phase13_final_spec.md)) |

### Delivery history

Work was delivered in numbered steps whose ZIP names, specs and migration messages predate the 13-phase
consolidation. They are kept unchanged; this table maps them to the canonical phases.

| Delivery step / ZIP | Content | Canonical phase |
|---|---|---|
| `pathforge-ai-phase6.zip` | Resume analyzer | 6 |
| step 7 | Job description + skill gap | 7 |
| step 8 | Roadmap generation | 8a |
| `pathforge-ai-phase9.zip` | Adaptive re-planning | 8b |
| `pathforge-ai-phase10.zip` | Job application tracking | 10a |
| `pathforge-ai-phase11.zip` | GitHub evaluator + skill evidence | 9 |
| `pathforge-ai-phase12.zip` (`docs/phase12_spec.md`) | Mentor + assessments | 10b |
| `pathforge-ai-phase13.zip` | Frontend dashboard | 11 |
| `pathforge-ai-phase12-security.zip` (`docs/phase12_security_spec.md`) | Observability, auth, security | 12 |
| `pathforge-ai-phase12-security-verified.zip` | Same, re-packaged with the browser smoke-test update | 12 |
| `pathforge-ai-final.zip` (`docs/phase13_final_spec.md`) | Testing, Docker, deployment, docs polish | 13 |

Each phase is implemented, tested, and explained before the next starts — see per-phase notes in `docs/`.

## Running locally (Phase 1–2 scope: API + database, no MCP/agent/frontend yet)

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env   # DEMO_MODE=true, SQLite — no keys needed
alembic upgrade head                # create the schema
python -m scripts.seed              # optional: AI Engineer skill graph + demo user
uvicorn app.main:app --reload
```

- API docs: http://localhost:8000/api/docs
- Health check: http://localhost:8000/api/health (now also reports DB connectivity)

Run tests:

```bash
cd apps/api
pytest -q
```

Run lint:

```bash
cd apps/api
ruff check app scripts alembic/env.py
```

## Running the MCP servers (Phase 3 scope)

Separate venv from the API (these are standalone processes — see
`docs/architecture.md` "MCP client contract"):

```bash
cd mcp-servers
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd github                 # or search, or learning-resources
python server.py          # stdio transport, DEMO_MODE=true by default
```

Run all tests (32 total, no live network calls):

```bash
cd mcp-servers
for d in github search learning-resources; do (cd "$d" && pytest -q); done
```

Run lint:

```bash
cd mcp-servers
ruff check .
```

## Running the agent (Phase 4 scope)

The agent lives in `apps/api` and needs the MCP servers on disk in the
same checkout (`../../mcp-servers` relative to `apps/api`) — no separate
install needed there since `apps/api/requirements.txt` already includes
`mcp`, `httpx`, and `pydantic`, everything `mcp-servers/*/server.py`
needs. Starting the API spawns all three MCP servers automatically:

```bash
cd apps/api
uvicorn app.main:app --reload   # DEMO_MODE=true — no API keys needed
```

Example request:

```bash
curl -X POST http://localhost:8000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"user_request": "Find good RAG projects on GitHub"}'
```

Example response shape:

```json
{
  "answer": "Here's what I found:\n- search_github_repositories: 1 result(s) found, e.g. 'rag-demo'",
  "sources": [{"tool": "search_github_repositories", "server": "github", "data": {"...": "..."}}],
  "tools_used": [{"tool_name": "search_github_repositories", "server_name": "github", "success": true, "reason": "..."}],
  "confidence": "high",
  "follow_up_questions": [],
  "errors": [],
  "status": "completed"
}
```

For a real (non-demo) LLM instead of the deterministic demo planner, set
`DEMO_MODE=false`, `LLM_PROVIDER=anthropic`, and `LLM_API_KEY` — untested
live in this project's own environment so far (no key configured here);
see `docs/architecture.md` "known limitations".

## Running RAG (Phase 5 scope)

No extra setup needed for local/demo use — the vector store defaults to
Qdrant's embedded local mode (on-disk at `./qdrant_data`, no server
required). To use a real Qdrant server instead (e.g. for persistence you
can inspect), start it and point `QDRANT_URL` at it:

```bash
docker compose up qdrant -d
# then set QDRANT_URL=http://localhost:6333 in .env
```

Ingest a document:

```bash
curl -X POST http://localhost:8000/api/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Retrieval-Augmented Generation",
    "content": "# RAG\n\nRAG grounds LLM answers in retrieved documents.\n\n## Embeddings\n\nEmbeddings turn text into vectors.",
    "source": "manual-entry",
    "document_type": "markdown",
    "metadata": {"skill": "rag"}
  }'
```

Search it:

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "What are embeddings?", "top_k": 3, "filters": {"skill": "rag"}}'
```

Run RAG tests only:

```bash
cd apps/api
pytest tests/test_rag -q   # 46 tests, all offline (no live embedding/vector-db API calls)
```

For a real (non-demo) embedding provider, set `DEMO_MODE=false`,
`EMBEDDING_PROVIDER=openai`, and `EMBEDDING_API_KEY` — untested live in
this project's own environment so far; see `docs/architecture.md`
"known limitations".

## Running the resume analyzer (Phase 6 scope)

Supported formats: plain text, Markdown, PDF (text-layer only — no OCR;
a scanned-image PDF returns a clear warning, not a fabricated result).

Analyze resume text directly (no file needed):

```bash
curl -X POST http://localhost:8000/api/resume/analyze \
  -F "text=Jane Smith
jane@example.com

SKILLS
Python, SQL, FastAPI

PROJECTS
RAG Chatbot
Built a RAG chatbot using FastAPI." \
  -F "user_id=<optional-existing-user-id>"
```

Or upload a file:

```bash
curl -X POST http://localhost:8000/api/resume/analyze \
  -F "file=@resume.pdf" \
  -F "user_id=<optional-existing-user-id>"
```

`user_id` is optional — omit it to see the extracted analysis without
persisting `UserSkill` rows to any account.

DEMO_MODE (default) uses pure rule-based extraction — regex/heuristics
over the resume's own text, no LLM call, deterministic for a given
input. Every skill claim distinguishes how it was found (explicit
mention vs. demonstrated in a project vs. used in work experience) and
is scored conservatively — a skill only listed once, nowhere else,
stays "beginner."

Run resume tests only:

```bash
cd apps/api
pytest tests/test_resume -q   # 50 tests, all offline (no live LLM calls)
```

## Running the job description analyzer (Phase 7 scope)

Supported inputs: plain text and Markdown (`.txt`, `.md`). PDF is not
supported yet and returns a clear 400.

```bash
curl -X POST http://localhost:8000/api/job-descriptions/analyze \
  -F "text=AI Engineer at Initech

REQUIREMENTS
- Strong experience with Python
- RAG

PREFERRED QUALIFICATIONS
- MCP" \
  -F "user_id=<existing-user-id>"
```

`user_id` is optional. Without it the JD is parsed and its requirements
are returned, but the gap comparison is skipped (`overall_match_score` is
`null`). Skills not in the catalog are returned in `unmatched_skills`
and never inserted. All gap numbers (status, severity, priority, match
score) are deterministic — the LLM, in real mode, only extracts. Phase 7
does **not** generate a learning roadmap (that is Phase 8).

```bash
cd apps/api
pytest tests/test_jobs -q   # 89 tests, all offline
```

## Running roadmap generation (Phase 8 scope)

A roadmap is built from a user's open skill gaps, so analyze a job
description for that user first (see Phase 7), then:

```bash
curl -X POST http://localhost:8000/api/roadmaps/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<existing-user-id>", "hours_per_day": 2, "duration_days": 120}'

curl http://localhost:8000/api/roadmaps/<roadmap-id>
curl "http://localhost:8000/api/roadmaps?user_id=<existing-user-id>"
```

Optional body fields: `target_role_id`, `job_description_id` (plan only
that JD's gaps). `hours_per_day` / `duration_days` fall back to the user's
`Profile`, then to a 1h/day default with a warning. Errors: 404 unknown
user, 409 no open gaps, 422 invalid input.

Everything is deterministic rules — no LLM call. Missing prerequisites are
added as foundation items, items are topologically ordered (highest
priority first among ready skills), effort is estimated per level step,
and `week_number` is derived from weekly capacity
(`hours_per_day x 60 x ROADMAP_STUDY_DAYS_PER_WEEK`). If the plan needs
more days than the deadline, `fits_deadline` is `false` with a warning;
nothing is dropped. Resources come only from the `learning_resources`
table. Generating again archives the previous roadmap.

## Running the web app (Phase 13 scope)

Spec: `docs/phase13_spec.md`. Code: `apps/web` (Next.js 15 App Router, React 19, TypeScript, Tailwind 3, shadcn/ui-style
components in `src/components/ui`). It only calls the existing API; there are no new backend endpoints.

```bash
# 1. API (demo mode, no credentials) + a demo user
cd apps/api && .venv/bin/alembic upgrade head && PYTHONPATH=. .venv/bin/python scripts/seed.py   # prints the demo user id
.venv/bin/uvicorn app.main:app --port 8000
# 2. Web app
cd apps/web && npm install && npm run dev        # http://localhost:3000  (NEXT_PUBLIC_API_URL defaults to http://localhost:8000/api)
```

Paste the user id into the **Active user id** bar. **There is no sign-in yet**: the API trusts the caller-supplied
`user_id`, so this is not access control (authentication arrives in the Phase 12 security delivery); the UI says so on every page.

| Page | What it shows |
|---|---|
| Overview | mode (demo/live), roadmap progress, applications by status, recent assessment evidence |
| Resume / Job analysis | text or file upload; skills with evidence; gap table with reasoning |
| Roadmap | generate, per-item status, progress, re-plan, recent activity |
| Applications | tracking, status changes, notes, read-only readiness with stale/disclaimer notices |
| GitHub evidence | bounded repo inspection, `data_source` label, limitations |
| Assessments | key-free questions, rubric-only coding notice, result with confidence change, adaptation and evidence history |
| Mentor | chat with citations, missing-context disclosure and answer source |

Quality gates (from `apps/web`): `npm run typecheck`, `npm run lint`, `npm test` (vitest), `npm run build`.
The typed client comes from `apps/web/openapi.json`; after changing the API run
`.venv/bin/python scripts/export_openapi.py` (apps/api) then `npm run gen:types` (apps/web). A backend test
(`tests/test_web_contract.py`) fails if the snapshot is stale or exposes answer-key fields.
`apps/web/scripts/smoke_browser.py` is a manual Playwright smoke test of the full UI against running servers;
it is not part of the automated suites (no browser E2E suite until Phase 13). It registers a fresh account through
the UI (no user id argument) and covers register, login, sign-out, wrong password, tampered-token redirect and every
dashboard page; usage: `python3 apps/web/scripts/smoke_browser.py`. Each run registers a new account, so many runs in
quick succession hit the registration throttle (429); restart the API to reset it.

Limitations: no knowledge-graph or interview-prep views (not built in earlier phases);
the overview aggregates existing endpoints client-side; the UI was exercised against the demo API only, not a live
LLM/GitHub/search backend.

## Running assessments + the mentor (Phase 12 scope)

Spec: `docs/phase12_spec.md`. All endpoints take a caller-supplied `user_id`; **there is no real authentication
yet**, so the ownership checks (foreign/unknown ids return 404) are consistency checks, not access control (Phase 12 security delivery).

```bash
# generate a key-free quiz (demo bank without credentials; clearly labelled), attempt it, submit
curl -s -X POST localhost:8000/api/assessments/generate -H 'content-type: application/json' \
  -d '{"user_id":"<id>","skill_slug":"rag","assessment_type":"quiz","question_count":5}'
curl -s -X POST localhost:8000/api/assessments/<assessment_id>/attempts -H 'content-type: application/json' -d '{"user_id":"<id>"}'
curl -s -X POST localhost:8000/api/assessments/attempts/<attempt_id>/submit -H 'content-type: application/json' \
  -d '{"user_id":"<id>","answers":[{"question_id":"<qid>","answer":"B"}]}'
curl -s 'localhost:8000/api/assessments/evidence?user_id=<id>&skill=rag'
# mentor
curl -s -X POST localhost:8000/api/mentor/sessions -H 'content-type: application/json' -d '{"user_id":"<id>"}'
curl -s -X POST localhost:8000/api/mentor/sessions/<sid>/messages -H 'content-type: application/json' \
  -d '{"user_id":"<id>","message":"Explain RAG"}'
```

Endpoints: `POST /assessments/generate`, `GET /assessments`, `GET /assessments/evidence`, `GET /assessments/{id}`,
`POST /assessments/{id}/attempts`, `POST /assessments/attempts/{attempt_id}/submit`, `POST|GET /mentor/sessions`,
`GET /mentor/sessions/{id}`, `POST /mentor/sessions/{id}/messages`.

- Answer keys and rubrics are never returned by any endpoint (tested, including an OpenAPI schema walk).
- MCQ is exact-match; short answers use a keyword rubric; coding answers use a text rubric only — **code is never
  executed, parsed or security/quality-analysed** and the response says so (`executed: false`).
- Confidence rules (`p12.v1`): strong ≥85 → +0.10, passed 60–85 → +0.03, weak <60 → −0.05 (−0.10 below 40);
  coding-only ×0.5; fewer than 3 questions → no change; retakes of the identical question set → no change;
  cumulative net adjustment capped at ±0.30. `UserSkill.level`/`source` are never changed.
- Resume re-analysis keeps assessment evidence; confidence = new resume confidence + ledger net adjustment.
- Strong result: halves the roadmap item's estimate once and skips beginner resources; weak result adds missing
  prerequisites, one revision item and one exercises item, then re-plans. Passed results change nothing.
- Mentor: deterministic intents; RAG citations only from retrieved chunks above `MENTOR_RAG_MIN_SCORE`; missing
  knowledge base / roadmap / skills are disclosed in `missing_context`. Demo mode answers by rules and says so.
- Limitations: demo bank covers 8 skills; rubric grading is keyword-based and can misjudge valid answers;
  live LLM generation/mentor paths are tested with fakes only, not against a live provider.

## Running the GitHub repository evaluator (Phase 11 scope)

Inspects a **public** repository and records *evidence* for catalog skills. It is
not a code-quality, security or proficiency grade: only repository metadata, the
README, the root directory listing and a few allow-listed manifest/CI files are
read (at most 12 GitHub MCP calls), and every evidence row states what it does not
prove. Evidence is stored separately from `user_skills`; **nothing here changes a
skill level**. As with Phases 9-10, `user_id` is caller-supplied (no auth yet).

```bash
curl -X POST http://localhost:8000/api/github/evaluate -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "repository_url": "https://github.com/<owner>/<repo>"}'
curl "http://localhost:8000/api/github/repositories?user_id=<user-id>"
curl "http://localhost:8000/api/github/evaluations/<evaluation-id>?user_id=<user-id>"
curl "http://localhost:8000/api/github/evidence?user_id=<user-id>&skill=fastapi"
```

All GitHub access goes through the GitHub MCP server (the API never calls GitHub or imports
the server). With `DEMO_MODE=true` the results come from fixture data and are labelled
`data_source: demo`. With `DEMO_MODE=false` the server calls the real GitHub REST API:
set `GITHUB_TOKEN` (optional; read by the MCP server process, never returned or logged) to
raise GitHub's rate limit; the live path is implemented and unit-tested with mocked HTTP but
has **not been run against live GitHub** in this build. Errors: 404 unknown/private repo,
429 rate limited, 502 GitHub unreachable or unusable data, 503 GitHub MCP server unavailable,
422 bad URL (only `github.com/<owner>/<repo>` or `<owner>/<repo>`). Application readiness
(`/api/applications/{id}/readiness`) lists matching repository evidence per skill without
changing the Phase 7 score. One migration adds `repository_evaluations` and `skill_evidence`.
Details: `docs/phase11_spec.md`.

```bash
cd apps/api && pytest tests/test_repo_evidence -q        # 52 tests, offline
cd mcp-servers/github && pytest -q                       # 28 tests
```

## Running job application tracking (Phase 10 scope)

All endpoints take `user_id`. **(Pre-Phase-12 note — superseded; every route now requires a token and the id must match it, see Phase 12 below.)** `user_id` is
caller-supplied, so the ownership checks (another user's application or an
unknown id -> 404) separate well-behaved clients only and are not access
control. Real auth was added in the Phase 12 security delivery (see below).

```bash
# link to an analyzed job description (title/company default from it) or give job_title
curl -X POST http://localhost:8000/api/applications -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "job_description_id": "<jd-id>"}'

curl -X PATCH http://localhost:8000/api/applications/<app-id>/status -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "status": "interview", "scheduled_at": "2030-01-01T10:00:00Z"}'

curl "http://localhost:8000/api/applications?user_id=<user-id>&status=applied&limit=20&offset=0"
curl "http://localhost:8000/api/applications/<app-id>?user_id=<user-id>"      # detail + activity history
curl "http://localhost:8000/api/applications/<app-id>/readiness?user_id=<user-id>"
```

Statuses: `interested`, `preparing`, `applied`, `assessment`, `interview`,
`offer`, `rejected`, `withdrawn` (the last two are final). Illegal moves return
409, bad input 422. Readiness reuses the Phase 7 gap engine on the linked job
description vs your current skills, labels each skill `measured` / `estimated` /
`none`, flags outdated stored gaps, and is an internal indicator, **not** a
hiring probability. It never changes your skill levels. One migration adds
`job_applications` and `application_events`. Details: `docs/phase10_spec.md`.

```bash
cd apps/api
pytest tests/test_applications -q   # 41 tests, all offline
```

## Running progress tracking + re-planning (Phase 9 scope)

All three endpoints take `user_id`; another user's roadmap (or an unknown
id) returns 404.

```bash
# update one item: not_started | in_progress | completed | blocked | skipped
curl -X PATCH http://localhost:8000/api/roadmaps/<roadmap-id>/items/<item-id>/progress \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "status": "in_progress", "completion_percentage": 40}'

curl "http://localhost:8000/api/roadmaps/<roadmap-id>/progress?user_id=<user-id>"

# re-plan the remaining work in place (new daily time and/or deadline)
curl -X POST http://localhost:8000/api/roadmaps/<roadmap-id>/replan \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "hours_per_day": 3, "duration_days": 90}'
```

Invalid state transitions return 409, invalid input 422. Re-planning keeps
completed/skipped items as they are, recomputes remaining effort from
progress and the user's current `UserSkill` levels, keeps prerequisites
first, schedules blocked work (and what depends on it) last, and reports
`fits_deadline` with a warning instead of dropping anything. Completing an
item never changes a `UserSkill` — mastery needs its own evidence. No LLM;
no migration. Details: `docs/phase9_spec.md`.

```bash
cd apps/api
pytest tests/test_roadmap -q   # 106 tests, all offline
```

```bash
cd apps/api
pytest tests/test_roadmap -q   # 43 tests, all offline
```

Docker and deployment are covered in [Setup, testing, Docker & deployment](#setup-testing-docker--deployment-phase-13-scope).

## Setup, testing, Docker & deployment (Phase 13 scope)

Spec: [docs/phase13_final_spec.md](docs/phase13_final_spec.md). Phase 13 adds no product features; it verifies and
documents the whole system and fixes deployment defects found by that audit.

### Prerequisites
Python 3.12+ (3.13 works locally), Node 20+, and optionally Docker with the Compose plugin. Playwright + Chromium are
needed only for the browser smoke test. No external service is required in demo mode.

### Local development
```bash
cp .env.example .env                                     # local defaults; DEMO_MODE=true needs no keys
cd apps/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                           # create/upgrade the SQLite database
PYTHONPATH=. .venv/bin/python scripts/seed.py            # optional: demo skill graph + demo@pathforge.ai (demo-only password)
.venv/bin/uvicorn app.main:app --reload --port 8000      # API docs: http://localhost:8000/docs
cd ../web && npm ci && npm run dev                       # http://localhost:3000 (register an account on /login)
```
`psycopg2-binary` (PostgreSQL driver) may fail to build on very new Python versions; it is not needed for SQLite.

### Running the tests
```bash
cd apps/api && .venv/bin/python -m pytest -q             # API: ~590 tests, all offline (a full run takes ~6 minutes)
for d in github search learning-resources; do (cd mcp-servers/$d && ../../apps/api/.venv/bin/python -m pytest -q); done
cd apps/api && .venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts
cd apps/api && .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head && .venv/bin/alembic check
cd apps/web && npm run typecheck && npm run lint && npm test && npm run build
python3 apps/web/scripts/smoke_browser.py                # needs API (:8000, DEMO_MODE=true) + built web app (:3000) running
```
`tests/test_security/test_journey.py` is the single end-to-end journey: register, login, resume, job analysis,
roadmap, progress, re-plan, GitHub evidence, assessment, mentor and application tracking with real authentication,
ending with a check that another user sees none of it.

### Docker
```bash
cp .env.example .env     # then set SECRET_KEY (python -c "import secrets; print(secrets.token_urlsafe(48))") and POSTGRES_PASSWORD
docker compose up --build                                  # db + qdrant + api (migrations run on start) + web
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build   # developer hot reload, published db/qdrant ports
```
- The default stack is production-like: `ENVIRONMENT=production`, `AUTH_REQUIRED=true`, `DEBUG=false`, no bind mounts,
  Postgres and Qdrant are **not** published to the host, `docker compose` refuses to start without `SECRET_KEY` and
  `POSTGRES_PASSWORD`, and the API refuses to start with a default/short key.
- Both images are built from the **repository root** (`apps/api/Dockerfile`, `apps/web/Dockerfile`); the API image keeps
  the repo layout so the stdio MCP servers resolve at `../../mcp-servers`. The API image runs as a non-root user and
  `docker-entrypoint.sh` runs `python -m alembic upgrade head` before starting (`RUN_MIGRATIONS=false` to skip).
- `NEXT_PUBLIC_API_URL` is compiled into the web bundle (the URL the **browser** uses for the API); `CORS_ORIGINS` must
  contain the web origin.
- Verification status of this configuration is in "Release verification" below.

### Production requirements
1. HTTPS in front of both services (reverse proxy); forward the real client address (login throttling keys on it).
2. `ENVIRONMENT=production`, strong `SECRET_KEY`, `AUTH_REQUIRED=true`, `DEBUG=false` (startup refuses anything else).
3. `DEMO_MODE=false` plus real `LLM_API_KEY`/provider settings only when you want live data; otherwise leave demo mode on
   (all demo data is labelled as such).
4. Set `METRICS_TOKEN` to expose `/api/metrics` (it is off in production without one); scrape with a bearer token.
5. Decide on `ALLOW_REGISTRATION` (open by default) and list admins in `ADMIN_EMAILS` (only they may call `/api/rag/ingest`).
6. Back up the `pathforge_pgdata` and `pathforge_qdrant_data` volumes. Run a single API replica unless you accept
   per-process login throttling and metrics.

### Authentication and admin setup
Register at `/login` (or `POST /api/auth/register`). To make someone an admin add their email to `ADMIN_EMAILS`
(JSON list, e.g. `["you@example.com"]`) and restart the API; the account must still be registered normally. There is no
password reset or email verification and tokens cannot be revoked before they expire (default 8 hours).

### Health, readiness and metrics
`GET /api/health` (liveness + mode), `GET /api/health/ready` (200 when the database answers, else 503; reports vector
store and MCP connection counts), `GET /api/metrics` (Prometheus text; bearer `METRICS_TOKEN` when set). Every response
carries `X-Request-ID`; logs are redacted and can be JSON (`LOG_FORMAT=json`).

### Troubleshooting
| Symptom | Cause / fix |
|---|---|
| API exits at start with "Unsafe configuration for production" | Set a random `SECRET_KEY` (>= 32 chars), `AUTH_REQUIRED=true`, `DEBUG=false`. |
| `docker compose` says a variable is missing | Set `SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`. |
| Browser shows "Failed to fetch"/CORS errors | Add the web origin to `CORS_ORIGINS`; rebuild web if `NEXT_PUBLIC_API_URL` changed. |
| 401 everywhere after a while | Token expired (`ACCESS_TOKEN_EXPIRE_MINUTES`); sign in again. |
| 429 on login/register | Throttle; wait for `Retry-After` or restart the API (in-memory counters). |
| `/api/metrics` returns 404/401 | Disabled in production without `METRICS_TOKEN`, or the bearer token is missing/wrong. |
| `/api/health/ready` is 503 | Database unreachable; check `DATABASE_URL` and that migrations ran. |
| Agent tools unavailable / `mcp_servers_connected` is 0 | MCP servers could not start; check the API log and that `mcp-servers/` sits two levels above `apps/api`. |
| `pip install` fails on psycopg2-binary | Use Python 3.12, or skip it when using SQLite. |
| Smoke test hits 429 | Each run registers a new account; restart the API to reset the in-memory throttle. |

### Release verification

Results of the final run on the delivered source (authoring sandbox, Python 3.13, Node 20). Anything not listed as passed was
not verified.

| Check | Result |
|---|---|
| API test suite | **PASSED** — 591 passed |
| MCP suites (github / search / learning-resources) | **PASSED** — 28 / 9 / 9 |
| Ruff check + format check (`app`, `tests`, `scripts`, `alembic/env.py`) | **PASSED** |
| Alembic upgrade → downgrade base → upgrade, `alembic check` — SQLite | **PASSED** |
| Alembic upgrade → downgrade base → upgrade, `alembic check` — PostgreSQL 16 (local server, not Docker) | **PASSED** |
| Web typecheck, lint, 44 unit tests, production build (incl. `output: "standalone"`) | **PASSED** |
| Browser smoke test (register / login / sign-out / tampered token / all pages), 5 consecutive runs | **PASSED** — 30 checks, 0 problems each |
| Standalone web server (`node server.js` + static assets) | **PASSED** |
| Full-journey API test with real auth (`tests/test_security/test_journey.py`) | **PASSED** |
| PostgreSQL persistence: journey over HTTP, server restart, data still present | **PASSED** |
| Image-layout simulation (`/srv/pathforge/...`): entrypoint migration, production settings, MCP servers over stdio, auth, metrics token, unsafe-setting refusal | **PASSED** |
| `docker compose config` (default and dev override); required-secret enforcement | **PASSED** |
| `docker build` of the api/web images, `docker compose up` | **BLOCKED — NOT RUN**: the sandbox cannot pull base images (Docker Hub returned 403), so the Dockerfiles and the running stack are unverified; the checks above exercise the same layout, entrypoint and settings without a container |

Two fixes came from this pass: a PostgreSQL-only false drift report from `alembic check` (association tables declare both a
primary key and an identical unique constraint; `alembic/env.py` now ignores a unique constraint that duplicates its table's
primary key, while real drift is still detected), and the deployment defects listed in `docs/phase13_final_spec.md`.

### Known limitations
JWTs are not revocable and the throttle/metrics are per process; open registration, no email verification or password
reset; admin is an allow-list; demo mode uses deterministic fixtures, and live-provider paths are tested with mocked HTTP
only; Docker images were not built in the authoring environment (see above); no CI pipeline or load testing.

## Authentication, observability & security (Phase 12 scope)

Spec: [docs/phase12_security_spec.md](docs/phase12_security_spec.md). Identity comes from a signed access token,
never from a caller-supplied `user_id`.

```bash
# register / login (public) -> {"access_token": "...", "token_type": "bearer", ...}
curl -X POST localhost:8000/api/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-long-passphrase","display_name":"You"}'
curl -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-long-passphrase"}'
curl localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"
```

- Passwords: scrypt with per-user salt; tokens: HS256 JWT (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 480).
- A `user_id` in any request must equal the token's user (else 403); foreign resource ids return 404.
  `/rag/ingest` is admin-only (`ADMIN_EMAILS`); `/rag/search` needs a login.
- Login/registration are throttled (429 + `Retry-After`). Staging/production refuse to start with a default or
  short `SECRET_KEY`, `AUTH_REQUIRED=false` or `DEBUG=true`.
- Observability: `X-Request-ID` on every response and log line, redacting log formatter (`LOG_LEVEL`,
  `LOG_FORMAT=text|json`), `GET /api/health`, `GET /api/health/ready` (503 if the database is down),
  `GET /api/metrics` (Prometheus text; `METRICS_ENABLED`, optional `METRICS_TOKEN`).
- Web app: `/login` (sign in / create account), token in `sessionStorage`, sign-out, expired sessions redirect to `/login`.
- Demo seed: `python scripts/seed.py` creates `demo@pathforge.ai` with a documented **demo-only** password
  (refuses `ENVIRONMENT=production`).
- `AUTH_REQUIRED=false` is a local/test-only trusted-caller mode (the earlier test suites run in it; the new
  `tests/test_security/` suite runs with auth on).
- Limits: JWTs are not revocable before expiry; throttle and metrics are per process; token in `sessionStorage`;
  admin by allow-list; open registration, no email verification or password reset.

## Demo mode

`DEMO_MODE=true` (the default) is what makes the project runnable with
zero API keys. Every MCP tool and the LLM/RAG layer route through a mock
provider that returns fixed, clearly-labeled (`"source": "mock"`) data
instead of calling a real external API. The agent workflow, tool
selection, and roadmap logic all still execute for real — only the
external data source is swapped.
