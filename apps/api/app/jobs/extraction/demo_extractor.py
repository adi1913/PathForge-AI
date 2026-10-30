"""Rule-based JD extraction used whenever DEMO_MODE=true. Never calls an
LLM: everything is regex/heuristic extraction from the JD's own text, so
it never invents a skill the text doesn't contain."""

import re

from app.jobs.extraction.base import JobDescriptionExtractor, RawJDExtraction, RawJDSkillMention
from app.jobs.sections import HEADER_SECTION
from app.skill_vocabulary import find_tech_mentions

_COMPANY_AT_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9&.,' -]{1,60})\b")


def _split_lines_or_bullets(section_text: str) -> list[str]:
    lines = [line.strip().lstrip("-*•").strip() for line in section_text.split("\n")]
    lines = [line for line in lines if line]
    if len(lines) > 1:
        return lines
    joined = " ".join(lines)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", joined) if s.strip()]


def _evidence_line(section_text: str, term: str) -> str:
    for line in section_text.split("\n"):
        if term in line.lower():
            return line.strip().lstrip("-*•").strip()[:300]
    return section_text.strip()[:300]


def _mentions_from_section(section_text: str, requirement_type: str, source_section: str) -> list[RawJDSkillMention]:
    return [
        RawJDSkillMention(
            skill_name=term,
            evidence_text=_evidence_line(section_text, term),
            requirement_type=requirement_type,
            source_section=source_section,
        )
        for term in find_tech_mentions(section_text)
    ]


class DemoJDExtractor(JobDescriptionExtractor):
    async def extract(self, text: str, sections: dict[str, str]) -> RawJDExtraction:
        header = sections.get(HEADER_SECTION, "")
        header_lines = [line.strip() for line in header.split("\n") if line.strip()]
        title = header_lines[0].lstrip("# ").strip() if header_lines else None
        company_match = _COMPANY_AT_RE.search(header) or _COMPANY_AT_RE.search(text[:500])

        mentions = _mentions_from_section(
            sections.get("required_qualifications", ""), "required", "required_qualifications"
        ) + _mentions_from_section(
            sections.get("preferred_qualifications", ""), "preferred", "preferred_qualifications"
        )

        # A technology named under responsibilities is evidence of importance:
        # if it is also in a qualifications section it keeps that section's
        # requirement type (so a preferred skill never becomes required);
        # if it appears only here it is an implicit requirement.
        type_by_skill = {m.skill_name: m.requirement_type for m in mentions}
        responsibilities_text = sections.get("responsibilities", "")
        mentions += [
            m.model_copy(update={"requirement_type": type_by_skill.get(m.skill_name, "required")})
            for m in _mentions_from_section(responsibilities_text, "required", "responsibilities")
        ]

        tools_text = sections.get("tools_and_technologies", "")
        return RawJDExtraction(
            title=title,
            company=company_match.group(1).strip() if company_match else None,
            role=title,
            summary=sections.get("summary", "").strip() or None,
            responsibilities=_split_lines_or_bullets(responsibilities_text) if responsibilities_text else [],
            skill_mentions=mentions,
            experience_requirements=_split_lines_or_bullets(sections.get("experience", "")),
            education_requirements=_split_lines_or_bullets(sections.get("education", "")),
            certification_requirements=_split_lines_or_bullets(sections.get("certifications", "")),
            tools_and_technologies=find_tech_mentions(tools_text) if tools_text else [],
        )
