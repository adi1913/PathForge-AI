from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Document(UUIDPKMixin, TimestampMixin, Base):
    """A source document ingested for RAG (course notes, docs, guides).
    Content lives in DocumentChunk rows; this row is just identity +
    metadata, so re-ingesting an unchanged source is a no-op via
    content_hash."""

    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(150))  # e.g. "learning_resource_mcp", "manual_upload"
    source_url: Mapped[str | None] = mapped_column(String(1000))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # sha256 of raw content
    document_metadata: Mapped[dict | None] = mapped_column(JSON)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )


class DocumentChunk(UUIDPKMixin, Base):
    """One retrieval-sized piece of a Document's text.

    Deliberately holds NO vector column. Phase 2 is DB foundation only —
    which vector store (pgvector column vs external Qdrant collection) is
    a Phase 5 decision. `embedding_reference` is a free-form pointer
    (e.g. a Qdrant point id, or "pgvector:<table>:<id>" once chosen) so
    that decision doesn't require touching this table again."""

    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_order"),)

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSON)
    embedding_reference: Mapped[str | None] = mapped_column(String(255))

    document: Mapped["Document"] = relationship(back_populates="chunks")
