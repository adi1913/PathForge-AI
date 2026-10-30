# Phase 8 — Personalized Roadmap Generation (deterministic)

## Goal
Turn a user's open `SkillGap` rows (Phase 7) into an ordered, scheduled,
persisted learning roadmap: `Roadmap` + `RoadmapItem` rows (existing tables).

## Behaviour
1. **Input gaps:** the user's `SkillGap` rows with `status` in {open, in_progress}
   and `match_status` != matched; optionally restricted to one
   `source_job_description_id`.
2. **Foundations:** transitive prerequisites (Phase 2 skill graph) the user has
   no evidence for (no `UserSkill`, or level `none`) are added as *foundation*
   items (none -> beginner). Prerequisites the user already has are skipped.
3. **Ordering:** topological over the prerequisite graph. Among ready skills the
   highest *effective priority* goes first (own `priority_score`, or the highest
   priority of any dependent in the set, so a foundation of a top gap is not
   starved); ties break on slug. Fully deterministic.
4. **Estimate:** minutes per level step reached (beginner 480, intermediate 900,
   advanced 1500, expert 2400); a gap with no level shortfall (low-confidence
   match) gets a 120-minute evidence-building floor.
5. **Schedule:** weekly capacity = `hours_per_day` x 60 x
   `ROADMAP_STUDY_DAYS_PER_WEEK`. `week_number` is the week an item starts.
   Hours/day and deadline come from the request, else the user's `Profile`, else
   a 1h/day default with a warning. If the plan needs more days than the
   deadline, `fits_deadline=false` and a warning is returned; nothing is
   silently dropped.
6. **Resources:** up to 2 `LearningResource` catalog rows per skill (matching
   difficulty first, then shortest). Only DB rows are used; nothing is invented.
   Resource items are the means *within* a skill's time budget and are not added
   to the schedule total.
7. **Persistence:** new roadmap is `active`, `generated_by="rules"`; the user's
   previous draft/active roadmaps are archived. Item
   `prerequisite_item_ids` link skill items to their prerequisite items.

## API
- `POST /api/roadmaps/generate` — JSON `{user_id, target_role_id?, job_description_id?,
  hours_per_day?, duration_days?}` -> roadmap. 404 unknown user, 409 no open gaps,
  422 invalid input.
- `GET /api/roadmaps/{roadmap_id}` — roadmap with items (404 if missing).
- `GET /api/roadmaps?user_id=` — roadmap summaries, newest first.

## Data model
No migration. Reuses `roadmaps`, `roadmap_items`, `learning_resources`.
New setting: `ROADMAP_STUDY_DAYS_PER_WEEK` (default 5).

## Non-goals
Adaptive re-planning (Phase 9), assessments/quizzes, project generation,
MCP/web resource discovery, LLM calls, progress tracking, readiness score.

## Acceptance
- Prerequisites always precede dependents; same input -> identical output.
- Gaps, foundations, resources, scheduling, deadline warning, archive-on-regenerate
  and error cases are covered by unit, DB-service and HTTP tests.
- Phase 6/7 tests unchanged and green; ruff clean.
