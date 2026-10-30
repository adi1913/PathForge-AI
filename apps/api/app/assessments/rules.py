"""Pure, deterministic outcome + confidence-update rules (no DB, no LLM). See docs/phase12_spec.md §4-§5.
Confidence only: nothing here can change a skill level."""

from dataclasses import dataclass

from app.models.enums import AssessmentOutcome

RULES_VERSION = "p12.v1"
STRONG_MIN = 85.0
PASSED_MIN = 60.0
WEAK_SEVERE_BELOW = 40.0
MIN_QUESTIONS = 3
NET_CAP = 0.30
DEFAULT_CONFIDENCE = 0.5  # matches the Phase 7 gap engine's treatment of a null confidence

_DELTA = {
    AssessmentOutcome.STRONG: 0.10,
    AssessmentOutcome.PASSED: 0.03,
    AssessmentOutcome.INSUFFICIENT: 0.0,
}


def classify_outcome(score_percent: float, question_count: int) -> AssessmentOutcome:
    if question_count < MIN_QUESTIONS:
        return AssessmentOutcome.INSUFFICIENT
    if score_percent >= STRONG_MIN:
        return AssessmentOutcome.STRONG
    if score_percent >= PASSED_MIN:
        return AssessmentOutcome.PASSED
    return AssessmentOutcome.WEAK


def raw_delta(outcome: AssessmentOutcome, score_percent: float, coding_only: bool) -> float:
    if outcome == AssessmentOutcome.WEAK:
        delta = -0.10 if score_percent < WEAK_SEVERE_BELOW else -0.05
    else:
        delta = _DELTA[outcome]
    return delta * 0.5 if coding_only else delta


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_net(net: float) -> float:
    return clamp(net, -NET_CAP, NET_CAP)


@dataclass(frozen=True)
class ConfidenceUpdate:
    before: float | None
    after: float | None
    delta_applied: float
    note: str


def compute_confidence_update(
    *,
    outcome: AssessmentOutcome,
    score_percent: float,
    coding_only: bool,
    is_retake: bool,
    confidence_before: float | None,
    has_user_skill: bool,
    net_so_far: float,
) -> ConfidenceUpdate:
    """`net_so_far` = sum of confidence_delta_applied already in the ledger for this user+skill."""
    if not has_user_skill:
        return ConfidenceUpdate(
            None,
            None,
            0.0,
            "No level is recorded for this skill, so no confidence was changed. The result is kept as evidence "
            "and will be applied if a level is recorded later.",
        )
    before = DEFAULT_CONFIDENCE if confidence_before is None else confidence_before
    if outcome == AssessmentOutcome.INSUFFICIENT:
        return ConfidenceUpdate(
            before, before, 0.0, f"Fewer than {MIN_QUESTIONS} questions: too little evidence to change confidence."
        )
    if is_retake:
        return ConfidenceUpdate(
            before,
            before,
            0.0,
            "Retake of an already-assessed question set: stored as evidence, confidence not changed. "
            "Generate a new assessment with different questions to re-measure.",
        )
    raw = raw_delta(outcome, score_percent, coding_only)
    net = clamp_net(net_so_far)
    allowed = clamp(net + raw, -NET_CAP, NET_CAP) - net
    after = clamp(before + allowed, 0.0, 1.0)
    applied = round(after - before, 3)
    after = round(before + applied, 3)
    if applied == 0.0 and raw != 0.0:
        note = f"Confidence unchanged: the assessment adjustment is already at its ±{NET_CAP:g} limit or the bound."
    elif applied == 0.0:
        note = "Confidence unchanged for this outcome."
    else:
        note = f"Confidence {before:g} -> {after:g} ({applied:+g}) under rules {RULES_VERSION}."
        if coding_only:
            note += " Coding-only (text-rubric) evidence counts half."
    return ConfidenceUpdate(round(before, 3), after, applied, note)


def net_adjustment(deltas: list[float]) -> float:
    """Net assessment adjustment for one user+skill, as used by resume re-analysis."""
    return round(clamp_net(sum(deltas)), 3)
