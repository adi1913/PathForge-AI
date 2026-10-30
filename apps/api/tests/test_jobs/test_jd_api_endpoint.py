"""HTTP -> FastAPI -> JD service -> normalization -> UserSkill retrieval ->
gap engine -> DB persistence -> structured response. No mocking of the
analyzer or the gap engine."""

import importlib

import pytest
from fastapi.testclient import TestClient

_JD = (
    "Backend Engineer at Globex\n\nREQUIREMENTS\n- Strong experience with Python\n- Docker\n\n"
    "PREFERRED QUALIFICATIONS\n- Kubernetes\n"
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'jd_e2e.db'}")
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


def _seed(with_user=True):
    import app.db.session as session_module
    from app.models.enums import EvidenceSource, SkillLevel
    from app.models.skill import Skill, UserSkill
    from app.models.user import User

    db = session_module.SessionLocal()
    skills = {slug: Skill(slug=slug, name=name) for slug, name in [("python", "Python"), ("docker", "Docker")]}
    db.add_all(skills.values())
    user_id = None
    if with_user:
        user = User(email="e2e-jd@example.com", password_hash="h")
        db.add(user)
        db.flush()
        db.add(
            UserSkill(
                user_id=user.id,
                skill_id=skills["python"].id,
                current_level=SkillLevel.BEGINNER,
                confidence=0.7,
                source=EvidenceSource.RESUME,
                evidence=[],
            )
        )
        user_id = user.id
    db.commit()
    db.close()
    return user_id


def test_end_to_end_gap_analysis_and_db_rows():
    user_id = _seed()
    with TestClient(_app()) as client:
        response = client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": user_id})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["job_description"]["company"] == "Globex"
    assert [s["normalized_skill_name"] for s in body["job_description"]["required_skills"]] == ["Python", "Docker"]
    assert body["job_description"]["unmatched_skills"] == ["kubernetes"]
    assert [g["skill_slug"] for g in body["weak_skills"]] == ["python"]
    assert [g["skill_slug"] for g in body["missing_skills"]] == ["docker"]
    assert (
        body["weak_skills"][0]["expected_level"] == "advanced" and body["weak_skills"][0]["current_level"] == "beginner"
    )
    assert body["missing_skills"][0]["reasoning"]
    scores = [g["priority_score"] for g in body["skill_gaps"]]
    assert scores == sorted(scores, reverse=True)
    assert 0 <= body["overall_match_score"] < 50

    import app.db.session as session_module
    from app.models.job_description import JobDescription, JobDescriptionSkill
    from app.models.skill import Skill
    from app.models.skill_gap import SkillGap

    db = session_module.SessionLocal()
    try:
        assert db.query(JobDescription).filter_by(id=body["job_description_id"]).one().user_id == user_id
        assert db.query(JobDescriptionSkill).count() == 2
        assert {g.skill.slug for g in db.query(SkillGap).all()} == {"python", "docker"}
        assert db.query(Skill).count() == 2  # unmatched kubernetes was NOT inserted
    finally:
        db.close()


def test_reanalysis_is_stable_over_http():
    user_id = _seed()
    with TestClient(_app()) as client:
        first = client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": user_id}).json()
        second = client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": user_id}).json()
    assert first["job_description_id"] == second["job_description_id"]
    assert first["overall_match_score"] == second["overall_match_score"]


def test_without_user_returns_no_gap_comparison():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        response = client.post("/api/job-descriptions/analyze", data={"text": _JD})
    body = response.json()
    assert response.status_code == 200
    assert body["overall_match_score"] is None and body["skill_gaps"] == []
    assert body["job_description"]["required_skills"]


def test_file_upload_markdown():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        response = client.post(
            "/api/job-descriptions/analyze",
            files={"file": ("../../evil/jd.md", b"# Dev\n\n## Requirements\n- Python\n", "text/markdown")},
        )
    assert response.status_code == 200
    assert response.json()["job_description"]["parser_metadata"]["parser_used"] == "MarkdownResumeParser"


def test_missing_input_is_422():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        assert client.post("/api/job-descriptions/analyze", data={}).status_code == 422


def test_oversized_file_is_413():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        response = client.post(
            "/api/job-descriptions/analyze", files={"file": ("jd.txt", b"x" * 2_000_001, "text/plain")}
        )
    assert response.status_code == 413


def test_oversized_text_rejected():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        response = client.post("/api/job-descriptions/analyze", data={"text": "x" * 2_000_001})
    assert response.status_code in (400, 413)


def test_unsupported_pdf_is_400():
    _seed(with_user=False)
    with TestClient(_app()) as client:
        response = client.post(
            "/api/job-descriptions/analyze", files={"file": ("jd.pdf", b"%PDF-1.4", "application/pdf")}
        )
    assert response.status_code == 400
