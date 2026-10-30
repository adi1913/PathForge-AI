"""Real (non-demo) JD extraction. Reuses the Phase 4 LLMProvider's
generate_structured (forced tool-calling + Pydantic validation + one
repair attempt). The LLM only extracts; scoring stays deterministic."""

from app.agent.llm.base import LLMProvider
from app.jobs.extraction.base import JobDescriptionExtractor, RawJDExtraction

_SYSTEM_PROMPT = (
    "You extract structured information from job descriptions. Extract ONLY what is explicitly present "
    "in the text — never invent a skill, company, or requirement. For each technology or skill, record the "
    "exact sentence it appears in and whether it is required or preferred (nice-to-have). Leave fields "
    "empty or null when the text does not contain them."
)


class RealJDExtractor(JobDescriptionExtractor):
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    async def extract(self, text: str, sections: dict[str, str]) -> RawJDExtraction:
        user_prompt = f"Detected JD sections: {list(sections.keys())}\n\nFull job description:\n{text}"
        return await self._llm.generate_structured(_SYSTEM_PROMPT, user_prompt, RawJDExtraction)
