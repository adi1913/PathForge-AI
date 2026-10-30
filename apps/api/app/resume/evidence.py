"""
Turns a group of RawSkillMention evidence for one skill into a
(level, confidence, reasoning) triple. Deliberately conservative: a bare
mention in a skills list is weak evidence on its own; demonstrated usage
in a project or work experience is stronger. Never reaches "expert" from
rule-based evidence — that requires a strength of signal this heuristic
can't honestly claim to detect.
"""

from app.models.enums import SkillLevel
from app.resume.extraction.base import RawSkillMention

_EVIDENCE_WEIGHT = {
    "explicit_mention": 1.0,
    "certification": 2.0,
    "work_experience": 2.5,
    "demonstrated_usage": 3.0,
    "inferred": 0.5,
}

_EVIDENCE_LABEL = {
    "explicit_mention": "listed in the skills section",
    "certification": "backed by a certification",
    "work_experience": "used in work experience",
    "demonstrated_usage": "demonstrated in a project",
    "inferred": "inferred from context",
}


def infer_proficiency(mentions: list[RawSkillMention]) -> tuple[SkillLevel, float, str]:
    if not mentions:
        return SkillLevel.NONE, 0.0, "No evidence found."

    total_score = sum(_EVIDENCE_WEIGHT.get(m.evidence_type, 0.5) for m in mentions)
    distinct_types = {m.evidence_type for m in mentions}

    # Conservative thresholds: a single skills-list mention alone
    # (score 1.0, one type) stays "beginner" — exactly the "Python in a
    # skills list is not automatically Advanced" case the brief calls out.
    if total_score >= 5.0 and len(distinct_types) >= 2:
        level = SkillLevel.ADVANCED
    elif total_score >= 2.5 or len(distinct_types) >= 2:
        level = SkillLevel.INTERMEDIATE
    else:
        level = SkillLevel.BEGINNER

    confidence = min(1.0, 0.25 + 0.15 * len(mentions) + 0.1 * len(distinct_types))

    labels = sorted({_EVIDENCE_LABEL.get(m.evidence_type, m.evidence_type) for m in mentions})
    reasoning = f"{level.value.capitalize()} based on {len(mentions)} piece(s) of evidence: " + "; ".join(labels) + "."

    return level, round(confidence, 2), reasoning
