"""Deterministic skill-gap engine. The LLM never touches these numbers.

match status : no UserSkill / level NONE -> MISSING; rank(current) <
               rank(expected) -> WEAK; confidence < 0.4 -> WEAK (a weakly
               evidenced skill does not count as a full match); else MATCHED
severity     : MATCHED -> none. Else score = importance base (crit 4, high 3,
               med 2, low 1) + max(0, rank(expected) - rank(current));
               >=6 critical, >=4 high, >=2 medium, >=1 low
priority     : req_weight(required 1.0, preferred 0.6) * importance_weight/4
               * severity_weight(crit 1, high .75, med .5, low .25, none 0)
               * prerequisite_factor(1 + 0.1 per prerequisite that is also a
               gap, capped 1.5) * 100, clamped to [0, 100], 1 decimal
match score  : 100 * sum(w * achieved) / sum(w); w = req(required 2,
               preferred 1) * importance(crit 4, high 3, med 2, low 1);
               achieved = 1 matched, rank(cur)/rank(exp) weak, 0 missing
"""

from app.jobs.schemas import JobSkillRequirement
from app.models.enums import GapSeverity, SkillImportance, SkillLevel, SkillMatchStatus
from app.models.skill import UserSkill

_LEVEL_RANK = {
    SkillLevel.NONE: 0,
    SkillLevel.BEGINNER: 1,
    SkillLevel.INTERMEDIATE: 2,
    SkillLevel.ADVANCED: 3,
    SkillLevel.EXPERT: 4,
}
_LOW_CONFIDENCE_THRESHOLD = 0.4
_REQUIREMENT_WEIGHT = {"required": 2.0, "preferred": 1.0}
_IMPORTANCE_WEIGHT = {
    SkillImportance.CRITICAL: 4,
    SkillImportance.HIGH: 3,
    SkillImportance.MEDIUM: 2,
    SkillImportance.LOW: 1,
}
_SEVERITY_BASE = dict(_IMPORTANCE_WEIGHT)
_SEVERITY_WEIGHT = {
    GapSeverity.CRITICAL: 1.0,
    GapSeverity.HIGH: 0.75,
    GapSeverity.MEDIUM: 0.5,
    GapSeverity.LOW: 0.25,
    GapSeverity.NONE: 0.0,
}
_PRIORITY_REQUIREMENT_WEIGHT = {"required": 1.0, "preferred": 0.6}


def classify_match(
    requirement: JobSkillRequirement, user_skill: UserSkill | None
) -> tuple[SkillMatchStatus, SkillLevel, float]:
    if user_skill is None or user_skill.current_level == SkillLevel.NONE:
        return SkillMatchStatus.MISSING, SkillLevel.NONE, 1.0
    current = user_skill.current_level
    confidence = user_skill.confidence if user_skill.confidence is not None else 0.5
    if _LEVEL_RANK[current] < _LEVEL_RANK[requirement.expected_level]:
        return SkillMatchStatus.WEAK, current, confidence
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        return SkillMatchStatus.WEAK, current, confidence
    return SkillMatchStatus.MATCHED, current, confidence


def compute_severity(
    match_status: SkillMatchStatus,
    importance: SkillImportance,
    expected_level: SkillLevel,
    current_level: SkillLevel,
) -> GapSeverity:
    if match_status == SkillMatchStatus.MATCHED:
        return GapSeverity.NONE
    score = _SEVERITY_BASE[importance] + max(0, _LEVEL_RANK[expected_level] - _LEVEL_RANK[current_level])
    if score >= 6:
        return GapSeverity.CRITICAL
    if score >= 4:
        return GapSeverity.HIGH
    if score >= 2:
        return GapSeverity.MEDIUM
    return GapSeverity.LOW


def compute_priority_score(
    requirement_type: str, importance: SkillImportance, severity: GapSeverity, prerequisite_gap_count: int
) -> float:
    prerequisite_factor = min(1.5, 1.0 + 0.1 * max(0, prerequisite_gap_count))
    score = (
        _PRIORITY_REQUIREMENT_WEIGHT[requirement_type]
        * (_IMPORTANCE_WEIGHT[importance] / 4)
        * _SEVERITY_WEIGHT[severity]
        * prerequisite_factor
        * 100
    )
    return round(max(0.0, min(100.0, score)), 1)


def compute_overall_match_score(
    evaluated: list[tuple[JobSkillRequirement, SkillMatchStatus, SkillLevel]],
) -> float:
    total_weight = 0.0
    achieved_weight = 0.0
    for requirement, status, current in evaluated:
        weight = _REQUIREMENT_WEIGHT[requirement.requirement_type] * _IMPORTANCE_WEIGHT[requirement.importance]
        total_weight += weight
        if status == SkillMatchStatus.MATCHED:
            achieved = 1.0
        elif status == SkillMatchStatus.WEAK:
            achieved = _LEVEL_RANK[current] / max(1, _LEVEL_RANK[requirement.expected_level])
        else:
            achieved = 0.0
        achieved_weight += weight * min(1.0, achieved)
    if total_weight == 0:
        return 0.0
    return round(100.0 * achieved_weight / total_weight, 1)


def build_reasoning(
    requirement: JobSkillRequirement,
    match_status: SkillMatchStatus,
    current_level: SkillLevel,
    severity: GapSeverity,
) -> str:
    name = requirement.normalized_skill_name or requirement.raw_name
    kind = requirement.requirement_type
    if match_status == SkillMatchStatus.MATCHED:
        return (
            f"{name} is {kind} at {requirement.expected_level.value} level and the profile shows "
            f"{current_level.value} with sufficient evidence."
        )
    if match_status == SkillMatchStatus.WEAK:
        return (
            f"{name} is {kind} at {requirement.expected_level.value} level but the profile shows only "
            f"{current_level.value} (or low-confidence evidence); gap severity is {severity.value}."
        )
    verb = "requires" if kind == "required" else "prefers"
    return (
        f"The job {verb} {name} ({requirement.importance.value} importance, expected "
        f"{requirement.expected_level.value}) and no evidence of it was found in the profile; "
        f"gap severity is {severity.value}."
    )
