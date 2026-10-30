import pytest

from app.jobs.gap_engine import (
    build_reasoning,
    classify_match,
    compute_overall_match_score,
    compute_priority_score,
    compute_severity,
)
from app.jobs.schemas import JobSkillRequirement
from app.models.enums import GapSeverity, SkillImportance, SkillLevel, SkillMatchStatus
from app.models.skill import UserSkill

S, M, G = SkillMatchStatus, GapSeverity, SkillImportance


def _req(rtype="required", importance=G.MEDIUM, expected=SkillLevel.INTERMEDIATE, name="Python"):
    return JobSkillRequirement(
        raw_name=name,
        normalized_skill_id="id",
        normalized_skill_name=name,
        requirement_type=rtype,
        importance=importance,
        expected_level=expected,
        evidence_text="e",
        confidence=0.6,
        reasoning="r",
    )


def _us(level, confidence=0.8):
    return UserSkill(user_id="u", skill_id="s", current_level=level, confidence=confidence)


# --- classify_match ---
def test_no_user_skill_is_missing():
    assert classify_match(_req(), None)[0] == S.MISSING


def test_level_none_is_missing():
    assert classify_match(_req(), _us(SkillLevel.NONE))[0] == S.MISSING


def test_sufficient_level_is_matched():
    assert classify_match(_req(), _us(SkillLevel.ADVANCED))[0] == S.MATCHED


def test_exactly_expected_level_is_matched():
    assert classify_match(_req(), _us(SkillLevel.INTERMEDIATE))[0] == S.MATCHED


def test_below_expected_is_weak():
    status, current, _ = classify_match(_req(expected=SkillLevel.ADVANCED), _us(SkillLevel.BEGINNER))
    assert status == S.WEAK and current == SkillLevel.BEGINNER


def test_low_confidence_downgrades_match_to_weak():
    assert classify_match(_req(), _us(SkillLevel.ADVANCED, confidence=0.2))[0] == S.WEAK


def test_missing_confidence_defaults_and_still_matches():
    assert classify_match(_req(), _us(SkillLevel.ADVANCED, confidence=None))[0] == S.MATCHED


# --- severity ---
def test_matched_has_no_severity():
    assert compute_severity(S.MATCHED, G.CRITICAL, SkillLevel.EXPERT, SkillLevel.EXPERT) == M.NONE


def test_critical_required_missing_is_critical():
    assert compute_severity(S.MISSING, G.CRITICAL, SkillLevel.ADVANCED, SkillLevel.NONE) == M.CRITICAL


def test_beginner_vs_advanced_high_importance_is_high_or_critical():
    sev = compute_severity(S.WEAK, G.HIGH, SkillLevel.ADVANCED, SkillLevel.BEGINNER)
    assert sev in (M.HIGH, M.CRITICAL)


def test_preferred_low_missing_is_lower_than_critical_required():
    low = compute_severity(S.MISSING, G.LOW, SkillLevel.BEGINNER, SkillLevel.NONE)
    crit = compute_severity(S.MISSING, G.CRITICAL, SkillLevel.ADVANCED, SkillLevel.NONE)
    assert low == M.MEDIUM and crit == M.CRITICAL


# --- priority ---
def test_priority_deterministic_and_bounded():
    a = compute_priority_score("required", G.CRITICAL, M.CRITICAL, 99)
    assert a == compute_priority_score("required", G.CRITICAL, M.CRITICAL, 99)
    assert 0 <= a <= 100


def test_required_outranks_preferred():
    assert compute_priority_score("required", G.HIGH, M.HIGH, 0) > compute_priority_score(
        "preferred", G.HIGH, M.HIGH, 0
    )


def test_critical_outranks_low():
    assert compute_priority_score("required", G.CRITICAL, M.CRITICAL, 0) > compute_priority_score(
        "required", G.LOW, M.LOW, 0
    )


def test_prerequisite_gaps_increase_priority_with_cap():
    base = compute_priority_score("required", G.HIGH, M.HIGH, 0)
    assert compute_priority_score("required", G.HIGH, M.HIGH, 2) > base
    assert compute_priority_score("required", G.HIGH, M.HIGH, 50) == compute_priority_score(
        "required", G.HIGH, M.HIGH, 5
    )


def test_matched_priority_is_zero():
    assert compute_priority_score("required", G.CRITICAL, M.NONE, 3) == 0.0


# --- overall ---
def test_perfect_candidate_scores_100():
    reqs = [(_req(), S.MATCHED, SkillLevel.ADVANCED), (_req(name="SQL"), S.MATCHED, SkillLevel.ADVANCED)]
    assert compute_overall_match_score(reqs) == 100.0


def test_partial_match_between_extremes():
    reqs = [(_req(), S.MATCHED, SkillLevel.ADVANCED), (_req(name="SQL"), S.MISSING, SkillLevel.NONE)]
    assert compute_overall_match_score(reqs) == 50.0


def test_weak_candidate_scores_by_level_ratio():
    reqs = [(_req(expected=SkillLevel.ADVANCED), S.WEAK, SkillLevel.BEGINNER)]
    assert compute_overall_match_score(reqs) == pytest.approx(33.3, abs=0.1)


def test_missing_critical_skills_scores_clearly_low():
    reqs = [
        (_req(importance=G.CRITICAL), S.MISSING, SkillLevel.NONE),
        (_req(importance=G.CRITICAL, name="Docker"), S.MISSING, SkillLevel.NONE),
        (_req(rtype="preferred", importance=G.LOW, name="Go"), S.MATCHED, SkillLevel.ADVANCED),
    ]
    assert compute_overall_match_score(reqs) < 15


def test_required_weighs_more_than_preferred():
    miss_required = [
        (_req(), S.MISSING, SkillLevel.NONE),
        (_req(rtype="preferred", name="Go"), S.MATCHED, SkillLevel.ADVANCED),
    ]
    miss_preferred = [
        (_req(), S.MATCHED, SkillLevel.ADVANCED),
        (_req(rtype="preferred", name="Go"), S.MISSING, SkillLevel.NONE),
    ]
    assert compute_overall_match_score(miss_required) < compute_overall_match_score(miss_preferred)


def test_empty_is_zero():
    assert compute_overall_match_score([]) == 0.0


# --- reasoning ---
def test_reasoning_explains_each_status():
    req = _req()
    assert "sufficient" in build_reasoning(req, S.MATCHED, SkillLevel.ADVANCED, M.NONE)
    assert "only" in build_reasoning(req, S.WEAK, SkillLevel.BEGINNER, M.MEDIUM)
    assert "requires" in build_reasoning(req, S.MISSING, SkillLevel.NONE, M.HIGH)
    assert "prefers" in build_reasoning(_req(rtype="preferred"), S.MISSING, SkillLevel.NONE, M.LOW)
