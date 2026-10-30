import app.models  # noqa: F401
from app.models.document import Document, DocumentChunk
from app.rag.embeddings.demo import DemoEmbeddingProvider
from app.rag.service import RAGService
from app.rag.vector_store.qdrant_store import QdrantVectorStore


def _service(db):
    store = QdrantVectorStore(collection_name="svc_test", local_path=None)  # fresh :memory: per test
    embedder = DemoEmbeddingProvider(dimension=64)
    return RAGService(db=db, vector_store=store, embedding_provider=embedder)


async def test_ingest_creates_document_and_chunk_rows(db_session):
    service = _service(db_session)
    result = await service.ingest_document(
        title="Doc A", content="First paragraph.\n\nSecond paragraph.", source="src-a", content_type="text"
    )
    # Both short paragraphs share no heading context and fit well under
    # the default chunk size, so the chunker correctly merges them into
    # one chunk — this test is about the DB rows getting created, not
    # about forcing multiple chunks.
    assert result.chunks_created == 1
    assert db_session.query(Document).count() == 1
    assert db_session.query(DocumentChunk).filter_by(document_id=result.document_id).count() == 1


async def test_ingest_is_idempotent_for_identical_content(db_session):
    service = _service(db_session)
    r1 = await service.ingest_document(title="Doc B", content="Same content here.", source="src-b", content_type="text")
    r2 = await service.ingest_document(title="Doc B", content="Same content here.", source="src-b", content_type="text")
    assert r1.document_id == r2.document_id
    assert r2.chunks_created == 0
    assert db_session.query(Document).count() == 1  # no duplicate Document row
    assert db_session.query(DocumentChunk).count() == 1  # no duplicate chunks either


async def test_reingestion_with_changed_content_replaces_chunks(db_session):
    service = _service(db_session)
    r1 = await service.ingest_document(title="Doc C", content="Original content.", source="src-c", content_type="text")
    r2 = await service.ingest_document(
        title="Doc C", content="Completely different content now.", source="src-c", content_type="text"
    )
    assert r1.document_id == r2.document_id  # same document identity
    assert r2.reingested is True
    assert db_session.query(Document).count() == 1
    chunks = db_session.query(DocumentChunk).filter_by(document_id=r2.document_id).all()
    assert len(chunks) == 1
    assert "Completely different" in chunks[0].content


async def test_search_finds_ingested_content(db_session):
    service = _service(db_session)
    await service.ingest_document(
        title="Doc D",
        content="Kubernetes is a container orchestration platform.",
        source="src-d",
        content_type="text",
    )
    chunks, context = await service.search("container orchestration", top_k=3)
    assert len(chunks) >= 1
    assert "Kubernetes" in context.text


async def test_delete_document_removes_db_rows_and_vectors(db_session):
    service = _service(db_session)
    result = await service.ingest_document(
        title="Doc E", content="Some deletable content.", source="src-e", content_type="text"
    )
    await service.delete_document(result.document_id)
    assert db_session.query(Document).filter_by(id=result.document_id).count() == 0
    assert db_session.query(DocumentChunk).filter_by(document_id=result.document_id).count() == 0
    chunks, _ = await service.search("deletable content", top_k=5)
    assert all(c.document_id != result.document_id for c in chunks)


async def test_missing_vector_is_repaired_on_reingest(db_session):
    service = _service(db_session)
    result = await service.ingest_document(
        title="Doc F", content="Content that will lose its vector.", source="src-f", content_type="text"
    )
    # Simulate vector loss: clear embedding_reference on the chunk row
    # without touching the vector store (as if the store's data was wiped
    # independently of Postgres — the scenario "repair" exists for).
    chunk = db_session.query(DocumentChunk).filter_by(document_id=result.document_id).one()
    chunk.embedding_reference = None
    db_session.commit()

    # Re-ingesting identical content must detect and repair the gap.
    repair_result = await service.ingest_document(
        title="Doc F", content="Content that will lose its vector.", source="src-f", content_type="text"
    )
    assert repair_result.chunks_repaired == 1
    db_session.refresh(chunk)
    assert chunk.embedding_reference is not None


async def test_metadata_filters_are_stored_and_searchable(db_session):
    service = _service(db_session)
    await service.ingest_document(
        title="Doc G",
        content="Advanced RAG techniques for production systems.",
        source="src-g",
        content_type="text",
        extra_metadata={"skill": "rag", "difficulty": "advanced"},
    )
    chunks, _ = await service.search("RAG techniques", top_k=5, filters={"skill": "rag"})
    assert len(chunks) == 1
    chunks_wrong_filter, _ = await service.search("RAG techniques", top_k=5, filters={"skill": "python"})
    assert len(chunks_wrong_filter) == 0
