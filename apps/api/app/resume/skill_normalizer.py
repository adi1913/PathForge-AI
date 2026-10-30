"""
Resolves an extracted skill mention string to the existing Skill catalog
(Phase 2). Never creates a new Skill row for an unmatched name — that's
explicitly out of scope (a future skill-catalog enrichment phase's job);
an unmatched name is returned as-is so the caller can surface it in
ResumeAnalysis.unmatched_skills.
"""

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.skill import Skill

# Known synonyms mapped to the canonical slugs seeded in Phase 2
# (scripts/seed.py). Deliberately small and specific — a synonym here
# must be an actual equivalent, not a fuzzy guess.
_SYNONYMS = {
    "ml": "machine-learning",
    "machine learning": "machine-learning",
    "dl": "deep-learning",
    "deep learning": "deep-learning",
    "genai": "llm-genai",
    "gen ai": "llm-genai",
    "generative ai": "llm-genai",
    "llms": "llm-genai",
    "llm": "llm-genai",
    "large language models": "llm-genai",
    "ai agents": "ai-agents",
    "agents": "ai-agents",
    "retrieval augmented generation": "rag",
    "retrieval-augmented generation": "rag",
    "model context protocol": "mcp",
    "amazon web services": "aws",
}


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


class SkillNormalizer:
    def __init__(self, db: Session):
        self._db = db

    def normalize(self, raw_name: str) -> Skill | None:
        lowered = raw_name.lower().strip()
        candidate_slug = _SYNONYMS.get(lowered, _slugify(raw_name))

        skill = self._db.query(Skill).filter_by(slug=candidate_slug).one_or_none()
        if skill is not None:
            return skill

        # Fallback: case-insensitive exact name match (handles "PyTorch"
        # vs "pytorch" vs "PYTORCH" all resolving the same way when the
        # catalog's canonical name isn't already slug-equal).
        return self._db.query(Skill).filter(func.lower(Skill.name) == lowered).one_or_none()
