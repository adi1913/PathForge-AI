"""Splits normalized JD text into named sections. Known heading variants
map to a canonical key; an unrecognized heading is preserved under its own
key only if it is strict ALL-CAPS (so ordinary sentences and title-case
lines in a JD are never mistaken for headings)."""

import re

CANONICAL_SECTION_VARIANTS: dict[str, list[str]] = {
    "summary": ["summary", "overview", "about the role", "about the job", "role summary", "job summary", "about us"],
    "responsibilities": [
        "responsibilities",
        "key responsibilities",
        "what you'll do",
        "what you will do",
        "duties",
        "your role",
        "the role",
        "day to day",
    ],
    "required_qualifications": [
        "requirements",
        "required qualifications",
        "required skills",
        "must have",
        "must haves",
        "minimum qualifications",
        "basic qualifications",
        "qualifications",
        "what you bring",
        "what we're looking for",
        "skills required",
    ],
    "preferred_qualifications": [
        "preferred qualifications",
        "preferred skills",
        "nice to have",
        "nice-to-have",
        "bonus",
        "bonus points",
        "preferred",
        "good to have",
        "plus",
        "desired skills",
    ],
    "experience": ["experience", "experience requirements", "years of experience"],
    "education": ["education", "education requirements"],
    "certifications": ["certifications", "certification requirements", "licenses"],
    "tools_and_technologies": ["tools and technologies", "tech stack", "technologies", "tools", "our stack"],
    "benefits": ["benefits", "perks", "what we offer", "compensation"],
}

_VARIANT_TO_CANONICAL = {
    variant: canonical for canonical, variants in CANONICAL_SECTION_VARIANTS.items() for variant in variants
}

HEADER_SECTION = "header"  # content before the first heading (title, company line)
_MAX_HEADING_WORDS = 6
_MAX_HEADING_CHARS = 60


def _normalize_heading_candidate(line: str) -> str:
    stripped = re.sub(r"^[#*\s]+|[*\s]+$", "", line)
    return re.sub(r"[:\-–—]+$", "", stripped).strip().lower().replace("’", "'")


_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _looks_like_heading(line: str) -> bool:
    if _BULLET_RE.match(line):  # a bullet like "- RAG" is content, never a heading
        return False
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS or stripped.endswith("."):
        return False
    if len(stripped.split()) > _MAX_HEADING_WORDS:
        return False
    if _normalize_heading_candidate(stripped) in _VARIANT_TO_CANONICAL:
        return True
    letters_only = re.sub(r"[^A-Za-z]", "", stripped)
    return len(letters_only) >= 3 and letters_only.isupper()


def detect_sections(text: str, max_sections: int) -> dict[str, str]:
    sections: dict[str, list[str]] = {HEADER_SECTION: []}
    current = HEADER_SECTION
    for line in text.split("\n"):
        if _looks_like_heading(line) and len(sections) < max_sections:
            normalized = _normalize_heading_candidate(line)
            current = _VARIANT_TO_CANONICAL.get(normalized, line.strip())
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}
