from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VectorPoint:
    point_id: str
    vector: list[float]
    payload: dict


@dataclass
class VectorSearchResult:
    point_id: str
    score: float
    payload: dict


class VectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self, dimension: int) -> None:
        """Creates the collection if it doesn't already exist. Safe to
        call on every startup/ingestion — must be a no-op if the
        collection is already present with a matching dimension."""
        ...

    @abstractmethod
    async def upsert(self, points: list[VectorPoint]) -> None:
        """Insert or overwrite. Must be idempotent: upserting the same
        point_id again replaces the vector/payload, never duplicates."""
        ...

    @abstractmethod
    async def delete_by_document_id(self, document_id: str) -> None:
        """Removes every point belonging to one document — used on
        document deletion and before re-ingestion of changed content."""
        ...

    @abstractmethod
    async def search(
        self, query_vector: list[float], top_k: int, filters: dict | None = None
    ) -> list[VectorSearchResult]: ...

    @abstractmethod
    async def has_point(self, point_id: str) -> bool:
        """Used for missing-vector recovery: check whether a chunk's
        point already exists before deciding to re-embed it."""
        ...
