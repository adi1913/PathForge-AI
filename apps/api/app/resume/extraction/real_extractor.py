"""
Real (non-demo) extraction. Reuses app.agent.llm.base.LLMProvider's
generate_structured — no second LLM abstraction. Structured output is
enforced and Pydantic-validated by generate_structured itself (forced
tool-calling + one repair attempt); this class just supplies the prompt.
"""

from app.agent.llm.base import LLMProvider
from app.resume.extraction.base import RawExtraction, ResumeExtractor

_SYSTEM_PROMPT = (
    "You extract structured information from resumes. Extract ONLY what is explicitly present in the "
    "provided text — never invent a company, date, skill, or credential that isn't there. If something "
    "is not present, leave the corresponding field empty or null. For skills, list every technology or "
    "skill explicitly mentioned or clearly demonstrated (e.g. named in a project description), tagging "
    "each with the section it came from."
)


class RealResumeExtractor(ResumeExtractor):
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    async def extract(self, text: str, sections: dict[str, str]) -> RawExtraction:
        user_prompt = f"Detected resume sections: {list(sections.keys())}\n\nFull resume text:\n{text}"
        return await self._llm.generate_structured(_SYSTEM_PROMPT, user_prompt, RawExtraction)
