"""Deterministic requirement importance + expected-proficiency rules.

Importance score (additive, then bucketed):
  base            = 2 if required else 1
  +1  intensifying wording in the evidence (essential, mandatory, critical,
      high priority, strong knowledge/experience). "must"/"required" are
      excluded on purpose: they are already implied by requirement_type.
  +1  the skill is named >= 2 times in the whole JD
  +1  the skill is mentioned in the responsibilities section
  >=4 critical | 3 high | 2 medium | <=1 low

Expected level (first matching rule wins):
  expert / deep expertise / mastery                  -> expert
  strong|extensive experience, or N+ years with N>=5 -> advanced
  proficient / solid experience / working knowledge  -> intermediate
  familiarity / familiar with / basic ...            -> beginner
  N years with N<5                                   -> intermediate
  otherwise required -> intermediate, preferred -> beginner
"""

import re

from app.jobs.extraction.base import RawJDSkillMention
from app.models.enums import SkillImportance, SkillLevel

_STRONG_WORDING_RE = re.compile(
    r"\b(essential|mandatory|strong knowledge|strong experience|critical|high priority)\b", re.IGNORECASE
)
_EXPERT_WORDING_RE = re.compile(r"\b(expert|deep expertise|mastery)\b", re.IGNORECASE)
_ADVANCED_WORDING_RE = re.compile(r"\b(strong experience|extensive experience)\b", re.IGNORECASE)
_YEARS_RE = re.compile(r"(\d+)\+?\s*years?", re.IGNORECASE)
_INTERMEDIATE_WORDING_RE = re.compile(r"\b(proficient|solid experience|working knowledge)\b", re.IGNORECASE)
_BEGINNER_WORDING_RE = re.compile(
    r"\b(familiarity|familiar with|basic knowledge|basic understanding|basic)\b", re.IGNORECASE
)


def classify_importance(
    mention: RawJDSkillMention, all_mentions_for_skill: list[RawJDSkillMention], full_text: str
) -> SkillImportance:
    score = 2 if mention.requirement_type == "required" else 1
    evidence = " ".join(m.evidence_text for m in all_mentions_for_skill) or mention.evidence_text
    if _STRONG_WORDING_RE.search(evidence):
        score += 1
    if full_text.lower().count(mention.skill_name.lower()) >= 2:
        score += 1
    if any(m.source_section == "responsibilities" for m in all_mentions_for_skill):
        score += 1

    if score >= 4:
        return SkillImportance.CRITICAL
    if score == 3:
        return SkillImportance.HIGH
    if score == 2:
        return SkillImportance.MEDIUM
    return SkillImportance.LOW


def infer_expected_level(mention: RawJDSkillMention, requirement_type: str) -> SkillLevel:
    text = mention.evidence_text
    if _EXPERT_WORDING_RE.search(text):
        return SkillLevel.EXPERT
    years = _YEARS_RE.search(text)
    if _ADVANCED_WORDING_RE.search(text) or (years and int(years.group(1)) >= 5):
        return SkillLevel.ADVANCED
    if _INTERMEDIATE_WORDING_RE.search(text):
        return SkillLevel.INTERMEDIATE
    if _BEGINNER_WORDING_RE.search(text):
        return SkillLevel.BEGINNER
    if years:
        return SkillLevel.INTERMEDIATE
    return SkillLevel.INTERMEDIATE if requirement_type == "required" else SkillLevel.BEGINNER
