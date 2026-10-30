"""
Rule-based extraction used whenever DEMO_MODE=true. Deliberately never
calls an LLM (see app.agent.llm.demo.DemoLLMProvider.generate_structured,
which refuses on principle) — everything here is regex/heuristic
extraction directly from the resume's own text, so it never invents a
fact the text doesn't contain.

Not NLP-grade (no real named-entity recognition) — good enough to prove
the pipeline end to end and to give real, traceable evidence text for
every skill claim, which is the actual Phase 6 requirement.
"""

import re

from app.resume.extraction.base import RawExtraction, RawSkillMention
from app.skill_vocabulary import find_tech_mentions

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_URL_RE = re.compile(r"https?://\S+")
_DATE_RANGE_RE = re.compile(
    r"(?P<start>[A-Za-z]+\s+\d{4}|\d{4})\s*(?:-|–|—|to)\s*(?P<end>present|current|[A-Za-z]+\s+\d{4}|\d{4})",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"\b(Bachelor|Master|B\.?Sc\.?|M\.?Sc\.?|B\.?Tech\.?|M\.?Tech\.?|B\.?A\.?|M\.?A\.?|Ph\.?D\.?|Associate|Diploma)\b",
    re.IGNORECASE,
)
_INSTITUTION_RE = re.compile(r"\b(University|College|Institute|School)\b", re.IGNORECASE)
_FIELD_RE = re.compile(r"\bin\s+([A-Za-z][A-Za-z &]+)", re.IGNORECASE)


def _split_blocks(section_text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", section_text) if b.strip()]


def _extract_bullets(block: str) -> tuple[list[str], list[str]]:
    """Splits a block's lines into (bullet_lines, non_bullet_lines)."""
    bullets, rest = [], []
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")):
            bullets.append(stripped.lstrip("-*• ").strip())
        elif stripped:
            rest.append(stripped)
    return bullets, rest


def _find_date_range(block: str) -> re.Match | None:
    """Searches line-by-line (never across a newline) so a degree line
    ending in one year and a separate date-range line don't get fused
    into one bogus match by \\s+ matching across the line break."""
    for line in block.split("\n"):
        match = _DATE_RANGE_RE.search(line)
        if match:
            return match
    return None


def _parse_experience_block(block: str) -> dict:
    lines = [line for line in block.split("\n") if line.strip()]
    if not lines:
        return {}
    first_line = lines[0].strip()

    company, role = None, None
    at_match = re.match(r"(.+?)\s+at\s+(.+)", first_line, re.IGNORECASE)
    dash_match = re.match(r"(.+?)\s*[-–—]\s*(.+)", first_line)
    if at_match:
        role, company = at_match.group(1).strip(), at_match.group(2).strip()
    elif dash_match:
        company, role = dash_match.group(1).strip(), dash_match.group(2).strip()
    else:
        role = first_line

    date_match = _find_date_range(block)
    start_date = date_match.group("start") if date_match else None
    end_date = date_match.group("end") if date_match else None
    is_current = bool(end_date and end_date.lower() in {"present", "current"})

    remaining_lines = [line for line in lines[1:] if not (date_match and date_match.group(0) in line)]
    description = " ".join(remaining_lines).strip()

    return {
        "company": company,
        "role": role,
        "start_date": start_date,
        "end_date": end_date,
        "is_current": is_current,
        "description": description,
        "technologies": find_tech_mentions(block),
        "_evidence_text": block[:300],
    }


def _parse_project_block(block: str) -> dict:
    lines = [line for line in block.split("\n") if line.strip()]
    if not lines:
        return {}
    name = re.sub(r"[:\-–—]+$", "", lines[0].strip())
    bullets, rest = _extract_bullets("\n".join(lines[1:]))
    links = _URL_RE.findall(block)
    return {
        "name": name,
        "description": " ".join(rest).strip(),
        "technologies": find_tech_mentions(block),
        "links": links,
        "achievements": bullets,
        "_evidence_text": block[:300],
    }


def _parse_education_block(block: str) -> dict:
    degree_match = _DEGREE_RE.search(block)
    institution_match = _INSTITUTION_RE.search(block)
    date_match = _find_date_range(block)
    field_match = _FIELD_RE.search(block) if degree_match else None

    institution = None
    if institution_match:
        line_with_institution = next(
            (line for line in block.split("\n") if institution_match.group(0).lower() in line.lower()), None
        )
        if line_with_institution:
            # Prefer just the comma-segment naming the institution (a
            # single line often reads "B.Sc Computer Science, State
            # University") over the whole line, which would otherwise
            # also swallow the degree/field text.
            segments = [s.strip() for s in line_with_institution.split(",")]
            institution = next(
                (s for s in segments if institution_match.group(0).lower() in s.lower()), line_with_institution
            )

    return {
        "institution": institution,
        "degree": degree_match.group(0) if degree_match else None,
        "field": field_match.group(1).strip() if field_match else None,
        "start_date": date_match.group("start") if date_match else None,
        "end_date": date_match.group("end") if date_match else None,
    }


def _parse_certification_line(line: str) -> dict | None:
    stripped = line.strip().lstrip("-*• ").strip()
    if not stripped:
        return None
    year_match = re.search(r"\b(19|20)\d{2}\b", stripped)
    url_match = _URL_RE.search(stripped)
    parts = stripped.split(",")
    name = parts[0].strip()
    issuer = parts[1].strip() if len(parts) > 1 else None
    return {
        "name": name,
        "issuer": issuer,
        "date": year_match.group(0) if year_match else None,
        "credential_url": url_match.group(0) if url_match else None,
    }


class DemoResumeExtractor:
    async def extract(self, text: str, sections: dict[str, str]) -> RawExtraction:
        header = sections.get("header", "")
        header_lines = [line.strip() for line in header.split("\n") if line.strip()]

        contact_name = None
        for line in header_lines:
            if not _EMAIL_RE.search(line) and not _PHONE_RE.search(line) and 1 <= len(line.split()) <= 5:
                contact_name = line
                break

        full_text_for_contact = header + "\n" + sections.get("summary", "")
        email_match = _EMAIL_RE.search(full_text_for_contact) or _EMAIL_RE.search(text)
        phone_match = _PHONE_RE.search(full_text_for_contact) or _PHONE_RE.search(text)
        links = _URL_RE.findall(header) or _URL_RE.findall(text[:1000])

        skill_mentions: list[RawSkillMention] = []
        skills_section = sections.get("skills", "")
        if skills_section:
            tokens = re.split(r"[,\n;|•]", skills_section)
            for token in tokens:
                cleaned = token.strip().strip("-*").strip()
                if cleaned and len(cleaned) <= 60:
                    skill_mentions.append(
                        RawSkillMention(
                            skill_name=cleaned,
                            evidence_text=skills_section[:200],
                            evidence_type="explicit_mention",
                            source_section="skills",
                        )
                    )

        experience = [_parse_experience_block(b) for b in _split_blocks(sections.get("experience", "")) if b.strip()]
        experience = [e for e in experience if e]
        for exp in experience:
            for tech in exp.get("technologies", []):
                skill_mentions.append(
                    RawSkillMention(
                        skill_name=tech,
                        evidence_text=exp.get("_evidence_text", ""),
                        evidence_type="work_experience",
                        source_section="experience",
                    )
                )

        projects = [_parse_project_block(b) for b in _split_blocks(sections.get("projects", "")) if b.strip()]
        projects = [p for p in projects if p]
        for proj in projects:
            for tech in proj.get("technologies", []):
                skill_mentions.append(
                    RawSkillMention(
                        skill_name=tech,
                        evidence_text=proj.get("_evidence_text", ""),
                        evidence_type="demonstrated_usage",
                        source_section="projects",
                    )
                )

        education = [_parse_education_block(b) for b in _split_blocks(sections.get("education", ""))]
        education = [e for e in education if e.get("institution") or e.get("degree")]

        certifications = []
        cert_section = sections.get("certifications", "")
        for line in cert_section.split("\n"):
            parsed = _parse_certification_line(line)
            if parsed:
                certifications.append(parsed)
                skill_mentions.append(
                    RawSkillMention(
                        skill_name=parsed["name"],
                        evidence_text=line.strip(),
                        evidence_type="certification",
                        source_section="certifications",
                    )
                )

        achievements = []
        for key in ("achievements", "awards"):
            section_text = sections.get(key, "")
            bullets, rest = _extract_bullets(section_text)
            achievements.extend(bullets or rest)

        summary = sections.get("summary", "").strip() or None

        return RawExtraction(
            summary=summary,
            contact_name=contact_name,
            contact_email=email_match.group(0) if email_match else None,
            contact_phone=phone_match.group(0) if phone_match else None,
            contact_location=None,
            contact_links=links,
            skill_mentions=skill_mentions,
            experience=experience,
            education=education,
            projects=projects,
            certifications=certifications,
            achievements=achievements,
        )
