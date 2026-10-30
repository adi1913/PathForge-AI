# Phase 11 — GitHub Repository Evaluator + Skill Evidence Engine (deterministic)

## Goals
1. Evaluate a **public** GitHub repository from observable facts and record which catalog skills it
   gives *evidence* for, with source, excerpt, confidence, limitations and timestamp.
2. Show that evidence next to the Phase 10 readiness report **without** changing the Phase 7 score.

## Non-goals
Auth, private repos, cloning/executing code, static analysis, scoring code quality/security/architecture,
LLM calls, changing `UserSkill`, a new readiness formula, writing to `Project`/`ProjectEvaluation`
(their 0-100 quality scores would claim more than a few inspected files can support), URL scraping.
(The older plan listed a "GitHub project evaluator" with quality scores; this phase deliberately
reports **signals and evidence**, not quality grades.)

## Boundary: everything goes through MCP
The API never imports `mcp-servers/*` and never calls GitHub itself. `RepositoryCollector` calls the
GitHub MCP server through `MCPClientManager.call_tool` and validates every result with its own
pydantic models. One new MCP tool is added to the GitHub server: `get_repository_file`
(allow-listed manifest/CI paths only, bounded, no arbitrary path). All repo tools now validate
`owner`/`repo` against GitHub's name charset (blocks path traversal into the API URL).

## Inspection plan (bounded, <= 12 tool calls)
metadata (required) -> languages -> README -> root structure -> `.github/workflows` listing (if
present) -> up to 5 allow-listed manifests present at root (`requirements.txt`, `pyproject.toml`,
`package.json`, `Pipfile`, `go.mod`, `Cargo.toml`, `pom.xml`, `Dockerfile`, `docker-compose.yml`,
`docker-compose.yaml`) -> up to 2 workflow files. Only the **root** tree is listed, README is
truncated by the server, so signals are "observed in the inspected files", never "absent from the repo"
beyond that scope. Optional parts that fail (README missing, structure error, malformed manifest) become
limitations; only metadata failure aborts.

## Data model (one migration)
- `github_repositories` (existing, reused): add unique `(user_id, github_url)`; `github_url` is the
  canonical `https://github.com/{owner}/{repo}` (owner/repo as returned by GitHub's `full_name`
  casing-insensitively matched via lowercase key). Duplicate submissions reuse the row.
- `repository_evaluations` (new, history kept): id, repository_id FK CASCADE, user_id FK CASCADE,
  `data_source` (`demo`|`live`), `evaluated_at`, `signals` JSON, `languages` JSON, `inspected` JSON,
  `limitations` JSON, `unmatched_technologies` JSON.
- `skill_evidence` (new): id, evaluation_id FK CASCADE, repository_id FK CASCADE, user_id FK CASCADE,
  skill_id FK skills CASCADE, `evidence_type`, `excerpt` (<= 300 chars), `confidence`, `limitations`,
  `data_source`, `evaluated_at`. Unique `(evaluation_id, skill_id, evidence_type)`; index `(user_id, skill_id)`.
Evidence is stored **separately** from `user_skills`. Nothing here writes `UserSkill` or `SkillGap`.

## Evidence rules (deterministic; confidence is per evidence row, capped at 0.7)
| type | rule | confidence |
|---|---|---|
| `dependency_manifest` | name declared in a parsed manifest | 0.50 |
| `language_share` | language >= 10% of bytes: 0.35; >= 40%: 0.45 | 0.35 / 0.45 |
| `infrastructure_file` | Dockerfile/compose -> Docker; CI workflow -> catalog skill `ci-cd` if present | 0.50 |
| `readme_mention` | whole-word vocabulary mention in README | 0.20 |
Per skill the response also shows an aggregate = min(0.7, max row + 0.05 x (distinct types - 1)).
Technology names resolve through the existing `SkillNormalizer`; unknown names go to
`unmatched_technologies` and no skill row is ever created. Demo-mode evidence is labelled
`data_source: demo` and describes fixture data, not the user's repo.
Every evidence row's limitation states what the type does not prove (e.g. a declared dependency is not
proof it is used well; byte share is not proficiency; a README mention is a claim).

## Signals (facts, no grades)
`has_readme`, `readme_chars`, `readme_truncated`, `has_license`, `has_tests`, `has_ci`, `has_dockerfile`,
`manifests_found`, `is_fork`, `is_archived`, `empty_repository`, `stars` (context only).
`has_tests` = root entry named `tests|test|__tests__|spec` or a root file matching `test_*`/`*.test.*`/`*_test.*`.

## API (`/api/github`)
- `POST /evaluate` `{user_id, repository_url}` -> evaluation (signals, languages, evidence grouped by
  skill, unmatched technologies, limitations, `reused_repository`). URL must be `https://github.com/o/r`
  (optional `.git`/trailing slash/`www.`) or `o/r`; anything else 422.
- `GET /repositories?user_id=` -> repos + latest evaluation id/time.
- `GET /evaluations/{id}?user_id=` -> stored evaluation.
- `GET /evidence?user_id=&skill=` -> evidence from each repo's latest evaluation.
Errors: 404 user/evaluation unknown or foreign; 404 `repository_not_found` (also private repos);
429 rate limited; 502 GitHub unreachable/timeout/malformed metadata; 503 MCP GitHub server unavailable;
422 bad URL. Messages are fixed strings; upstream text and tokens are never echoed or logged.
No auth: `user_id` is caller-supplied (see Phase 9/10 limitation); ownership checks are not access control.

## Readiness integration
`ReadinessSkill` gains `github_evidence` (latest-evaluation rows for that skill: repo, type, confidence,
excerpt, limitations, data_source, evaluated_at). Scores, status, severity, counts are untouched.
A warning lists skills that have repository evidence but a missing/weak recorded level, stating that
repository evidence is not proficiency. Readiness stays read-only.

## Tests / acceptance
Unit: URL parsing, manifest parsing, evidence rules, signals. Service+DB: persistence, duplicates, history,
ownership, rate-limit/not-found/timeout/malformed/empty/unsupported-language handling via a fake MCP
manager, **UserSkill unchanged**. MCP server: new tool discovery, allow-list, traversal rejection, bounds.
HTTP e2e through the real demo GitHub MCP subprocess. Readiness integration + regression of Phases 6-10.
Migration cycle + `alembic check`; full API suite, 3 MCP suites, ruff clean.
