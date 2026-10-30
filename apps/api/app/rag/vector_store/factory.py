from app.core.config import Settings, get_settings
from app.rag.vector_store.base import VectorStore
from app.rag.vector_store.qdrant_store import QdrantVectorStore


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    settings = settings or get_settings()
    return QdrantVectorStore(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        local_path=settings.QDRANT_LOCAL_PATH,
    )
