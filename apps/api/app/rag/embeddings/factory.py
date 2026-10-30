from app.core.config import Settings, get_settings
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.embeddings.demo import DemoEmbeddingProvider
from app.rag.embeddings.real import RealEmbeddingProvider


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if settings.DEMO_MODE:
        return DemoEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    return RealEmbeddingProvider(settings)  # raises EmbeddingUnavailableError if unconfigured
