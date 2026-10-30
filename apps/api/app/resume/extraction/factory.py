from app.agent.llm.factory import get_llm_provider
from app.core.config import Settings, get_settings
from app.resume.extraction.base import ResumeExtractor
from app.resume.extraction.demo_extractor import DemoResumeExtractor
from app.resume.extraction.real_extractor import RealResumeExtractor


def get_resume_extractor(settings: Settings | None = None) -> ResumeExtractor:
    settings = settings or get_settings()
    if settings.DEMO_MODE:
        return DemoResumeExtractor()
    return RealResumeExtractor(get_llm_provider(settings))
