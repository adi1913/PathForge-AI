from app.assessments import grading
from app.assessments.grading import Criterion
from app.assessments.rules import (
    NET_CAP,
    classify_outcome,
    compute_confidence_update,
    net_adjustment,
    raw_delta,
)
from app.models.enums import AssessmentOutcome as O
from app.models.enums import QuestionType as Q

RUBRIC = grading.dump_rubric(
    [Criterion("a", ("alpha",)), Criterion("b", ("beta", "bravo")), Criterion("c", ("gamma",), 2.0)]
)


def test_mcq_exact_case_and_space_insensitive_and_unanswered():
    assert grading.grade_mcq("B", " b ").is_correct
    assert not grading.grade_mcq("B", "A").is_correct
    assert grading.grade_mcq("B", None).feedback == "No answer given."


def test_short_answer_partial_credit_is_weighted_and_deterministic():
    answer = "alpha and bravo are mentioned here"
    first = grading.grade_rubric(Q.SHORT_ANSWER, RUBRIC, answer)
    second = grading.grade_rubric(Q.SHORT_ANSWER, RUBRIC, answer)
    assert first == second
    assert first.score == 0.5 and not first.is_correct  # weights 1+1 of 4
    assert first.evaluation["criteria_met"] == 2 and first.evaluation["criteria_total"] == 3


def test_short_answer_too_short_scores_zero():
    assert grading.grade_rubric(Q.SHORT_ANSWER, RUBRIC, "alpha beta gamma").score == 0.0


def test_keyword_match_is_whole_word():
    rubric = grading.dump_rubric([Criterion("x", ("enter",))])
    assert grading.grade_rubric(Q.SHORT_ANSWER, rubric, "the center of the circle is here ok").score == 0.0
    assert grading.grade_rubric(Q.SHORT_ANSWER, rubric, "you enter the building through here").score == 1.0


def test_coding_is_text_rubric_never_executed_and_labelled():
    code = "import os; os.system('echo pwned'); alpha beta gamma"
    result = grading.grade_rubric(Q.CODING, RUBRIC, code)
    assert result.evaluation["executed"] is False
    assert result.evaluation["method"] == grading.METHOD_CODING
    assert "not executed" in result.evaluation["notice"]
    assert result.score == 1.0  # text present; nothing was run


def test_missing_rubric_cannot_score():
    assert grading.grade_rubric(Q.CODING, None, "anything").score == 0.0


def test_weighted_score_coding_counts_half():
    assert grading.weighted_score_percent([(Q.MULTIPLE_CHOICE, 1.0), (Q.CODING, 0.0)]) == 66.7
    assert grading.weighted_score_percent([]) == 0.0


def test_outcome_thresholds():
    assert classify_outcome(85, 5) == O.STRONG and classify_outcome(84.9, 5) == O.PASSED
    assert classify_outcome(60, 5) == O.PASSED and classify_outcome(59.9, 5) == O.WEAK
    assert classify_outcome(100, 2) == O.INSUFFICIENT


def test_raw_deltas_and_coding_only_halving():
    assert raw_delta(O.STRONG, 90, False) == 0.10 and raw_delta(O.PASSED, 70, False) == 0.03
    assert raw_delta(O.WEAK, 45, False) == -0.05 and raw_delta(O.WEAK, 35, False) == -0.10
    assert raw_delta(O.STRONG, 90, True) == 0.05


def _update(**kw):
    base = dict(
        outcome=O.STRONG,
        score_percent=90,
        coding_only=False,
        is_retake=False,
        confidence_before=0.6,
        has_user_skill=True,
        net_so_far=0.0,
    )
    return compute_confidence_update(**{**base, **kw})


def test_confidence_update_applies_and_clamps_to_one():
    assert _update().after == 0.7 and _update().delta_applied == 0.1
    assert _update(confidence_before=0.95).after == 1.0


def test_net_cap_limits_cumulative_adjustment():
    near = _update(net_so_far=NET_CAP - 0.05)
    assert near.delta_applied == 0.05
    capped = _update(net_so_far=NET_CAP)
    assert capped.delta_applied == 0.0 and "limit" in capped.note
    assert _update(outcome=O.WEAK, score_percent=10, net_so_far=-NET_CAP).delta_applied == 0.0


def test_retake_insufficient_and_missing_user_skill_do_not_change_confidence():
    assert _update(is_retake=True).delta_applied == 0.0
    assert _update(outcome=O.INSUFFICIENT).delta_applied == 0.0
    none = _update(has_user_skill=False, confidence_before=None)
    assert none.delta_applied == 0.0 and none.after is None and "No level is recorded" in none.note


def test_net_adjustment_is_bounded():
    assert net_adjustment([0.1, 0.1, 0.1, 0.1]) == NET_CAP and net_adjustment([-0.5]) == -NET_CAP
