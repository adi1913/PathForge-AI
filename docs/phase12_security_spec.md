# Phase 12 — Observability, Authentication & Security (spec)

Canonical plan: **Phase 12** of 13 (README "Development phases"). Not to be confused with `docs/phase12_spec.md`,
which is the earlier *assessments + mentor* delivery (canonical Phase 10b) and is unchanged. Delivered as
`pathforge-ai-phase12-security.zip`.

## 1. Inspection findings (what exists today)

| Area | Current behaviour |
|---|---|
| Identity | None. `users` has `email`, `password_hash`, `is_active`, but no code hashes or verifies passwords and no endpoint creates users. Every endpoint takes a caller-supplied `user_id` (query, JSON body or form field); `/agent/run` takes an optional one. |
| Ownership | Services scope by `user_id` and return 404 for unknown/foreign ids (roadmaps, applications, assessments, mentor, GitHub evaluations). That is consistency, not access control, because the caller chooses the `user_id`. `GET /roadmaps/{id}` has **no** `user_id` and no owner check. |
| Shared data | `/rag/ingest` and `/rag/search` use one knowledge base for everyone; the mentor cites from it. |
| Validation | Pydantic bounds, upload size/char limits, status-transition rules, answer-key boundary (all kept). Validation errors echo the submitted `input`. |
| Logging | Plain `logging.getLogger("pathforge.*")`; no central config, no request id, no redaction. MCP tool calls are persisted to `mcp_tool_logs` with sanitized metadata (kept). |
| Health | `GET /api/health` (status, mode, database_ok). No readiness, no metrics. |
| Config | `SECRET_KEY` defaults to `change-me-in-env`; CORS is `localhost:3000` only (kept). PyJWT is already installed (dependency of `mcp`). |
| Frontend (Phase 11) | Manual "Active user id" bar in `localStorage`; no Authorization header. |
| Migrations | Not needed: `users.password_hash`/`is_active` already exist; no new table or column. |

## 2. Requirements

### Authentication
- `POST /api/auth/register` (email, password, optional display name) → 201 with user + access token. Disabled by `ALLOW_REGISTRATION=false`.
- `POST /api/auth/login` → token. Generic `Invalid credentials` for unknown email, wrong password and inactive users; password work is performed for unknown emails to equalise timing.
- `GET /api/auth/me` → current user.
- Passwords: scrypt (stdlib, per-user random salt, parameters stored in the hash string), constant-time compare, 10–128 characters. Plaintext is never stored, returned or logged.
- Tokens: JWT HS256 (PyJWT) with `sub`, `iat`, `exp`, `iss`, `aud`, `jti`; short lifetime (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 480). Verified on every request, and the user is re-loaded and must still exist and be active.
- Login/registration throttling: failed logins per (client address, email) within a window → 429 + `Retry-After`; success clears the counter.

### Authorization and ownership
- Every API route requires a valid token except: `GET /health`, `GET /health/ready`, `POST /auth/register`, `POST /auth/login`, OpenAPI/docs, and `GET /metrics` (own token rule below).
- **Identity comes from the token.** A `user_id` in a query/body/form is only an assertion: if present it must equal the token's user (else 403); where optional it defaults to the token's user. A request can therefore never act for another user.
- `GET /roadmaps/{id}`: owner check (foreign == unknown → 404).
- All other user resources (resume/JD analyses, skills, gaps, roadmaps, applications, assessments/attempts/evidence, mentor sessions, GitHub repositories/evaluations/evidence) are already scoped by `user_id`; with the binding above they are scoped by the *authenticated* user. Foreign or unknown ids stay 404.
- Shared knowledge base: `/rag/search` requires login; `/rag/ingest` requires an admin (`ADMIN_EMAILS` allow-list) because ingested text is cited to every user.
- `AUTH_REQUIRED=false` is a **local/test-only** "trusted caller" mode that restores the old behaviour. Default is `true`; staging/production refuse to start with it off.

### Security hardening
- Startup validation: staging/production refuse a default/short (<32 chars) `SECRET_KEY`, `AUTH_REQUIRED=false`, `DEBUG=true`.
- Secrets (`SECRET_KEY`, `METRICS_TOKEN`, API keys) are `repr=False` and never appear in logs, health or errors. `.env.example` has placeholders only.
- Safe errors: unhandled exceptions → generic 500 + request id (no stack or exception text to clients); validation errors drop echoed `input`/`ctx`, so a submitted password is never reflected.
- Security headers on API responses: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, API-only CSP (not on `/docs`).
- CORS stays an explicit allow-list (localhost:3000 default, configurable); methods/headers narrowed to what the dashboard uses.
- Seed script hashes a documented **demo-only** password, and refuses to run in production.

### Observability
- Request id per request (`X-Request-ID`; inbound value accepted only if it matches `[A-Za-z0-9._-]{8,64}`), carried into every log line via a context variable and returned to the client.
- Central logging config: `LOG_LEVEL`, `LOG_FORMAT=text|json`. Redaction of `Authorization`/bearer values, JWTs, `password=`/`token=`/`secret=`/`api_key=` pairs and `sk-…` keys in messages and exception text.
- Access log per request: method, route *template*, status, duration, request id. Never query strings, bodies or headers.
- `GET /health` (unchanged shape) and `GET /health/ready`: 200 when the database answers, else 503; reports vector-store and MCP connection state without secrets.
- `GET /metrics`: Prometheus text exposition from an in-process registry (request count, latency histogram, in-flight gauge, auth events). Route labels are templates (bounded cardinality). Enabled by `METRICS_ENABLED` (default true locally); if `METRICS_TOKEN` is set it requires that bearer token; in production it is off unless a token is configured.
- No new external services or dependencies. Distributed tracing/OTel backends are out of scope; request-id correlation is the tracing mechanism.

### Frontend (Phase 11 dashboard)
- New `/login` page (sign in / create account), token kept in `sessionStorage`, `Authorization: Bearer` on every API call, sign-out button, current user in the header. The manual "Active user id" bar is removed; `user_id` values sent to the API come from `/auth/me`.
- A 401 clears the session and redirects to `/login` with a "session expired" message; 403/404/422/429 show their safe messages. All Phase 11 pages keep working.

## 3. Security boundaries and honest limits
- Stateless JWTs cannot be revoked before they expire (no refresh tokens, no server-side logout list). Sign-out only discards the token client-side.
- Throttling and metrics are per process (not shared across workers) and key on the client address the server sees; behind a proxy, forward the real address.
- Token in `sessionStorage` is readable by any XSS on the origin; the dashboard renders no untrusted HTML, but this is a trade-off versus httpOnly cookies (which would add CSRF handling).
- Admin = `ADMIN_EMAILS` allow-list, not a role table. Open registration unless disabled. No email verification or password reset.
- `AUTH_REQUIRED=false` mode exists for the ~490 earlier tests (see §5) and local experiments; it must not be used outside local/test.

## 4. Implementation plan
`app/security/` (`passwords`, `tokens`, `deps`, `throttle`, `validation`), `app/api/routes/auth.py`, `app/api/routes/ops.py`,
`app/observability/` (`context`, `logging`, `metrics`, `middleware`); router-level `Depends(get_current_user)` for every
protected router plus per-handler `auth.bind(user_id)`; config additions; seed update; frontend `lib/auth.ts`, `/login`,
header/user hook changes; OpenAPI snapshot + types regenerated.

## 5. Test modes
`AUTH_REQUIRED` defaults to true. The earlier HTTP tests send a bare `user_id`, so `tests/conftest.py` sets
`AUTH_REQUIRED=false` for them and they run **unchanged**. Enforcement is proven by `tests/test_security/` with auth on:
an unauthenticated sweep over every OpenAPI route, a cross-user sweep, foreign-resource checks, and real authenticated
runs of the assessment, mentor, roadmap, application, resume and GitHub flows.

## 6. Acceptance criteria
1. Register/login/me work; passwords are hashed (scrypt) and never returned/logged; inactive users cannot log in or use old tokens.
2. Missing/malformed/expired/wrong-audience/tampered tokens → 401 on every protected route (sweep covers all routes in OpenAPI).
3. Token for user A with `user_id` of user B → 403 everywhere a `user_id` is accepted; A cannot read/modify B's resources by id (404).
4. Non-admin `/rag/ingest` → 403; unauthenticated `/rag/search` → 401.
5. Login throttle returns 429 after the configured failures; correct login still works for other keys.
6. Logs redact passwords/tokens/keys; access log has no query strings; request id round-trips; unhandled error → generic 500.
7. `/health/ready` 503 when DB unavailable; `/metrics` honours token rules and exposes template labels only.
8. Startup validation rejects unsafe production settings.
9. Frontend: login, register, logout, expired-session redirect, Authorization header, API error handling tested; typecheck, lint, tests, build pass.
10. Earlier suites unchanged and green; MCP suites green; Ruff clean; migration upgrade/downgrade/upgrade and `alembic check` clean (no new migration).
