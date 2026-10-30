"""HTTP end-to-end: JD analysis (Phase 7) -> SkillGap rows -> roadmap
generation (Phase 8) -> persisted Roadmap/RoadmapItem rows -> fetch."""

import importlib

import pytest
from fastapi.testclient import TestClient

_JD = "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n\n" "PREFERRED QUALIFICATIONS\n- Python\n"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'roadmap_e2e.db'}")
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
    from app.models.skill import Skill, SkillPrerequisite
    from app.models.user import User

    db = session_module.SessionLocal()
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [("python", "Python"), ("machine-learning", "Machine Learning"), ("docker", "Docker")]
    }
    db.add_all(skills.values())
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    user = User(email="e2e-road@example.com", password_hash="h")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def test_jd_analysis_to_roadmap_end_to_end():
    user_id = _seed()
    with TestClient(_app()) as client:
        analysis = client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": user_id}).json()
        jd_id = analysis["job_description_id"]
        response = client.post(
            "/api/roadmaps/generate",
            json={"user_id": user_id, "job_description_id": jd_id, "hours_per_day": 2, "duration_days": 365},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        slugs = [i["skill_slug"] for i in body["items"] if i["item_type"] == "skill"]
        assert slugs.index("python") < slugs.index("machine-learning")  # prerequisite first
        assert set(slugs) == {"python", "machine-learning", "docker"}
        assert body["status"] == "active" and body["generated_by"] == "rules"
        assert body["summary"]["fits_deadline"] is True
        assert [i["order_index"] for i in body["items"]] == list(range(1, len(body["items"]) + 1))

        fetched = client.get(f"/api/roadmaps/{body['id']}")
        assert fetched.status_code == 200 and fetched.json()["id"] == body["id"]
        listing = client.get("/api/roadmaps", params={"user_id": user_id}).json()
        assert [r["id"] for r in listing] == [body["id"]]

    import app.db.session as session_module
    from app.models.roadmap import Roadmap, RoadmapItem

    db = session_module.SessionLocal()
    try:
        assert db.query(Roadmap).count() == 1
        assert db.query(RoadmapItem).count() == len(body["items"])
    finally:
        db.close()


def test_regenerate_over_http_archives_old_and_lists_newest_first():
    user_id = _seed()
    with TestClient(_app()) as client:
        client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": user_id})
        first = client.post("/api/roadmaps/generate", json={"user_id": user_id}).json()
        second = client.post("/api/roadmaps/generate", json={"user_id": user_id}).json()
        listing = client.get("/api/roadmaps", params={"user_id": user_id}).json()
    assert {r["id"]: r["status"] for r in listing} == {first["id"]: "archived", second["id"]: "active"}


def test_unknown_user_is_404():
    _seed()
    with TestClient(_app()) as client:
        assert client.post("/api/roadmaps/generate", json={"user_id": "ghost"}).status_code == 404


def test_no_open_gaps_is_409():
    user_id = _seed()
    with TestClient(_app()) as client:
        response = client.post("/api/roadmaps/generate", json={"user_id": user_id})
    assert response.status_code == 409 and "job description" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_id": "u", "hours_per_day": 0},
        {"user_id": "u", "hours_per_day": 24},
        {"user_id": "u", "duration_days": -5},
        {"user_id": "u", "duration_days": 99999},
    ],
)
def test_invalid_input_is_422(payload):
    _seed()
    with TestClient(_app()) as client:
        assert client.post("/api/roadmaps/generate", json=payload).status_code == 422


def test_get_missing_roadmap_is_404():
    _seed()
    with TestClient(_app()) as client:
        assert client.get("/api/roadmaps/nope").status_code == 404


def test_list_requires_user_id():
    _seed()
    with TestClient(_app()) as client:
        assert client.get("/api/roadmaps").status_code == 422
