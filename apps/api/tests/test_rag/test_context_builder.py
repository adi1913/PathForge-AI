from app.rag.retrieval.context_builder import build_context
from app.rag.retrieval.retriever import RetrievedChunk


def _chunk(chunk_id, doc_id, content, score, chunk_index=0, title="T", heading_path=None):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        content=content,
        score=score,
        source="src",
        title=title,
        heading_path=heading_path or [],
        chunk_index=chunk_index,
    )


def test_context_preserves_source_attribution():
    chunks = [_chunk("c1", "d1", "Some content", 0.9, title="My Doc", heading_path=["Intro"])]
    context = build_context(chunks, max_chunks=5, max_chars=1000)
    assert "My Doc" in context.text
    assert "Intro" in context.text
    assert "Some content" in context.text
    assert context.sources[0].document_id == "d1"


def test_context_respects_max_chunks():
    chunks = [_chunk(f"c{i}", "d1", f"content {i}", 1.0, chunk_index=i) for i in range(10)]
    context = build_context(chunks, max_chunks=3, max_chars=100_000)
    assert len(context.sources) == 3


def test_context_respects_max_chars_by_dropping_whole_chunks():
    chunks = [_chunk(f"c{i}", "d1", "x" * 50, 1.0, chunk_index=i) for i in range(10)]
    context = build_context(chunks, max_chunks=10, max_chars=120)
    for source_block in context.text.split("\n\n---\n\n"):
        assert "x" * 50 in source_block  # every included chunk is whole


def test_context_deduplicates_same_chunk():
    chunk = _chunk("c1", "d1", "same content", 1.0, chunk_index=0)
    context = build_context([chunk, chunk, chunk], max_chunks=10, max_chars=10_000)
    assert len(context.sources) == 1


def test_context_applies_relevance_threshold():
    chunks = [
        _chunk("c1", "d1", "high relevance", 0.9, chunk_index=0),
        _chunk("c2", "d1", "low relevance", 0.1, chunk_index=1),
    ]
    context = build_context(chunks, max_chunks=10, max_chars=10_000, relevance_threshold=0.5)
    assert len(context.sources) == 1
    assert "high relevance" in context.text
    assert "low relevance" not in context.text


def test_empty_input_produces_empty_context():
    context = build_context([], max_chunks=5, max_chars=1000)
    assert context.text == ""
    assert context.sources == []
