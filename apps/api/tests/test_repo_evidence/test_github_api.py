"""HTTP end-to-end for Phase 11 through the real demo GitHub MCP server subprocess:

HTTP -> FastAPI -> RepositoryCollector -> MCPClientManager -> MCP protocol (stdio)
-> GitHub MCP server -> DemoGitHubProvider -> evidence rows -> readiness
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'gh_e2e.db'}")
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
    from app.models.skill import Skill, UserSkill
    from app.models.user import User

    db = session_module.SessionLocal()
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [("python", "Python"), ("fastapi", "FastAPI"), ("docker", "Docker"), ("qdrant", "Qdrant")]
    }
    db.add_all(skills.values())
    owner = User(email="o@example.com", password_hash="h")
    other = User(email="x@example.com", password_hash="h")
    db.add_all([owner, other])
    db.flush()
    db.add(
        UserSkill(
            user_id=owner.id,
            skill_id=skills["python"].id,
            current_level=SkillLevel.INTERMEDIATE,
            confidence=0.9,
            source=EvidenceSource.MANUAL,
        )
    )
    db.commit()
    ids = owner.id, other.id
    db.close()
    return ids


def test_evaluate_through_real_mcp_then_list_and_isolate():
    owner, other = _seed()
    with _client() as client:
        r = client.post("/api/github/evaluate", json={"user_id": owner, "repository_url": "octocat/rag-demo"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["data_source"] == "demo" and body["reused_repository"] is False
        by = {g["skill_slug"]: g for g in body["evidence"]}
        assert {"python", "fastapi", "qdrant", "docker"} <= set(by)
        assert body["signals"]["has_readme"] and body["signals"]["has_dockerfile"]
        assert any("DEMO data" in lim for lim in body["limitations"])
        assert "not verified proficiency" in body["note"]
        assert "repository metadata" in body["inspected"] and "pyproject.toml" in body["inspected"]

        again = client.post(
            "/api/github/evaluate", json={"user_id": owner, "repository_url": "https://github.com/octocat/rag-demo"}
        )
        assert again.json()["reused_repository"] is True

        repos = client.get("/api/github/repositories", params={"user_id": owner}).json()
        assert len(repos) == 1 and repos[0]["latest_evaluation_id"] == again.json()["evaluation_id"]
        ev = client.get("/api/github/evidence", params={"user_id": owner, "skill": "qdrant"}).json()
        assert len(ev) == 1 and ev[0]["repository"] == "octocat/rag-demo" and ev[0]["data_source"] == "demo"
        got = client.get(f"/api/github/evaluations/{body['evaluation_id']}", params={"user_id": owner})
        assert got.status_code == 200 and got.json()["evaluation_id"] == body["evaluation_id"]

        # another user cannot read it and sees nothing
        assert (
            client.get(f"/api/github/evaluations/{body['evaluation_id']}", params={"user_id": other}).status_code == 404
        )
        assert client.get("/api/github/evidence", params={"user_id": other}).json() == []
        assert client.get("/api/github/repositories", params={"user_id": other}).json() == []


def test_no_proficiency_change_and_readiness_shows_evidence():
    import app.db.session as session_module
    from app.models.skill import UserSkill

    owner, _ = _seed()
    jd = "Backend Engineer at Initech\n\nREQUIREMENTS\n- Python\n- FastAPI\n- Docker\n"
    with _client() as client:
        analysis = client.post("/api/job-descriptions/analyze", data={"text": jd, "user_id": owner}).json()
        client.post("/api/github/evaluate", json={"user_id": owner, "repository_url": "octocat/rag-demo"})
        app_id = client.post(
            "/api/applications", json={"user_id": owner, "job_description_id": analysis["job_description_id"]}
        ).json()["id"]
        readiness = client.get(f"/api/applications/{app_id}/readiness", params={"user_id": owner}).json()
        assert readiness["overall_match_score"] == analysis["overall_match_score"]  # score is the Phase 7 score
        by = {s["skill_name"]: s for s in readiness["skills"]}
        assert by["FastAPI"]["match_status"] == "missing" and by["FastAPI"]["github_evidence"]
        assert by["Python"]["github_evidence"][0]["data_source"] == "demo"

    db = session_module.SessionLocal()
    rows = db.query(UserSkill).all()
    assert [(r.current_level.value, r.confidence) for r in rows] == [("intermediate", 0.9)]
    db.close()


def test_error_responses_are_fixed_messages():
    owner, _ = _seed()
    with _client() as client:
        for bad in ("https://evil.example/a/b", "a/../b", "nonsense", ""):
            r = client.post("/api/github/evaluate", json={"user_id": owner, "repository_url": bad})
            assert r.status_code == 422
        r = client.post("/api/github/evaluate", json={"user_id": "ghost", "repository_url": "a/b"})
        assert r.status_code == 404 and r.json()["detail"] == "User not found"
        assert client.get("/api/github/evaluations/missing", params={"user_id": owner}).status_code == 404
        assert client.post("/api/github/evaluate", json={"repository_url": "a/b"}).status_code == 422
