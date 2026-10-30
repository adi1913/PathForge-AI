import pytest

from app.jobs.extraction.base import RawJDSkillMention
from app.jobs.requirement_classifier import classify_importance, infer_expected_level
from app.models.enums import SkillImportance, SkillLevel


def _m(name="python", rtype="required", evidence="Python", section="required_qualifications"):
    return RawJDSkillMention(skill_name=name, evidence_text=evidence, requirement_type=rtype, source_section=section)


def test_bare_required_is_medium_not_critical():
    m = _m()
    assert classify_importance(m, [m], "Python") == SkillImportance.MEDIUM


def test_bare_preferred_is_low():
    m = _m(rtype="preferred")
    assert classify_importance(m, [m], "Python") == SkillImportance.LOW


def test_strong_wording_raises_required_to_high():
    m = _m(evidence="Essential: Python")
    assert classify_importance(m, [m], "Python") == SkillImportance.HIGH


def test_strong_plus_repetition_is_critical():
    m = _m(evidence="Strong experience with Python")
    assert classify_importance(m, [m], "python and more python") == SkillImportance.CRITICAL


def test_repetition_alone_raises_one_step():
    m = _m()
    assert classify_importance(m, [m], "python, python") == SkillImportance.HIGH


def test_responsibilities_mention_boosts():
    req = _m()
    resp = _m(section="responsibilities")
    assert classify_importance(req, [req, resp], "Python") == SkillImportance.HIGH


def test_nice_to_have_wording_stays_low():
    m = _m(rtype="preferred", evidence="Nice to have: Python")
    assert classify_importance(m, [m], "Python") == SkillImportance.LOW


def test_must_and_required_do_not_double_count():
    m = _m(evidence="Python is required and a must")
    assert classify_importance(m, [m], "Python") == SkillImportance.MEDIUM


def test_importance_is_deterministic():
    m = _m(evidence="Strong experience with Python")
    results = {classify_importance(m, [m], "python python") for _ in range(5)}
    assert len(results) == 1


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ("Expert in Python", SkillLevel.EXPERT),
        ("Deep expertise in Python", SkillLevel.EXPERT),
        ("Strong experience with Python", SkillLevel.ADVANCED),
        ("5+ years of Python", SkillLevel.ADVANCED),
        ("Proficient in Python", SkillLevel.INTERMEDIATE),
        ("Working knowledge of Python", SkillLevel.INTERMEDIATE),
        ("3 years of Python", SkillLevel.INTERMEDIATE),
        ("Basic knowledge of Python", SkillLevel.BEGINNER),
        ("Familiarity with Python", SkillLevel.BEGINNER),
    ],
)
def test_expected_level_from_wording(evidence, expected):
    assert infer_expected_level(_m(evidence=evidence), "required") == expected


def test_required_without_wording_is_intermediate_not_expert():
    assert infer_expected_level(_m(), "required") == SkillLevel.INTERMEDIATE


def test_preferred_without_wording_is_beginner():
    assert infer_expected_level(_m(rtype="preferred"), "preferred") == SkillLevel.BEGINNER


def test_expert_wins_over_years():
    assert infer_expected_level(_m(evidence="Expert with 2 years Python"), "required") == SkillLevel.EXPERT
