"""
Splits normalized resume text into named sections by scanning for
heading-shaped lines. Deliberately not tied to one fixed template:
known section-name variants map to a canonical key (so extraction code
can reliably find "the skills section" regardless of whether the resume
says "Skills", "Technical Skills", or "SKILLS"); an unrecognized but
heading-shaped line is preserved under its own key rather than
discarded, per the brief's "do not assume one fixed resume template."
"""

import re

CANONICAL_SECTION_VARIANTS: dict[str, list[str]] = {
    "summary": ["summary", "professional summary", "objective", "profile", "about", "about me"],
    "skills": ["skills", "technical skills", "core skills", "skill set", "key skills"],
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "work history",
        "relevant experience",
    ],
    "education": ["education", "academic background", "educational background"],
    "projects": ["projects", "personal projects", "key projects", "academic projects"],
    "certifications": ["certifications", "certificates", "licenses", "licenses and certifications"],
    "achievements": ["achievements", "accomplishments"],
    "publications": ["publications"],
    "awards": ["awards", "honors", "honors and awards"],
}

_VARIANT_TO_CANONICAL = {
    variant: canonical for canonical, variants in CANONICAL_SECTION_VARIANTS.items() for variant in variants
}

_HEADER_SECTION = "header"  # anything before the first detected heading (name, contact line, etc.)
_MAX_HEADING_WORDS = 6
_MAX_HEADING_CHARS = 60


def _normalize_heading_candidate(line: str) -> str:
    return re.sub(r"[:\-–—]+$", "", line.strip()).strip().lower()


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return False
    if stripped.endswith("."):  # a sentence, not a heading
        return False
    word_count = len(stripped.split())
    if word_count > _MAX_HEADING_WORDS:
        return False
    normalized = _normalize_heading_candidate(stripped)
    if normalized in _VARIANT_TO_CANONICAL:
        return True
    # Generic heading heuristic for a template this doesn't recognize:
    # resumes conventionally set section headers in ALL CAPS. Title-case
    # is deliberately NOT treated as a heading signal on its own — it
    # false-positives constantly on names, addresses, and degree lines
    # ("B.Sc Computer Science" is title-case-ish but not a heading).
    letters_only = re.sub(r"[^A-Za-z]", "", stripped)
    if not letters_only or len(letters_only) < 3:
        return False
    return letters_only.isupper()


def detect_sections(text: str, max_sections: int) -> dict[str, str]:
    """Returns an ordered dict: canonical name (for recognized headings)
    or the original heading text (for unrecognized-but-heading-shaped
    lines) -> that section's raw text. Content before the first detected
    heading lands under `_HEADER_SECTION`."""
    sections: dict[str, list[str]] = {_HEADER_SECTION: []}
    current = _HEADER_SECTION

    for line in text.split("\n"):
        if _looks_like_heading(line) and len(sections) < max_sections:
            normalized = _normalize_heading_candidate(line)
            current = _VARIANT_TO_CANONICAL.get(normalized, line.strip())
            sections.setdefault(current, [])
            continue
        sections[current].append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}
