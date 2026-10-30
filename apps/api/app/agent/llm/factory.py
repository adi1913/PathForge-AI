from app.agent.llm.base import LLMProvider
from app.agent.llm.demo import DemoLLMProvider
from app.agent.llm.real import RealLLMProvider
from app.core.config import Settings, get_settings


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.DEMO_MODE:
        return DemoLLMProvider()
    return RealLLMProvider(settings)  # raises LLMUnavailableError if unconfigured
