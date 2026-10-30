"""
The single entry point the API (and, later, the agent) uses for RAG.
Owns the DB session for Document/DocumentChunk rows and coordinates the
parser -> chunker -> embedding provider -> vector store pipeline.
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.document import Document, DocumentChunk
from app.rag.chunking.chunker import Chunk, StructuralChunker
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.errors import DocumentTooLargeError
from app.rag.parsers.factory import get_parser
from app.rag.retrieval.context_builder import RAGContext, build_context
from app.rag.retrieval.retriever import RetrievedChunk, Retriever
from app.rag.vector_store.base import VectorPoint, VectorStore

logger = logging.getLogger("pathforge.rag")

# Fixed namespace so point IDs are deterministic across process restarts —
# not just deterministic within one run. uuid5(NAMESPACE, f"{doc_id}:{i}")
# always yields the same point ID for the same (document, chunk_index).
_POINT_ID_NAMESPACE = uuid.UUID("6f6e1f6a-6b6a-4e9a-9f2a-9d6f6b6c6a6e")

_EMBEDDING_BATCH_SIZE = 64


@dataclass
class IngestResult:
    document_id: str
    chunks_created: int
    chunks_repaired: int
    reingested: bool


def _point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{document_id}:{chunk_index}"))


class RAGService:
    def __init__(
        self,
        db: Session,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        settings: Settings | None = None,
    ):
        self._db = db
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._settings = settings or get_settings()

    async def ingest_document(
        self,
        title: str,
        content: str,
        source: str | None,
        content_type: str,
        extra_metadata: dict | None = None,
    ) -> IngestResult:
        if len(content) > self._settings.RAG_MAX_DOCUMENT_CHARS:
            raise DocumentTooLargeError(
                f"Document is {len(content)} characters, exceeding the "
                f"{self._settings.RAG_MAX_DOCUMENT_CHARS}-character limit"
            )

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing_by_hash = self._db.query(Document).filter_by(content_hash=content_hash).one_or_none()
        if existing_by_hash is not None:
            # Identical content already ingested — idempotent no-op except
            # for repairing any chunk whose vector went missing.
            repaired = await self._repair_missing_vectors(existing_by_hash)
            return IngestResult(
                document_id=existing_by_hash.id,
                chunks_created=0,
                chunks_repaired=repaired,
                reingested=False,
            )

        # Same (title, source) but different content = a real re-ingestion
        # (the document changed) — replace its chunks/vectors rather than
        # accumulating stale ones under a second Document row.
        existing_by_identity = (
            self._db.query(Document).filter_by(title=title, source=source).one_or_none() if source is not None else None
        )
        reingested = existing_by_identity is not None
        document = existing_by_identity or Document(title=title, source=source)
        document.content_hash = content_hash
        document.document_metadata = extra_metadata or {}
        self._db.add(document)
        self._db.flush()  # assigns document.id

        if reingested:
            await self._vector_store.delete_by_document_id(document.id)
            self._db.query(DocumentChunk).filter_by(document_id=document.id).delete()
            self._db.flush()

        parsed = get_parser(content_type).parse(content)
        chunker = StructuralChunker(
            chunk_size=self._settings.RAG_CHUNK_SIZE_CHARS,
            chunk_overlap=self._settings.RAG_CHUNK_OVERLAP_CHARS,
            min_chunk_size=self._settings.RAG_MIN_CHUNK_SIZE_CHARS,
        )
        chunks = chunker.chunk(parsed)
        if len(chunks) > self._settings.RAG_MAX_CHUNKS_PER_DOCUMENT:
            raise DocumentTooLargeError(
                f"Document produced {len(chunks)} chunks, exceeding the "
                f"{self._settings.RAG_MAX_CHUNKS_PER_DOCUMENT}-chunk limit"
            )

        start = time.monotonic()
        chunk_rows = self._create_chunk_rows(document, chunks)
        # The caller-supplied `title` always wins — it's a required API
        # field. `parsed.title` (e.g. an H1 heading) is only ever a
        # fallback for a hypothetical future caller that doesn't supply
        # one; it must never override an explicitly given title.
        effective_title = title or parsed.title
        await self._embed_and_store(
            document, effective_title, source, content_type, extra_metadata or {}, chunk_rows, chunks
        )
        self._db.commit()
        logger.info(
            "Ingested document %s: %d chunks in %dms",
            document.id,
            len(chunks),
            int((time.monotonic() - start) * 1000),
        )

        return IngestResult(
            document_id=document.id, chunks_created=len(chunks), chunks_repaired=0, reingested=reingested
        )

    def _create_chunk_rows(self, document: Document, chunks: list[Chunk]) -> list[DocumentChunk]:
        rows = []
        for chunk in chunks:
            row = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                chunk_metadata={"heading_path": chunk.heading_path, "content_type": chunk.content_type},
            )
            self._db.add(row)
            rows.append(row)
        self._db.flush()
        return rows

    async def _embed_and_store(
        self,
        document: Document,
        title: str,
        source: str | None,
        content_type: str,
        extra_metadata: dict,
        chunk_rows: list[DocumentChunk],
        chunks: list[Chunk],
    ) -> None:
        await self._vector_store.ensure_collection(self._embedding_provider.dimension)

        for batch_start in range(0, len(chunks), _EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
            batch_rows = chunk_rows[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
            vectors = await self._embedding_provider.embed([c.content for c in batch_chunks])

            points = []
            for chunk, row, vector in zip(batch_chunks, batch_rows, vectors, strict=True):
                point_id = _point_id(document.id, chunk.chunk_index)
                payload = {
                    "document_id": document.id,
                    "chunk_id": row.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "title": title,
                    "source": source,
                    "heading_path": chunk.heading_path,
                    "document_type": content_type,
                    "content_type": chunk.content_type,
                    **extra_metadata,
                }
                points.append(VectorPoint(point_id=point_id, vector=vector, payload=payload))
                row.embedding_reference = point_id

            await self._vector_store.upsert(points)

    async def _repair_missing_vectors(self, document: Document) -> int:
        chunk_rows = (
            self._db.query(DocumentChunk).filter_by(document_id=document.id).order_by(DocumentChunk.chunk_index).all()
        )
        to_repair: list[DocumentChunk] = []
        for row in chunk_rows:
            if row.embedding_reference is None or not await self._vector_store.has_point(row.embedding_reference):
                to_repair.append(row)
        if not to_repair:
            return 0

        await self._vector_store.ensure_collection(self._embedding_provider.dimension)
        vectors = await self._embedding_provider.embed([row.content for row in to_repair])
        points = []
        for row, vector in zip(to_repair, vectors, strict=True):
            point_id = _point_id(document.id, row.chunk_index)
            metadata = row.chunk_metadata or {}
            payload = {
                "document_id": document.id,
                "chunk_id": row.id,
                "chunk_index": row.chunk_index,
                "content": row.content,
                "title": document.title,
                "source": document.source,
                "heading_path": metadata.get("heading_path", []),
                "document_type": (document.document_metadata or {}).get("document_type", "text"),
                "content_type": metadata.get("content_type", "text"),
            }
            points.append(VectorPoint(point_id=point_id, vector=vector, payload=payload))
            row.embedding_reference = point_id
        await self._vector_store.upsert(points)
        self._db.commit()
        logger.info("Repaired %d missing vector(s) for document %s", len(to_repair), document.id)
        return len(to_repair)

    async def delete_document(self, document_id: str) -> None:
        await self._vector_store.delete_by_document_id(document_id)
        self._db.query(DocumentChunk).filter_by(document_id=document_id).delete()
        self._db.query(Document).filter_by(id=document_id).delete()
        self._db.commit()

    async def search(
        self, query: str, top_k: int, filters: dict | None = None
    ) -> tuple[list[RetrievedChunk], RAGContext]:
        bounded_top_k = max(1, min(top_k, self._settings.RAG_MAX_TOP_K))
        retriever = Retriever(self._vector_store, self._embedding_provider, self._settings.RAG_MAX_TOP_K)
        chunks = await retriever.retrieve(query, bounded_top_k, filters)
        context = build_context(chunks, max_chunks=bounded_top_k, max_chars=self._settings.RAG_MAX_CONTEXT_CHARS)
        return chunks, context
