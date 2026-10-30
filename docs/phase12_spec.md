# Phase 12 — Assessments + Contextual Mentor

Status: spec written before implementation. Scope is the original plan item "12. Mentor + assessments"; no
frontend, auth or new MCP servers.

## 1. Goals

1. Generate quizzes / short-answer / coding challenges per skill, store attempts, grade them **deterministically**.
2. Store every graded attempt as **separate, persistent evidence** (`assessment_evidence` ledger) that no other
   feature (notably resume re-analysis) can overwrite or erase.
3. Let assessment results move `UserSkill.confidence` only, by explicit rules. **Never** change `UserSkill.level`
   or `UserSkill.source`.
4. Feed results into the roadmap: strong → less beginner material; weak → prerequisites, revision, exercises;
   then re-plan with the Phase 9 `ReplanService`.
5. A contextual mentor that answers from the user's stored learning state + RAG, with citations and explicit
   missing-context disclosure.

## 2. Non-goals

- Executing, compiling or sandboxing submitted code. Coding answers are scored by a **text rubric only**.
- Claiming security, code-quality, correctness-by-test or complexity analysis of submitted code.
- Real authentication (Phase 13). `user_id` is caller-supplied everywhere; ownership checks are consistent
  data scoping, **not** access control.
- LLM-graded scoring. An LLM may *draft* questions in real mode; grading is always deterministic.
- Interview preparation, frontend, readiness-score changes (Phase 7/10 scorers are untouched).

## 3. Architecture

```
app/assessments/
  bank.py        deterministic demo question bank (clearly labelled), per skill slug
  generator.py   QuestionGenerator: BankGenerator (DEMO_MODE) / LLMGenerator (real, LLMProvider.generate_structured)
  grading.py     pure grading functions (MCQ exact, short-answer keyword rubric, coding text rubric)
  rules.py       pure outcome + confidence-update rules, RULES_VERSION
  service.py     AssessmentService: generate / fetch / start attempt / submit / history
  adaptation.py  AdaptationService: roadmap changes from an outcome, then ReplanService
  access.py      load_owned_assessment / load_owned_attempt (unknown == foreign -> 404)
  schemas.py     user-facing schemas (NO answer-key fields exist in any of them)
app/mentor/
  intent.py      deterministic intent classifier
  context.py     builds MentorContext from DB (skills, role, roadmap, progress, assessments) — never reads keys
  service.py     MentorService: sessions, messages, answer (rules in DEMO_MODE; LLM in real mode)
  access.py      load_owned_session
  schemas.py
api/routes/assessments.py, api/routes/mentor.py
```

Reused models: `Assessment`, `Question`, `AssessmentAttempt`, `AssessmentAnswer`, `MentorSession`,
`MentorMessage`, `ProgressEvent` (`ASSESSMENT_PASSED/FAILED`, `ITEM_SKIPPED`, `ITEM_PROGRESS_UPDATED`),
`RoadmapItem`. Reused services: `RAGService.search`, `ReplanService.replan`, `LLMProvider`.

### Data model (one migration, `phase_12_assessments_evidence`)

| Change | Why |
|---|---|
| `assessments.generation_source` VARCHAR(20) NOT NULL default `demo_bank` (`demo_bank` \| `llm`) | label demo vs LLM-drafted questions |
| `questions.order_index` INT NOT NULL default 0 (set 0..n-1 by the service) | deterministic question order |
| `assessment_answers.evaluation` JSON null | per-answer grading method + criteria counts |
| NEW `assessment_evidence` | the immutable evidence ledger (below) |

`assessment_evidence`: `id, user_id→users CASCADE, skill_id→skills CASCADE, assessment_id→SET NULL,
attempt_id→SET NULL (unique), attempt_number, score_percent, outcome (strong|passed|weak|insufficient),
assessment_type, question_count, evaluation_methods JSON, confidence_before, confidence_after,
confidence_delta_applied, confidence_note, rules_version, data_source (demo|llm), created_at`.
Nothing in the app updates or deletes ledger rows (append-only). Deleting an attempt/assessment keeps the row.

Answer keys live only in `questions.expected_answer` (MCQ option id) and `questions.evaluation_rubric` (JSON
text of criteria with keyword patterns). They are read only by `grading.py` and the generator.

## 4. Grading rules (deterministic; same input → same score)

All scores are fractions 0–1 per answer; attempt score = weighted mean × 100, 1 decimal.

| Type | Method | Rule |
|---|---|---|
| MULTIPLE_CHOICE | `mcq_exact` | option id equals key (case/space-insensitive) → 1 else 0. Unanswered → 0. Weight 1.0 |
| SHORT_ANSWER | `short_keyword_rubric` | rubric = criteria `{label, any_of[], weight}`. Criterion met if any pattern appears as a whole word/phrase (case-insensitive). Score = met weight / total weight. Answers < 5 words score 0. Correct if ≥ 0.7. Weight 1.0 |
| CODING | `coding_text_rubric` | same criterion mechanism on the submitted text (regex/keyword presence). **Code is never executed, imported, compiled or parsed.** Weight 0.5. Correct if ≥ 0.7 |

Every coding result carries `executed: false` and the notice: *"Your code was not executed. No tests were run
and no correctness, security, complexity or code-quality analysis was performed. This score only reflects
whether your text contains the elements the rubric looks for."* Short answers carry: *"Keyword rubric, not a
semantic judgement."* Keyword matching can be gamed; this is documented and is why coding weighs less and why
retakes never move confidence.

Feedback never includes the correct option, expected text, keywords or criteria labels — only
`correct/incorrect`, a score, and counts (`criteria_met` / `criteria_total`).

### Outcome (on the weighted attempt score)

| Score | Outcome |
|---|---|
| ≥ 85 | `strong` |
| 60 – <85 | `passed` |
| < 60 | `weak` |
| fewer than 3 questions | `insufficient` (stored, no confidence change, no roadmap change) |

## 5. Confidence-update rules (RULES_VERSION `p12.v1`)

Applied only on a **first completed attempt** of an assessment and only if a `UserSkill` row already exists.

1. raw delta: strong +0.10; passed +0.03; weak with score ≥ 40 → −0.05; weak with score < 40 → −0.10;
   insufficient 0.
2. If the assessment's questions are all CODING, raw delta × 0.5 (rubric-only evidence is weaker).
3. Cumulative net adjustment from assessments for one (user, skill) is bounded to ±0.30
   (`net = Σ confidence_delta_applied`). `allowed = clamp(net + raw, −0.30, +0.30) − net`.
4. `confidence_after = clamp(confidence_before + allowed, 0, 1)`; `delta_applied = after − before` (3 dp).
5. Retakes (2nd+ completed attempt of the same assessment) are stored in the ledger with delta 0 and note
   "retake — confidence not changed; generate a new assessment to re-measure".
6. No `UserSkill` row → ledger row stored, `confidence_note` says no level is recorded; nothing is created.
   (When a resume later creates the row, §6 applies the ledger.)
7. `current_level` and `source` are never written. UserSkill is touched only when the applied delta is non-zero; then an entry `{"type":"assessment", ...}` is appended to
   `UserSkill.evidence` (bounded: keep all non-assessment entries + the 5 newest assessment entries).

## 6. Evidence preservation vs. resume re-analysis

`ResumeAnalyzerService._persist_user_skills` today replaces `level/confidence/source/evidence`. Change (minimal):

- keep existing `evidence` entries whose `type == "assessment"` and append them to the new resume evidence;
- set `confidence = clamp(resume_confidence + net_assessment_adjustment)` where the net comes from the ledger
  (`Σ confidence_delta_applied` for that user+skill, clamped ±0.30);
- when it creates a **new** `UserSkill` row, apply the same net (so results recorded before the resume existed
  are not lost).

The ledger itself is never touched by resume code. Level and source continue to follow the Phase 6 rules.

## 7. Adaptive roadmap rules

Target: the roadmap that owns `assessment.roadmap_item_id`, else the user's ACTIVE roadmap with a SKILL item
for the assessed skill. Archived roadmap / no item → no change + explanation in the response.

| Outcome | Changes (each recorded as a `ProgressEvent` with `metadata.source = "assessment_adaptation"`) |
|---|---|
| strong | (a) once per item: skill item `estimated_minutes` → `max(120, round(×0.5))`; (b) NOT_STARTED beginner-difficulty resources of that skill → `SKIPPED` (reversible, Phase 9 allows SKIPPED→NOT_STARTED). The skill item is **not** completed or marked mastered. Time freed pulls dependent skills earlier when re-planned. |
| passed | no roadmap change |
| weak | (a) for each direct catalog prerequisite not already a SKILL item in the roadmap and with no `UserSkill` at ≥ beginner confidence ≥ 0.4: add `Foundation: Learn <X>` item; (b) add one `Revision: <skill>` item (LEARNING_RESOURCE, 60 min, no URL — not a real resource) and one `Practice exercises: <skill>` item (PROJECT, 90 min) attached to the skill item. Dedup by (skill, title prefix). Completed items stay completed. |

After changes, `ReplanService.replan(roadmap_id, ReplanRequest(user_id))` re-sequences (prerequisites first).
Replan failures (`NothingToReplan`, etc.) become warnings; the assessment result is **already committed**.
Limitation: revision/exercise items are not counted in the replan's schedule minutes (same as Phase 8 resource
items); foundations are skill items and are counted.

## 8. Mentor

`POST /mentor/sessions/{id}/messages` stores the user message, builds a `MentorContext`, answers, stores the
mentor message with metadata `{intent, citations, missing_context, answer_source}`.

Context (all user-scoped): profile target role, `UserSkill` rows (level, confidence, source), active roadmap +
`summarize()` progress, completed items, next incomplete skill item, assessment ledger history, weak skills
(latest ledger outcome `weak`), RAG search over the question. **The context builder never reads
`Question.expected_answer` / `evaluation_rubric`.**

Intents (deterministic keyword classifier): `next_topic`, `explain`, `why_needed`, `test_me`, `exercise`,
`progress`, `general`.

- DEMO_MODE (`answer_source = "demo_rules"`): answers are assembled from stored state and retrieved chunks only.
  `explain/why_needed/general` need retrieved chunks with score ≥ `MENTOR_RAG_MIN_SCORE`; otherwise the answer
  says no relevant source was found and does **not** invent an explanation. `test_me` / `exercise` create an
  assessment through `AssessmentService` (bank-backed, labelled) and return its id + the key-free questions.
- Real mode (`answer_source = "llm"`): `LLMProvider.generate_structured` with the context block; the LLM returns
  `{answer, used_sources:[n…]}`; numbers are validated against the retrieved list; only those become citations.
  Retrieved text is passed as data, never as instructions.
- Citations: `[{index, title, source, heading, document_id, chunk_id, score}]`, present only when retrieved
  chunks were actually used.
- `missing_context`: list of human-readable gaps (no target role, no skills, no active roadmap, no assessments,
  RAG unavailable / no relevant documents). Always returned; also appended to the answer when non-empty.

## 9. API contracts (prefix `/api`)

| Method | Path | Notes |
|---|---|---|
| POST | `/assessments/generate` | `{user_id, skill_slug? , roadmap_item_id?, assessment_type=quiz|coding|mixed, question_count=5 (3–10)}` → `AssessmentOut`. 422 if no bank for the skill in DEMO_MODE |
| GET | `/assessments?user_id&skill?` | list (no questions) |
| GET | `/assessments/evidence?user_id&skill?` | ledger rows (read-only) |
| GET | `/assessments/{id}?user_id` | `AssessmentOut` (questions without keys) |
| POST | `/assessments/{id}/attempts` | `{user_id}` → `AttemptStartOut`; returns the open attempt if one exists |
| POST | `/assessments/attempts/{attempt_id}/submit` | `{user_id, answers:[{question_id, answer}]}` → `SubmitOut` (per-answer feedback, outcome, confidence update, adaptation summary) |
| POST | `/mentor/sessions` | `{user_id, title?}` |
| GET | `/mentor/sessions?user_id` / `/mentor/sessions/{id}?user_id` | list / history (last 50) |
| POST | `/mentor/sessions/{id}/messages` | `{user_id, message ≤ 2000 chars}` → `MentorReply` |

Errors: 404 unknown **or foreign** assessment/attempt/session (indistinguishable); 409 attempt already
submitted; 422 validation (unknown question id, duplicates, over-long answers); 503 when the RAG store is
unavailable is *not* raised — the mentor degrades and discloses it.

## 10. Ownership boundaries & the auth limitation

Every read/write path takes `user_id` and resolves rows with `filter_by(id=..., user_id=...)`. Cross-user access
returns 404. This stops accidental cross-user reads in a trusted caller; it is **not** authentication — anyone
who can call the API can pass any `user_id`. Real auth is Phase 13.

## 11. Acceptance tests (all in `tests/test_assessments`, `tests/test_mentor`)

- **Key leakage**: generate/fetch/start/submit responses and every mentor reply contain no `expected_answer`,
  rubric keyword, correct option id mapping or criteria text; OpenAPI response schemas contain no property named
  `expected_answer` / `evaluation_rubric` / `rubric`.
- **Determinism**: same answers → identical scores across runs; MCQ, short-answer partial credit, coding rubric;
  `executed:false` + notice present for coding.
- **Rules**: outcome thresholds; each delta; coding-only halving; ±0.30 cap; retake delta 0; insufficient;
  no-UserSkill path; `current_level`/`source` unchanged.
- **Evidence preservation**: after a resume re-analysis the ledger rows are intact, assessment evidence entries
  survive in `UserSkill.evidence`, confidence = resume + net; new UserSkill created later picks up the net.
- **Ownership**: foreign assessment/attempt/session → 404; submit by other user → 404.
- **Adaptive**: strong shrinks once + skips beginner resources, never completes; weak adds prerequisite,
  revision, exercises without duplicates on a second weak result; passed changes nothing; archived/absent
  roadmap handled; replan invoked; Phase 6–11 suites still green.
- **Mentor**: citations only from retrieved chunks; unknown-topic → no fabricated explanation; missing-context
  disclosure; uses roadmap/skills/assessment history; LLM path validates cited indices (fake provider).
- Migration upgrade → downgrade → upgrade; `alembic check` clean; Ruff clean; all three MCP suites.

## 12. Known limitations (to be repeated in README)

Keyword/regex rubric grading can be gamed and is not semantic; coding is never run; the demo bank covers a fixed
set of skills; revision/exercise items are not counted in schedule minutes; no auth.
