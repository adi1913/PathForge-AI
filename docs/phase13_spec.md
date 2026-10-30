# Delivery step 13 — Frontend dashboard (spec)

> Historical delivery spec (shipped as `pathforge-ai-phase13.zip`). In the canonical 13-phase plan this is **Phase 11
> (Frontend dashboard)**; canonical Phase 13 is documented in `docs/phase13_final_spec.md`. References below to numbered
> "later phases" use the old delivery numbering and were superseded: authentication and observability shipped as canonical
> Phase 12 (`docs/phase12_security_spec.md`).

Scope source: README "Development phases" item 13 (*Frontend dashboard*) and the project brief's stack
(Next.js + TypeScript + Tailwind + shadcn/ui, "full SaaS dashboard"). Nothing else (auth/observability, broader testing,
Docker polish and docs polish belonged to later phases) is in scope.

## Goals
A web UI in `apps/web` over the **existing** Phase 1–12 API, no backend behaviour changes:

| Page | Uses |
|---|---|
| `/` Overview | `/api/health`, roadmaps + progress, applications, assessment evidence, repositories |
| `/resume` | `POST /api/resume/analyze` (text or file) |
| `/jobs` | `POST /api/job-descriptions/analyze` → matched/weak/missing skills |
| `/roadmap` | list/generate/get, item progress PATCH, progress report, replan |
| `/applications` | list/create, status update, notes, readiness |
| `/github` | evaluate repository, repositories, evidence |
| `/assessments` | generate, attempt, submit, result (confidence + adaptation), evidence history |
| `/mentor` | sessions, messages, citations, missing context, created assessments |

## Decisions
1. **No authentication existed at this delivery step** (added later in canonical Phase 12). The API identifies callers by a caller-supplied `user_id`; the UI
   asks for it ("Active user" bar, kept in `localStorage`, validated by the API returning 404 for unknown ids) and
   says so in the UI. This is not access control. `scripts/seed.py` prints the demo user's id.
2. **Typed from the contract.** `apps/web/openapi.json` is a snapshot of `app.openapi()`;
   `src/lib/api-types.ts` is generated from it (`npm run gen:types`). A backend test fails if the snapshot is stale
   (`npm run gen:openapi`-equivalent command is documented).
3. **Honest labelling.** Demo mode is shown from `/api/health`; assessment source labels, grading notices
   (coding answers are rubric-only, never executed), mentor `answer_source`, `missing_context` and citations,
   GitHub `data_source` and limitations, and readiness disclaimers are rendered, not hidden.
4. **Answer keys.** The UI only consumes key-free schemas; nothing in the web app references answer keys.
5. **Errors.** One fetch wrapper turns non-2xx into `ApiError` (status + detail); every page shows loading,
   empty and error states. No secrets in the browser; only `NEXT_PUBLIC_API_URL`.
6. **UI kit.** shadcn/ui-style primitives (Button, Card, Badge, Input, Textarea, Select, Progress) written in
   `src/components/ui` (class-variance-authority + tailwind-merge), Tailwind v3, light/dark via CSS variables.
7. **No new backend endpoints**; the overview aggregates existing endpoints client-side.

## Acceptance
- `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` all pass.
- Unit tests: API client (query/multipart/error handling), user-id storage, status/format helpers, key
  components (answer rendering without keys, citation list, missing-context banner, readiness/progress views).
- Backend: OpenAPI snapshot drift test; full Phase 1–12 regression unchanged.
- Smoke: the built app serves `/` and every route returns 200 against a running demo API
  (limitation: no browser-level E2E was run unless stated in the README).

## Limitations
No authentication; no knowledge-graph/interview-prep views (not built in earlier phases); the overview is
client-side aggregation; no browser E2E suite at this step.
