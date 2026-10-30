# Phase 10 — Job Application Tracking + Readiness Summary (deterministic)

## Goals
1. Track job applications through a validated status lifecycle with an append-only
   activity history.
2. Link an application to an already-analyzed `JobDescription` (no copying of JD data) and
   show a transparent readiness summary computed by the **existing Phase 7 gap engine**.

## Non-goals
Auth (see limitation), email/calendar sync, fetching job URLs, LLM calls, a new scorer,
writing to `UserSkill`/`SkillGap`/roadmaps, hiring-probability claims, frontend.

## Security limitation (unchanged from Phases 8–9)
There is no authentication. `user_id` is caller-supplied, so ownership checks only separate
well-behaved clients; they are **not** access control. Real auth arrives in Phase 13. Every
route requires `user_id`; an unknown application and another user's application both return 404.

## Data model (one migration, two new tables, no changes to existing tables)
`job_applications`: id, `user_id` FK users CASCADE, `job_description_id` FK job_descriptions
SET NULL (nullable), `target_role_id` FK target_roles SET NULL (nullable), `company`,
`job_title`, `status` (enum), `applied_on` (date, null until applied), `scheduled_at`
(datetime, next assessment/interview), `notes` (text), `created_at/updated_at`.
Unique `(user_id, job_description_id)` (NULLs allowed, so manual applications can repeat).
Indexes: user_id, (user_id, status), job_description_id, target_role_id.
`application_events` (append-only): id, `application_id` FK CASCADE, `event_type`
(`created|status_changed|note_added|details_updated`), `from_status`, `to_status`,
`note`, `occurred_at`. Index on (application_id, occurred_at).
JD title/company are *defaults* copied once into `job_title`/`company` only when not supplied;
requirements and skills always come from the linked JD.
Downgrade drops both tables.

## Status lifecycle
`interested`, `preparing`, `applied`, `assessment`, `interview`, `offer`, `rejected`, `withdrawn`.
Allowed: interested->{preparing, applied, withdrawn}; preparing->{interested, applied, withdrawn};
applied->{assessment, interview, offer, rejected, withdrawn}; assessment->{interview, offer, rejected,
withdrawn}; interview->{assessment, offer, rejected, withdrawn}; offer->{rejected, withdrawn};
`rejected` and `withdrawn` are terminal. Same-state or any other move -> 409.
Entering `applied` sets `applied_on` (request value, else today; future dates -> 422).
`scheduled_at` is accepted only with `assessment`/`interview` (else 422) and is cleared on
other transitions. Every change appends an event; repeated updates append repeated events.

## API (`/api/applications`)
- `POST /applications` `{user_id, job_description_id?, target_role_id?, company?, job_title?, notes?}`
  -> 201. Needs a JD or a `job_title`. JD must belong to the user (else 404); unknown role -> 404;
  duplicate JD link -> 409.
- `GET /applications?user_id=&status=&target_role_id=&limit=&offset=` (limit 1..100, default 50;
  ordered newest `updated_at`, then id) -> `{items, total}`.
- `GET /applications/{id}?user_id=` -> detail + events.
- `PATCH /applications/{id}/status` `{user_id, status, applied_on?, scheduled_at?, note?}`.
- `POST /applications/{id}/notes` `{user_id, note}` (appends event, updates `notes`).
- `GET /applications/{id}/readiness?user_id=`.

## Readiness (reuses `app.jobs.gap_engine`; read-only)
Computed live from the JD's stored `JobDescriptionSkill` rows vs the user's *current* `UserSkill`
using `classify_match`, `compute_severity`, `compute_priority_score`, `compute_overall_match_score`.
Nothing is written. Response states `status`: `computed` or `unavailable` (with `reason`: no linked JD /
JD deleted / JD has no matched skills). Includes counts, `overall_match_score`, ranked gaps with
reasoning, `unmatched_requirements` (listed, not scored), per-skill `data_kind`
(`measured` = assessment/project/github/mentor evidence, `estimated` = resume/manual,
`none` = no evidence), `jd_analyzed_at`, `skills_last_updated`, and
`persisted_gaps_may_be_stale` (user skills changed after the JD analysis, so stored `SkillGap`
rows/roadmaps may predate the numbers shown). Warnings cover: no skills on record, estimates only,
unmatched requirements. The disclaimer is always present: an internal skill-match indicator,
not a hiring probability. Includes the user's active roadmap's effort-weighted progress
(measured) when one exists. Proficiency is never modified.

## Tests / acceptance
Unit: transition table, readiness maths (reused engine). Service+DB: create/link/duplicate/
ownership, transitions, events persisted, rollback on invalid update, pagination/filter,
readiness unavailable/stale/estimate cases. HTTP e2e: JD analyze -> application -> readiness ->
status flow. Migration cycle + `alembic check` clean. Full API suite, 3 MCP suites, ruff clean.
