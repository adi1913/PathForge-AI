# Phase 9 — Progress Tracking + Adaptive Re-planning (deterministic)

## Goals
1. Let a user record progress on roadmap items (`not_started`, `in_progress`,
   `completed`, `blocked`, plus the existing `skipped`).
2. Re-plan the *remaining* work of a roadmap from that progress, the user's
   current `UserSkill` levels, revised daily study time and an optional revised
   deadline — in place, without erasing progress.

## Non-goals
New gaps / new skills entering the plan (run a JD analysis + generate a new
roadmap for that), assessments, mastery inference, LLM calls, resource discovery,
auth. **Completing a roadmap item never changes `UserSkill`** — the skill model
has no rule that makes "item completed" evidence of mastery, so proficiency only
changes through its own evidence paths (resume, manual, later assessments).

## Progress updates
Transitions (anything else -> 409): `not_started`->{in_progress, completed, blocked, skipped};
`in_progress`->{in_progress (percent update), completed, not_started, blocked, skipped};
`blocked`->{in_progress, not_started, skipped}; `skipped`->{not_started, in_progress};
`completed`->{in_progress} (reopen). Same-state is rejected except `in_progress`.
`completion_percentage`: `completed`=100, `not_started`/`blocked`/`skipped` keep or reset
to 0 for not_started; `in_progress` accepts 0<=p<100 (default: keep current); sending it
with any other status -> 422. Completing/starting an item whose prerequisite items are
not completed is allowed but returns a warning (prerequisites are advisory).
Every change appends a `ProgressEvent` (`previous_value`/`new_value` = status), which is
also the source of timestamps (`started_at` = first start, `completed_at` = latest
completion). When no skill item remains (all completed/skipped) the roadmap becomes
`completed`; reopening an item makes it `active` again. Archived roadmaps reject updates.

## Re-planning (in place, `POST /api/roadmaps/{id}/replan`)
1. Resolved items = skill items `completed` or `skipped`; they keep status, percentage and
   history and are excluded from scheduling. No remaining skill items -> 409.
2. Remaining effort per skill item = `min(estimated_minutes * (1 - pct/100),
   estimate(user_level_now -> target_level))`, where target is the user's `SkillGap.target_level`
   for that skill (foundations: beginner). So progress and a raised proficiency can only
   shrink the estimate. Stored `estimated_minutes` is left untouched (idempotent on repeat).
3. Order: Phase 8 topological ordering over item prerequisites (resolved prerequisites are
   satisfied); among ready items, `in_progress` first, then effective priority, then slug.
   Blocked items and everything that transitively depends on them are *stalled*: scheduled
   after all unblocked work (still prerequisite-ordered) and listed in a warning. Nothing is dropped.
4. Schedule: weekly capacity = hours/day x 60 x `ROADMAP_STUDY_DAYS_PER_WEEK`; hours/day from
   request, else `Profile`, else 1h with a warning. `week_number` for remaining items is
   relative to the re-plan (week 1 = now); resolved items keep their historical week.
   Deadline = request `duration_days` (days from now), else `Profile.target_duration_days`,
   else none. `fits_deadline` + warning when remaining days exceed it; nothing dropped.
5. Persist: remaining items get new `order_index`/`week_number`; resolved items are ordered
   first (original relative order); resource items follow their skill item. Same roadmap id,
   no new items. `roadmap.duration_days` = revised deadline when one was given.
   A `ROADMAP_REPLANNED` event records before/after week and order per item (history).
   Re-planning can be repeated; identical inputs give identical plans.

## API (all require `user_id`; unknown roadmap *or* another user's roadmap -> 404)
- `PATCH /api/roadmaps/{roadmap_id}/items/{item_id}/progress` `{user_id, status, completion_percentage?}`
- `GET /api/roadmaps/{roadmap_id}/progress?user_id=` -> counts, effort-weighted percent,
  per-item progress with timestamps, recent events.
- `POST /api/roadmaps/{roadmap_id}/replan` `{user_id, hours_per_day?, duration_days?}` -> roadmap
  + replan summary. Errors: 404, 409 (archived / nothing remaining), 422 (hours 0<h<=16,
  days 1..1825).
- Phase 8 routes and schemas are unchanged (`GET /roadmaps/{id}` summary now covers
  remaining work; identical for a roadmap with no progress).

## Data model
No migration. Adds `ProgressEventType.ITEM_BLOCKED` and `ITEM_PROGRESS_UPDATED` (stored as
VARCHAR(30), no DB constraint). Uses existing `roadmap_items`, `progress_events`.

## Acceptance
Tests cover: no/some/all completed, blocked prerequisite, feasible and infeasible deadline,
changed availability, proficiency change, repeated re-planning, invalid transitions/inputs,
cross-user access, persistence after reload, UserSkill untouched; Phase 6-8 tests unchanged.
