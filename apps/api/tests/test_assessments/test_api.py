"""HTTP end-to-end for Phase 12 assessments: key-free responses, ownership, evidence ledger, resume preservation."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from tests.test_assessments.helpers import answers_for, own

FORBIDDEN_KEYS = {"expected_answer", "evaluation_rubric", "rubric", "any_of", "correct_option", "answer_key"}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'assess_e2e.db'}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)


def _app():
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


def _seed():
    import app.db.session as session_module
    from tests.test_assessments.helpers import seed

    db = session_module.SessionLocal()
    user, other, skills = seed(db)
    own(db, user, skills["rag"], confidence=0.5)
    ids = user.id, other.id
    db.close()
    return ids


def _keys(node):
    found = set()
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            found |= _keys(v)
    elif isinstance(node, list):
        for v in node:
            found |= _keys(v)
    return found


def _answers(assessment_id, mode):
    import app.db.session as session_module

    db = session_module.SessionLocal()
    try:
        return [a.model_dump() for a in answers_for(db, assessment_id, mode)]
    finally:
        db.close()


def _generate(client, user, **extra):
    body = {"user_id": user, "skill_slug": "rag", "assessment_type": "quiz", "question_count": 5, **extra}
    return client.post("/api/assessments/generate", json=body)


def test_full_flow_never_leaks_answer_keys_and_records_evidence():
    owner, _ = _seed()
    with TestClient(_app()) as client:
        gen = _generate(client, owner)
        assert gen.status_code == 200, gen.text
        assessment = gen.json()
        assert assessment["source_label"] and "demo" in assessment["source_label"].lower()
        responses = [assessment]

        fetched = client.get(f"/api/assessments/{assessment['id']}", params={"user_id": owner})
        assert fetched.status_code == 200
        responses.append(fetched.json())
        listing = client.get("/api/assessments", params={"user_id": owner})
        assert listing.status_code == 200
        responses.append(listing.json())

        started = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner})
        assert started.status_code == 200
        responses.append(started.json())
        again = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner}).json()
        assert again["resumed"] is True and again["attempt_id"] == started.json()["attempt_id"]

        submit = client.post(
            f"/api/assessments/attempts/{started.json()['attempt_id']}/submit",
            json={"user_id": owner, "answers": _answers(assessment["id"], "correct")},
        )
        assert submit.status_code == 200, submit.text
        result = submit.json()
        responses.append(result)
        assert result["outcome"] == "strong"
        assert result["confidence"]["level_changed"] is False
        assert result["confidence"]["after"] > result["confidence"]["before"]

        evidence = client.get("/api/assessments/evidence", params={"user_id": owner, "skill": "rag"})
        assert evidence.status_code == 200 and len(evidence.json()) == 1
        responses.append(evidence.json())

        # resubmitting the same attempt is a conflict, not a second evidence row
        dup = client.post(
            f"/api/assessments/attempts/{started.json()['attempt_id']}/submit",
            json={"user_id": owner, "answers": _answers(assessment["id"], "correct")},
        )
        assert dup.status_code == 409

        for payload in responses:
            leaked = _keys(payload) & FORBIDDEN_KEYS
            assert not leaked, leaked
        # no stored key value appears verbatim in any user-facing response
        blob = json.dumps(responses)
        import app.db.session as session_module
        from app.assessments import grading
        from app.models.assessment import Question

        db = session_module.SessionLocal()
        for q in db.query(Question).all():
            for c in grading.parse_rubric(q.evaluation_rubric):
                for kw in c.any_of:
                    if len(kw) >= 12:
                        assert kw not in blob
        db.close()


def test_openapi_schema_exposes_no_answer_key_fields():
    with TestClient(_app()) as client:
        schema = client.get("/api/openapi.json").json()
    names = set()
    for name, comp in schema["components"]["schemas"].items():
        if any(t in name for t in ("Assessment", "Question", "Attempt", "Submit", "Answer", "Evidence", "Mentor")):
            names |= set(comp.get("properties", {}))
    assert names
    assert not (names & FORBIDDEN_KEYS), names & FORBIDDEN_KEYS


def test_ownership_unknown_and_foreign_ids_are_not_found():
    owner, other = _seed()
    with TestClient(_app()) as client:
        assessment = _generate(client, owner).json()
        attempt = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner}).json()
        answers = _answers(assessment["id"], "correct")

        assert client.get(f"/api/assessments/{assessment['id']}", params={"user_id": other}).status_code == 404
        assert client.get("/api/assessments/nope", params={"user_id": owner}).status_code == 404
        assert client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": other}).status_code == 404
        foreign_submit = client.post(
            f"/api/assessments/attempts/{attempt['attempt_id']}/submit", json={"user_id": other, "answers": answers}
        )
        assert foreign_submit.status_code == 404
        assert client.get("/api/assessments", params={"user_id": other}).json() == []
        assert client.get("/api/assessments/evidence", params={"user_id": other}).json() == []
        # the foreign attempt was not consumed
        ok = client.post(
            f"/api/assessments/attempts/{attempt['attempt_id']}/submit", json={"user_id": owner, "answers": answers}
        )
        assert ok.status_code == 200


def test_validation_errors():
    owner, _ = _seed()
    with TestClient(_app()) as client:
        assert _generate(client, owner, skill_slug="not-a-skill").status_code in (404, 422)
        assert _generate(client, owner, question_count=2).status_code == 422
        assert _generate(client, owner, question_count=11).status_code == 422
        assessment = _generate(client, owner).json()
        attempt = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner}).json()
        bad = client.post(
            f"/api/assessments/attempts/{attempt['attempt_id']}/submit",
            json={"user_id": owner, "answers": [{"question_id": "nope", "answer": "A"}]},
        )
        assert bad.status_code == 422


def test_coding_answers_are_rubric_graded_and_labelled_not_executed():
    owner, _ = _seed()
    with TestClient(_app()) as client:
        assessment = _generate(client, owner, assessment_type="mixed", question_count=7).json()
        attempt = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner}).json()
        answers = _answers(assessment["id"], "correct")
        coding_ids = [q["id"] for q in assessment["questions"] if q["question_type"] == "coding"]
        assert coding_ids
        result = client.post(
            f"/api/assessments/attempts/{attempt['attempt_id']}/submit", json={"user_id": owner, "answers": answers}
        ).json()
        coding = [a for a in result["answers"] if a["question_id"] in coding_ids]
        assert coding and all(a["evaluation"]["executed"] is False and a["evaluation"]["notice"] for a in coding)


def test_resume_reanalysis_preserves_assessment_evidence_and_ledger():
    owner, _ = _seed()
    with TestClient(_app()) as client:
        assessment = _generate(client, owner).json()
        attempt = client.post(f"/api/assessments/{assessment['id']}/attempts", json={"user_id": owner}).json()
        result = client.post(
            f"/api/assessments/attempts/{attempt['attempt_id']}/submit",
            json={"user_id": owner, "answers": _answers(assessment["id"], "correct")},
        ).json()
        delta = result["confidence"]["delta"]
        assert delta > 0

        resp = client.post(
            "/api/resume/analyze",
            data={"user_id": owner, "text": "Jane Doe\n\nSKILLS\n- RAG\n- Python\n"},
        )
        assert resp.status_code == 200, resp.text

        import app.db.session as session_module
        from app.models.assessment import AssessmentEvidence
        from app.models.skill import Skill, UserSkill

        db = session_module.SessionLocal()
        try:
            assert db.query(AssessmentEvidence).filter_by(user_id=owner).count() == 1
            rag = db.query(Skill).filter_by(slug="rag").one()
            row = db.get(UserSkill, (owner, rag.id))
            types = [e.get("type") for e in row.evidence]
            assert "assessment" in types
            assert 0.0 <= row.confidence <= 1.0
        finally:
            db.close()
        still = client.get("/api/assessments/evidence", params={"user_id": owner}).json()
        assert len(still) == 1
