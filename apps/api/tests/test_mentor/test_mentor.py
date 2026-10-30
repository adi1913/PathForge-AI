"""Phase 12 mentor: grounded citations, disclosure of missing context, roadmap/assessment awareness, ownership."""

import importlib

import pytest
from fastapi.testclient import TestClient

from app.agent.errors import AgentError
from app.mentor.errors import MentorError
from app.mentor.intent import classify_intent
from app.mentor.schemas import MessageRequest, SessionCreate
from app.mentor.service import MentorLLMReply, MentorService
from app.rag.retrieval.retriever import RetrievedChunk
from app.roadmap.schemas import RoadmapGenerateRequest
from app.roadmap.service import RoadmapService
from tests.test_assessments.helpers import gap, generate, own, run_attempt, seed


def _chunk(n=1, score=0.9, content="RAG retrieves documents and feeds them to the model as context."):
    return RetrievedChunk(
        chunk_id=f"c{n}",
        document_id=f"d{n}",
        content=content,
        score=score,
        source="kb://rag",
        title=f"Doc {n}",
        heading_path=["RAG", "Basics"],
        chunk_index=0,
    )


class FakeRAG:
    def __init__(self, chunks=None, fail=False):
        self.chunks, self.fail, self.queries = chunks or [], fail, []

    async def search(self, query, top_k, filters=None):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("vector store down")
        return self.chunks[:top_k], None


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def generate_structured(self, system, user, schema):
        self.calls.append(user)
        if self.error:
            raise self.error
        return self.reply


async def _ask(db, user, text, rag=None, llm=None):
    svc = MentorService(db, rag=rag, llm=llm)
    session = svc.create_session(SessionCreate(user_id=user.id))
    return await svc.post_message(session.id, MessageRequest(user_id=user.id, message=text)), svc, session


def test_intent_and_focus_detection():
    assert classify_intent("Quiz me on RAG") == "test_me"
    assert classify_intent("give me a coding exercise") == "exercise"
    assert classify_intent("what should I learn next?") == "next_topic"
    assert classify_intent("how am I doing") == "progress"
    assert classify_intent("explain embeddings") == "explain"
    assert classify_intent("hello") == "general"


async def test_explain_cites_only_retrieved_chunks(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["rag"], confidence=0.5)
    rag = FakeRAG([_chunk(1), _chunk(2, score=0.5)])
    reply, _, _ = await _ask(db_session, user, "Explain RAG", rag=rag)
    assert reply.answer_source == "demo_rules"
    assert [c.chunk_id for c in reply.citations] == ["c1", "c2"]
    assert all(f"[{c.index}]" in reply.answer for c in reply.citations)
    assert "Your recorded level for RAG" in reply.answer  # uses skill state
    assert "knowledge base" not in " ".join(reply.missing_context).lower() or reply.missing_context == []


async def test_no_relevant_source_means_no_fabricated_explanation_and_disclosure(db_session):
    user, _, _ = seed(db_session)
    reply, _, _ = await _ask(db_session, user, "Explain RAG", rag=FakeRAG([_chunk(1, score=0.01)]))
    assert reply.citations == []
    assert "won't guess" in reply.answer
    assert any("No relevant document" in m for m in reply.missing_context)
    assert "Missing context:" in reply.answer


async def test_unavailable_or_failing_knowledge_base_is_disclosed(db_session):
    user, _, _ = seed(db_session)
    none_reply, _, _ = await _ask(db_session, user, "Explain RAG", rag=None)
    assert any("unavailable" in m for m in none_reply.missing_context) and none_reply.citations == []
    failing, _, _ = await _ask(db_session, user, "Explain RAG", rag=FakeRAG(fail=True))
    assert any("failed" in m for m in failing.missing_context) and failing.citations == []


async def test_missing_roadmap_and_skills_are_disclosed(db_session):
    user, _, _ = seed(db_session)
    reply, _, _ = await _ask(db_session, user, "What should I learn next?")
    assert "no active roadmap" in reply.answer


async def test_next_topic_and_progress_use_roadmap_and_assessment_history(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["python"], confidence=0.8)
    gap(db_session, user, skills["machine-learning"])
    RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=2))
    nxt, _, _ = await _ask(db_session, user, "What should I learn next?")
    assert "Machine Learning" in nxt.answer

    a = await generate(db_session, user, "machine-learning")
    await run_attempt(db_session, user, a.id, "wrong")
    progress, _, _ = await _ask(db_session, user, "How am I doing?")
    assert "Machine Learning" in progress.answer
    assert "assessment" in progress.answer.lower() or "weak" in progress.answer.lower()


async def test_test_me_creates_key_free_assessment(db_session):
    user, _, skills = seed(db_session)
    reply, _, _ = await _ask(db_session, user, "Quiz me on RAG")
    assert reply.assessment is not None and reply.actions[0].type == "assessment_created"
    dumped = reply.model_dump_json()
    for forbidden in ("expected_answer", "evaluation_rubric", "any_of", "correct_option"):
        assert forbidden not in dumped
    assert "demo" in reply.answer.lower()


async def test_exercise_says_code_is_not_executed(db_session):
    user, _, _ = seed(db_session)
    reply, _, _ = await _ask(db_session, user, "Give me a coding exercise on docker")
    assert "never executed" in reply.answer


async def test_llm_path_keeps_only_valid_citation_indices(db_session):
    user, _, _ = seed(db_session)
    llm = FakeLLM(MentorLLMReply(answer="RAG feeds retrieved text to the model [1].", used_sources=[1, 7, 0]))
    reply, _, _ = await _ask(db_session, user, "Explain RAG", rag=FakeRAG([_chunk(1)]), llm=llm)
    assert reply.answer_source == "llm"
    assert [c.index for c in reply.citations] == [1]
    assert "SOURCES" in llm.calls[0]


async def test_llm_failure_falls_back_to_rules_with_disclosure(db_session):
    user, _, _ = seed(db_session)
    reply, _, _ = await _ask(
        db_session, user, "Explain RAG", rag=FakeRAG([_chunk(1)]), llm=FakeLLM(error=AgentError("boom"))
    )
    assert reply.answer_source == "demo_rules"
    assert any("LLM provider could not be used" in m for m in reply.missing_context)


async def test_session_ownership_and_message_limits(db_session):
    user, other, _ = seed(db_session)
    svc = MentorService(db_session)
    session = svc.create_session(SessionCreate(user_id=user.id))
    with pytest.raises(MentorError) as exc:
        await svc.post_message(session.id, MessageRequest(user_id=other.id, message="hi"))
    assert exc.value.status_code == 404
    with pytest.raises(MentorError) as exc:
        svc.get_session(session.id, other.id)
    assert exc.value.status_code == 404
    assert svc.list_sessions(other.id) == []
    with pytest.raises(MentorError) as exc:
        await svc.post_message(session.id, MessageRequest(user_id=user.id, message="x" * 2001))
    assert exc.value.status_code == 422
    with pytest.raises(MentorError):
        await svc.post_message(session.id, MessageRequest(user_id=user.id, message="   "))


async def test_history_is_persisted(db_session):
    user, _, _ = seed(db_session)
    _, svc, session = await _ask(db_session, user, "hello there")
    detail = svc.get_session(session.id, user.id)
    assert [m.role for m in detail.messages] == ["user", "mentor"] and detail.message_count == 2


# --- HTTP end-to-end with the real (demo) embedding provider -----------------------------------


@pytest.fixture
def e2e_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mentor_e2e.db'}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "mentor_e2e_test")
    from app.core.config import get_settings

    get_settings.cache_clear()  # settings are cached; without this the on-disk ./qdrant_data store is used
    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield session_module
    session_module.Base.metadata.drop_all(bind=session_module.engine)
    get_settings.cache_clear()


def test_http_mentor_cites_ingested_document_and_discloses_when_empty(e2e_env):
    import app.main as main_module

    db = e2e_env.SessionLocal()
    user, other, _ = seed(db)
    uid, oid = user.id, other.id
    db.close()
    importlib.reload(main_module)
    text = "Retrieval augmented generation RAG retrieves relevant documents and adds them to the prompt as context."
    with TestClient(main_module.app) as client:
        empty_session = client.post("/api/mentor/sessions", json={"user_id": uid}).json()
        empty = client.post(
            f"/api/mentor/sessions/{empty_session['id']}/messages",
            json={"user_id": uid, "message": "Explain retrieval augmented generation"},
        ).json()
        assert empty["citations"] == [] and empty["missing_context"]

        ing = client.post("/api/rag/ingest", json={"title": "RAG intro", "content": text, "source": "kb://rag-intro"})
        assert ing.status_code == 200, ing.text
        reply = client.post(
            f"/api/mentor/sessions/{empty_session['id']}/messages",
            json={"user_id": uid, "message": "Explain retrieval augmented generation RAG documents context"},
        ).json()
        assert reply["citations"], reply
        assert {c["document_id"] for c in reply["citations"]} == {ing.json()["document_id"]}

        assert client.get(f"/api/mentor/sessions/{empty_session['id']}", params={"user_id": oid}).status_code == 404
        too_long = client.post(
            f"/api/mentor/sessions/{empty_session['id']}/messages", json={"user_id": uid, "message": "x" * 2001}
        )
        assert too_long.status_code == 422
