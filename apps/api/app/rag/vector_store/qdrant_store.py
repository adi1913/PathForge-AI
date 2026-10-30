"""
Qdrant-backed VectorStore. Two modes, same class, same API:

- **Local mode** (default, `QDRANT_URL` unset): `AsyncQdrantClient(path=...)`
  — Qdrant's own embedded local storage engine, on-disk, no server
  process required at all. This is what makes DEMO_MODE (and tests) work
  with zero external services: it's genuinely the Qdrant client and
  Qdrant's real data structures/search algorithm, just not talking to a
  network server. Chosen over an ad hoc in-process vector store
  specifically so the "don't bypass the architecture" requirement holds
  — swapping to a real server later changes only configuration.
- **Server mode** (`QDRANT_URL` set): talks to a real Qdrant instance
  (e.g. the `qdrant` docker-compose service) over HTTP/gRPC.
"""

from qdrant_client import AsyncQdrantClient, models

from app.rag.errors import VectorStoreError
from app.rag.vector_store.base import VectorPoint, VectorSearchResult, VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(
        self,
        collection_name: str,
        url: str | None = None,
        api_key: str | None = None,
        local_path: str | None = None,
    ):
        self._collection_name = collection_name
        if url:
            self._client = AsyncQdrantClient(url=url, api_key=api_key)
        else:
            # local_path=None falls back to ":memory:" — used by tests
            # that want a throwaway store with no disk footprint at all.
            self._client = AsyncQdrantClient(path=local_path or ":memory:")

    async def ensure_collection(self, dimension: int) -> None:
        try:
            exists = await self._client.collection_exists(self._collection_name)
            if not exists:
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
                )
        except Exception as exc:
            raise VectorStoreError(f"Failed to ensure Qdrant collection '{self._collection_name}': {exc}") from exc

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        try:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=[models.PointStruct(id=p.point_id, vector=p.vector, payload=p.payload) for p in points],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to upsert {len(points)} point(s) into Qdrant: {exc}") from exc

    async def delete_by_document_id(self, document_id: str) -> None:
        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                    )
                ),
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete vectors for document '{document_id}': {exc}") from exc

    async def search(
        self, query_vector: list[float], top_k: int, filters: dict | None = None
    ) -> list[VectorSearchResult]:
        query_filter = None
        if filters:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(key=key, match=models.MatchValue(value=value))
                    for key, value in filters.items()
                ]
            )
        try:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc

        return [
            VectorSearchResult(point_id=str(point.id), score=point.score, payload=point.payload or {})
            for point in result.points
        ]

    async def has_point(self, point_id: str) -> bool:
        try:
            records = await self._client.retrieve(collection_name=self._collection_name, ids=[point_id])
        except Exception as exc:
            raise VectorStoreError(f"Qdrant lookup failed for point '{point_id}': {exc}") from exc
        return len(records) > 0

    async def close(self) -> None:
        await self._client.close()
