"""HTTP end-to-end for Phase 10: JD analysis -> application -> readiness -> status flow."""

import importlib

import pytest
from fastapi.testclient import TestClient

_JD = "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n\nPREFERRED QUALIFICATIONS\n- Python\n"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'apps_e2e.db'}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)


def _client():
    import app.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


def _seed():
    import app.db.session as session_module
    from app.models.enums import EvidenceSource, SkillLevel
    from app.models.skill import Skill, SkillPrerequisite, UserSkill
    from app.models.user import User

    db = session_module.SessionLocal()
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [("python", "Python"), ("machine-learning", "Machine Learning"), ("docker", "Docker")]
    }
    db.add_all(skills.values())
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    owner = User(email="owner@example.com", password_hash="h")
    other = User(email="intruder@example.com", password_hash="h")
    db.add_all([owner, other])
    db.flush()
    db.add(
        UserSkill(
            user_id=owner.id,
            skill_id=skills["python"].id,
            current_level=SkillLevel.ADVANCED,
            confidence=0.9,
            source=EvidenceSource.PROJECT,
        )
    )
    db.commit()
    ids = owner.id, other.id
    db.close()
    return ids


def test_full_flow_through_http():
    owner, other = _seed()
    with _client() as client:
        analysis = client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": owner})
        assert analysis.status_code == 200
        jd_id = analysis.json()["job_description_id"]

        created = client.post("/api/applications", json={"user_id": owner, "job_description_id": jd_id})
        assert created.status_code == 201
        app_id = created.json()["id"]
        assert created.json()["status"] == "interested"
        assert client.post("/api/applications", json={"user_id": owner, "job_description_id": jd_id}).status_code == 409

        r = client.get(f"/api/applications/{app_id}/readiness", params={"user_id": owner})
        body = r.json()
        assert r.status_code == 200 and body["status"] == "computed"
        names = {s["skill_name"]: s for s in body["skills"]}
        assert names["Python"]["match_status"] == "matched" and names["Python"]["data_kind"] == "measured"
        assert names["Docker"]["match_status"] == "missing"
        assert 0 < body["overall_match_score"] < 100 and "not a hiring probability" in body["disclaimer"]

        # analysis persisted real gaps; readiness is consistent with the analysis' own score
        assert body["overall_match_score"] == analysis.json()["overall_match_score"]

        for status, expect in [("preparing", 200), ("applied", 200), ("preparing", 409), ("interview", 200)]:
            payload = {"user_id": owner, "status": status}
            if status == "interview":
                payload["scheduled_at"] = "2030-01-01T10:00:00Z"
            assert client.patch(f"/api/applications/{app_id}/status", json=payload).status_code == expect

        detail = client.get(f"/api/applications/{app_id}", params={"user_id": owner}).json()
        assert detail["status"] == "interview" and detail["scheduled_at"].startswith("2030-01-01T10:00")
        assert detail["applied_on"] is not None and len(detail["events"]) == 4

        listing = client.get("/api/applications", params={"user_id": owner, "status": "interview"}).json()
        assert listing["total"] == 1 and listing["items"][0]["id"] == app_id
        assert client.get("/api/applications", params={"user_id": owner, "status": "offer"}).json()["total"] == 0

        note = client.post(f"/api/applications/{app_id}/notes", json={"user_id": owner, "note": "Panel on Monday"})
        assert note.status_code == 200 and note.json()["events"][-1]["event_type"] == "note_added"

        # cross-user access: 404 everywhere, existence not leaked
        for method, url, kw in [
            ("get", f"/api/applications/{app_id}", {"params": {"user_id": other}}),
            ("get", f"/api/applications/{app_id}/readiness", {"params": {"user_id": other}}),
            ("patch", f"/api/applications/{app_id}/status", {"json": {"user_id": other, "status": "withdrawn"}}),
            ("post", f"/api/applications/{app_id}/notes", {"json": {"user_id": other, "note": "x"}}),
        ]:
            assert getattr(client, method)(url, **kw).status_code == 404
        assert client.get("/api/applications", params={"user_id": other}).json()["total"] == 0
        assert client.post("/api/applications", json={"user_id": other, "job_description_id": jd_id}).status_code == 404


def test_validation_errors():
    owner, _ = _seed()
    with _client() as client:
        assert client.post("/api/applications", json={"user_id": owner}).status_code == 422  # no title/JD
        assert client.post("/api/applications", json={"job_title": "x"}).status_code == 422  # no user
        assert client.post("/api/applications", json={"user_id": owner, "job_title": "x" * 300}).status_code == 422
        created = client.post("/api/applications", json={"user_id": owner, "job_title": "Data Analyst"}).json()
        url = f"/api/applications/{created['id']}/status"
        assert client.patch(url, json={"user_id": owner, "status": "bogus"}).status_code == 422
        assert (
            client.patch(
                url, json={"user_id": owner, "status": "preparing", "scheduled_at": "2030-01-01T00:00:00Z"}
            ).status_code
            == 422
        )
        assert client.get("/api/applications", params={"user_id": owner, "limit": 0}).status_code == 422
        assert client.get("/api/applications", params={"user_id": owner, "limit": 101}).status_code == 422
        assert client.get("/api/applications/unknown", params={"user_id": owner}).status_code == 404
        r = client.get(f"/api/applications/{created['id']}/readiness", params={"user_id": owner}).json()
        assert r["status"] == "unavailable" and r["overall_match_score"] is None
        assert (
            client.post(f"/api/applications/{created['id']}/notes", json={"user_id": owner, "note": "   "}).status_code
            == 422
        )
