"""
POST /api/rag/ingest -> Document created -> Chunks created -> Embeddings
generated -> Vectors stored -> POST /api/rag/search -> Retriever ->
Relevant chunks returned -> Sources preserved.

No mocking of the RAG pipeline anywhere in this file — real parser, real
chunker, real (demo) embeddings, real Qdrant (embedded local mode).
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    db_path = tmp_path / "rag_e2e_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "rag_e2e_test")

    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)


def _fresh_app():
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


def test_rag_ingest_then_search_end_to_end():
    with TestClient(_fresh_app()) as client:
        ingest_response = client.post(
            "/api/rag/ingest",
            json={
                "title": "Retrieval-Augmented Generation",
                "content": (
                    "# Retrieval-Augmented Generation\n\n"
                    "RAG combines a retriever with a language model to ground answers in real documents.\n\n"
                    "## Embeddings\n\n"
                    "Embeddings turn text into vectors so similar meanings land close together.\n\n"
                    "## Vector Databases\n\n"
                    "Vector databases like Qdrant store embeddings and support fast nearest-neighbor search."
                ),
                "source": "test-suite",
                "document_type": "markdown",
                "metadata": {"skill": "rag"},
            },
        )
        assert ingest_response.status_code == 200
        ingest_body = ingest_response.json()
        assert ingest_body["chunks_created"] == 3
        document_id = ingest_body["document_id"]

        search_response = client.post(
            "/api/rag/search", json={"query": "How do vector databases support search?", "top_k": 3}
        )

    assert search_response.status_code == 200
    body = search_response.json()
    assert len(body["results"]) >= 1
    assert any(r["document_id"] == document_id for r in body["results"])
    top_result = body["results"][0]
    assert "Vector" in top_result["content"] or "vector" in top_result["content"].lower()
    assert body["context"]  # non-empty, citation-preserving context text
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["title"] == "Retrieval-Augmented Generation"


def test_rag_search_with_metadata_filter():
    with TestClient(_fresh_app()) as client:
        client.post(
            "/api/rag/ingest",
            json={
                "title": "Python Basics",
                "content": "Python is a general-purpose programming language.",
                "source": "test-suite",
                "document_type": "text",
                "metadata": {"skill": "python"},
            },
        )
        client.post(
            "/api/rag/ingest",
            json={
                "title": "RAG Basics",
                "content": "RAG grounds language model answers in retrieved documents.",
                "source": "test-suite",
                "document_type": "text",
                "metadata": {"skill": "rag"},
            },
        )

        response = client.post(
            "/api/rag/search", json={"query": "programming language", "top_k": 5, "filters": {"skill": "python"}}
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Python Basics"


def test_rag_reingestion_is_idempotent_via_api():
    with TestClient(_fresh_app()) as client:
        payload = {
            "title": "Idempotency Check",
            "content": "This exact content should only ever produce one document.",
            "source": "test-suite",
            "document_type": "text",
        }
        r1 = client.post("/api/rag/ingest", json=payload)
        r2 = client.post("/api/rag/ingest", json=payload)

    assert r1.json()["document_id"] == r2.json()["document_id"]
    assert r2.json()["chunks_created"] == 0


def test_rag_ingest_validates_empty_content():
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/rag/ingest", json={"title": "Empty", "content": "", "document_type": "text"})
    assert response.status_code == 422
