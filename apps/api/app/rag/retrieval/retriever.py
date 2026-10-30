from dataclasses import dataclass

from app.rag.embeddings.base import EmbeddingProvider
from app.rag.vector_store.base import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    content: str
    score: float
    source: str | None
    title: str | None
    heading_path: list[str]
    chunk_index: int


class Retriever:
    def __init__(self, vector_store: VectorStore, embedding_provider: EmbeddingProvider, max_top_k: int):
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._max_top_k = max_top_k

    async def retrieve(self, query: str, top_k: int, filters: dict | None = None) -> list[RetrievedChunk]:
        bounded_top_k = max(1, min(top_k, self._max_top_k))
        query_vectors = await self._embedding_provider.embed([query])
        results = await self._vector_store.search(query_vectors[0], bounded_top_k, filters)
        return [
            RetrievedChunk(
                chunk_id=r.point_id,
                document_id=r.payload.get("document_id", ""),
                content=r.payload.get("content", ""),
                score=r.score,
                source=r.payload.get("source"),
                title=r.payload.get("title"),
                heading_path=r.payload.get("heading_path", []),
                chunk_index=r.payload.get("chunk_index", 0),
            )
            for r in results
        ]
