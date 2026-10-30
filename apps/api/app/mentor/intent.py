"""Deterministic intent classification and focus-skill detection for the mentor."""

import re

from app.models.skill import Skill

INTENTS = ("test_me", "exercise", "next_topic", "progress", "why_needed", "explain", "general")
_PATTERNS = [
    ("test_me", r"\b(test me|quiz me|quiz|assess me|assessment|test my)\b"),
    ("exercise", r"\b(coding exercise|coding challenge|practice exercise|exercise|practice problem)\b"),
    ("next_topic", r"\b(next topic|what should i (learn|study|do) next|what'?s next|what is next|what next)\b"),
    ("progress", r"\b(my progress|how am i doing|weak (areas|spots|skills)|where am i weak|what have i)\b"),
    ("why_needed", r"\bwhy (do|should) i (need|learn|study)\b|\bwhy (is|are) .{1,60}(needed|important|useful)\b"),
    ("explain", r"\b(explain|what is|what are|what's|define|how does|how do|tell me about)\b"),
]
_ALIASES = {
    "llm-genai": ("llm", "llms", "large language model", "generative ai", "genai"),
    "machine-learning": ("ml",),
    "ai-agents": ("agents", "agent", "ai agent"),
    "rag": ("retrieval augmented generation", "retrieval-augmented generation"),
    "mcp": ("model context protocol",),
    "deep-learning": ("dl", "neural networks"),
    "data-structures": ("dsa", "algorithms"),
}


def classify_intent(message: str) -> str:
    text = message.lower()
    for intent, pattern in _PATTERNS:
        if re.search(pattern, text):
            return intent
    return "general"


def _terms(skill: Skill) -> set[str]:
    return {skill.slug, skill.slug.replace("-", " "), skill.name.lower(), *_ALIASES.get(skill.slug, ())}


def find_focus_skill(message: str, skills: list[Skill]) -> Skill | None:
    """The catalog skill whose name/alias appears (as a whole word/phrase) in the message; the longest match wins."""
    text = message.lower()
    best: tuple[int, Skill] | None = None
    for skill in skills:
        for term in _terms(skill):
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) and (best is None or len(term) > best[0]):
                best = (len(term), skill)
    return best[1] if best else None
