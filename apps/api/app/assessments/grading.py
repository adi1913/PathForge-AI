"""Deterministic grading. Pure functions: the same input always yields the same score.

Nothing here executes, imports, compiles or even parses submitted code: coding answers are plain text that
is checked for the presence of rubric elements. Nothing returned to a user contains the key (expected option,
keywords, criteria labels) — only correct/incorrect, a score and counts."""

import json
import re
from dataclasses import dataclass

from app.models.enums import QuestionType

WEIGHTS = {QuestionType.MULTIPLE_CHOICE: 1.0, QuestionType.SHORT_ANSWER: 1.0, QuestionType.CODING: 0.5}
CORRECT_THRESHOLD = 0.7
MIN_SHORT_ANSWER_WORDS = 5

METHOD_MCQ = "mcq_exact"
METHOD_SHORT = "short_keyword_rubric"
METHOD_CODING = "coding_text_rubric"

CODING_NOTICE = (
    "Your code was not executed. No tests were run and no correctness, security, complexity or code-quality "
    "analysis was performed. This score only reflects whether your text contains the elements the rubric "
    "looks for."
)
SHORT_NOTICE = "Scored by a keyword rubric, not a semantic judgement."


@dataclass(frozen=True)
class Criterion:
    label: str
    any_of: tuple[str, ...]
    weight: float = 1.0


@dataclass(frozen=True)
class GradedAnswer:
    score: float  # 0..1
    is_correct: bool
    feedback: str
    evaluation: dict


def dump_rubric(criteria: list[Criterion]) -> str:
    return json.dumps([{"label": c.label, "any_of": list(c.any_of), "weight": c.weight} for c in criteria])


def parse_rubric(text: str | None) -> list[Criterion]:
    if not text:
        return []
    try:
        raw = json.loads(text)
        return [
            Criterion(str(c["label"]), tuple(str(p) for p in c["any_of"]), float(c.get("weight", 1.0))) for c in raw
        ]
    except (ValueError, KeyError, TypeError):
        return []


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _present(haystack: str, pattern: str) -> bool:
    """Whole-word/phrase match when the pattern begins/ends with a word character, plain otherwise."""
    p = _normalize(pattern)
    if not p:
        return False
    left = r"(?<!\w)" if re.match(r"\w", p[0]) else ""
    right = r"(?!\w)" if re.match(r"\w", p[-1]) else ""
    return re.search(left + re.escape(p) + right, haystack) is not None


def grade_mcq(expected: str | None, answer: str | None) -> GradedAnswer:
    given = _normalize(answer or "")
    correct = bool(expected) and given == _normalize(expected)
    return GradedAnswer(
        score=1.0 if correct else 0.0,
        is_correct=correct,
        feedback="Correct." if correct else ("Incorrect." if given else "No answer given."),
        evaluation={"method": METHOD_MCQ},
    )


def grade_rubric(question_type: QuestionType, rubric_text: str | None, answer: str | None) -> GradedAnswer:
    coding = question_type == QuestionType.CODING
    method = METHOD_CODING if coding else METHOD_SHORT
    criteria = parse_rubric(rubric_text)
    text = _normalize(answer or "")
    base_eval = {"method": method, "notice": CODING_NOTICE if coding else SHORT_NOTICE}
    if coding:
        base_eval["executed"] = False
    if not criteria:
        return GradedAnswer(0.0, False, "This question has no usable rubric and could not be scored.", base_eval)
    if not text:
        return GradedAnswer(
            0.0, False, "No answer given.", {**base_eval, "criteria_met": 0, "criteria_total": len(criteria)}
        )
    if not coding and len(text.split()) < MIN_SHORT_ANSWER_WORDS:
        return GradedAnswer(
            0.0,
            False,
            f"Answer too short to score (at least {MIN_SHORT_ANSWER_WORDS} words).",
            {**base_eval, "criteria_met": 0, "criteria_total": len(criteria)},
        )
    met = [c for c in criteria if any(_present(text, p) for p in c.any_of)]
    total_weight = sum(c.weight for c in criteria)
    score = round(sum(c.weight for c in met) / total_weight, 4) if total_weight else 0.0
    return GradedAnswer(
        score=score,
        is_correct=score >= CORRECT_THRESHOLD,
        feedback=f"Matched {len(met)} of {len(criteria)} rubric elements.",
        evaluation={**base_eval, "criteria_met": len(met), "criteria_total": len(criteria)},
    )


def grade_answer(
    question_type: QuestionType, expected: str | None, rubric: str | None, answer: str | None
) -> GradedAnswer:
    if question_type == QuestionType.MULTIPLE_CHOICE:
        return grade_mcq(expected, answer)
    return grade_rubric(question_type, rubric, answer)


def weighted_score_percent(graded: list[tuple[QuestionType, float]]) -> float:
    total = sum(WEIGHTS[t] for t, _ in graded)
    if total == 0:
        return 0.0
    return round(100.0 * sum(WEIGHTS[t] * s for t, s in graded) / total, 1)
