from app.agent.llm.factory import get_llm_provider
from app.core.config import Settings, get_settings
from app.jobs.extraction.base import JobDescriptionExtractor
from app.jobs.extraction.demo_extractor import DemoJDExtractor
from app.jobs.extraction.real_extractor import RealJDExtractor


def get_jd_extractor(settings: Settings | None = None) -> JobDescriptionExtractor:
    settings = settings or get_settings()
    if settings.DEMO_MODE:
        return DemoJDExtractor()
    return RealJDExtractor(get_llm_provider(settings))
