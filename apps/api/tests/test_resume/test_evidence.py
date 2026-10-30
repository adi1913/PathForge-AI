from app.models.enums import SkillLevel
from app.resume.evidence import infer_proficiency
from app.resume.extraction.base import RawSkillMention


def _mention(evidence_type, skill="Python"):
    return RawSkillMention(
        skill_name=skill, evidence_text="some text", evidence_type=evidence_type, source_section="skills"
    )


def test_single_explicit_mention_is_beginner_not_advanced():
    # The exact scenario the brief calls out: "Python" in a skills list
    # must NOT automatically become Advanced.
    level, confidence, reasoning = infer_proficiency([_mention("explicit_mention")])
    assert level == SkillLevel.BEGINNER
    assert confidence <= 0.5


def test_demonstrated_usage_plus_work_experience_is_advanced():
    mentions = [_mention("demonstrated_usage"), _mention("work_experience")]
    level, confidence, reasoning = infer_proficiency(mentions)
    assert level == SkillLevel.ADVANCED
    assert confidence > 0.5


def test_single_demonstrated_usage_alone_is_intermediate_not_advanced():
    level, _, _ = infer_proficiency([_mention("demonstrated_usage")])
    assert level == SkillLevel.INTERMEDIATE


def test_no_evidence_returns_none_level():
    level, confidence, _ = infer_proficiency([])
    assert level == SkillLevel.NONE
    assert confidence == 0.0


def test_reasoning_is_explainable_and_lists_evidence():
    _, _, reasoning = infer_proficiency([_mention("certification"), _mention("work_experience")])
    assert "certification" in reasoning.lower()
    assert "work experience" in reasoning.lower()


def test_confidence_increases_with_more_evidence():
    _, conf_one, _ = infer_proficiency([_mention("explicit_mention")])
    _, conf_three, _ = infer_proficiency(
        [_mention("explicit_mention"), _mention("work_experience"), _mention("demonstrated_usage")]
    )
    assert conf_three > conf_one
