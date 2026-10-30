"""Real authenticated end-to-end runs: identity from the token (no user_id sent), strict isolation between users."""

from app.models.enums import EvidenceSource, SkillLevel
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from tests.test_assessments.helpers import answers_for

_JD = "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n\nPREFERRED QUALIFICATIONS\n- Python\n"


def _seed_skills(owner_id):
    import app.db.session as s

    db = s.SessionLocal()
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [
            ("python", "Python"),
            ("machine-learning", "Machine Learning"),
            ("rag", "RAG"),
            ("docker", "Docker"),
        ]
    }
    db.add_all(skills.values())
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    db.add(SkillPrerequisite(skill_id=skills["rag"].id, prerequisite_skill_id=skills["machine-learning"].id))
    db.add(
        UserSkill(
            user_id=owner_id,
            skill_id=skills["python"].id,
            current_level=SkillLevel.ADVANCED,
            confidence=0.9,
            source=EvidenceSource.PROJECT,
        )
    )
    db.add(
        UserSkill(
            user_id=owner_id,
            skill_id=skills["rag"].id,
            current_level=SkillLevel.INTERMEDIATE,
            confidence=0.5,
            source=EvidenceSource.RESUME,
            evidence=[{"type": "resume", "text": "x", "section": "skills"}],
        )
    )
    db.commit()
    db.close()


def test_job_description_application_readiness_and_roadmap_flow(client, alice, bob):
    _seed_skills(alice.id)
    a = alice.headers
    analysis = client.post("/api/job-descriptions/analyze", data={"text": _JD}, headers=a)  # no user_id: from token
    assert analysis.status_code == 200, analysis.text
    jd_id = analysis.json()["job_description_id"]

    created = client.post("/api/applications", json={"job_description_id": jd_id, "user_id": alice.id}, headers=a)
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    assert (
        client.get(f"/api/applications/{app_id}/readiness", params={"user_id": alice.id}, headers=a).status_code == 200
    )

    roadmap = client.post("/api/roadmaps/generate", json={"user_id": alice.id}, headers=a)
    assert roadmap.status_code == 200, roadmap.text
    rid = roadmap.json()["id"]
    assert client.get(f"/api/roadmaps/{rid}", headers=a).status_code == 200

    b = bob.headers
    p = {"user_id": bob.id}
    assert client.get(f"/api/applications/{app_id}", params=p, headers=b).status_code == 404
    assert client.get(f"/api/applications/{app_id}/readiness", params=p, headers=b).status_code == 404
    assert (
        client.patch(f"/api/applications/{app_id}/status", json={**p, "status": "applied"}, headers=b).status_code
        == 404
    )
    assert client.post(f"/api/applications/{app_id}/notes", json={**p, "note": "x"}, headers=b).status_code == 404
    assert client.get("/api/applications", params=p, headers=b).json()["total"] == 0
    assert client.post("/api/applications", json={**p, "job_description_id": jd_id}, headers=b).status_code == 404
    assert client.get(f"/api/roadmaps/{rid}", headers=b).status_code == 404
    assert client.get(f"/api/roadmaps/{rid}/progress", params=p, headers=b).status_code == 404
    assert client.get("/api/roadmaps", params=p, headers=b).json() == []
    # still sees her own data afterwards
    assert client.get(f"/api/applications/{app_id}", params={"user_id": alice.id}, headers=a).status_code == 200


def test_assessment_flow_and_isolation(client, alice, bob):
    _seed_skills(alice.id)
    a, b = alice.headers, bob.headers
    gen = client.post(
        "/api/assessments/generate",
        json={"user_id": alice.id, "skill_slug": "rag", "assessment_type": "quiz", "question_count": 5},
        headers=a,
    )
    assert gen.status_code == 200, gen.text
    aid = gen.json()["id"]
    attempt = client.post(f"/api/assessments/{aid}/attempts", json={"user_id": alice.id}, headers=a)
    assert attempt.status_code == 200
    attempt_id = attempt.json()["attempt_id"]

    p = {"user_id": bob.id}
    assert client.get(f"/api/assessments/{aid}", params=p, headers=b).status_code == 404
    assert client.post(f"/api/assessments/{aid}/attempts", json=p, headers=b).status_code == 404
    import app.db.session as s

    db = s.SessionLocal()
    answers = [x.model_dump() for x in answers_for(db, aid, "correct")]
    db.close()
    assert (
        client.post(
            f"/api/assessments/attempts/{attempt_id}/submit", json={**p, "answers": answers}, headers=b
        ).status_code
        == 404
    )
    assert client.get("/api/assessments", params=p, headers=b).json() == []
    assert client.get("/api/assessments/evidence", params=p, headers=b).json() == []

    done = client.post(
        f"/api/assessments/attempts/{attempt_id}/submit",
        json={"user_id": alice.id, "answers": answers},
        headers=a,
    )
    assert done.status_code == 200, done.text
    assert len(client.get("/api/assessments/evidence", params={"user_id": alice.id}, headers=a).json()) == 1
    assert client.get("/api/assessments/evidence", params=p, headers=b).json() == []


def test_mentor_flow_and_isolation(client, alice, bob):
    a, b = alice.headers, bob.headers
    session = client.post("/api/mentor/sessions", json={"user_id": alice.id}, headers=a)
    assert session.status_code in (200, 201), session.text
    sid = session.json()["id"]
    msg = client.post(
        f"/api/mentor/sessions/{sid}/messages", json={"user_id": alice.id, "message": "Explain RAG"}, headers=a
    )
    assert msg.status_code == 200, msg.text
    p = {"user_id": bob.id}
    assert client.get(f"/api/mentor/sessions/{sid}", params=p, headers=b).status_code == 404
    assert (
        client.post(f"/api/mentor/sessions/{sid}/messages", json={**p, "message": "hi"}, headers=b).status_code == 404
    )
    assert client.get("/api/mentor/sessions", params=p, headers=b).json() == []


def test_github_evidence_flow_and_isolation(client, alice, bob):
    _seed_skills(alice.id)
    a, b = alice.headers, bob.headers
    ev = client.post(
        "/api/github/evaluate", json={"user_id": alice.id, "repository_url": "octocat/rag-demo"}, headers=a
    )
    assert ev.status_code == 200, ev.text
    eid = ev.json()["evaluation_id"]
    p = {"user_id": bob.id}
    assert client.get(f"/api/github/evaluations/{eid}", params=p, headers=b).status_code == 404
    assert client.get("/api/github/repositories", params=p, headers=b).json() == []
    assert client.get("/api/github/evidence", params=p, headers=b).json() == []
    assert client.get(f"/api/github/evaluations/{eid}", params={"user_id": alice.id}, headers=a).status_code == 200


def test_resume_analysis_uses_token_identity(client, alice, bob):
    _seed_skills(alice.id)
    text = "Jane Smith\njane@example.com\n\nSKILLS\nPython, Docker\n"
    resp = client.post("/api/resume/analyze", data={"text": text}, headers=alice.headers)
    assert resp.status_code == 200, resp.text
    import app.db.session as s

    db = s.SessionLocal()
    mine = db.query(UserSkill).filter_by(user_id=alice.id).count()
    theirs = db.query(UserSkill).filter_by(user_id=bob.id).count()
    db.close()
    assert mine >= 2 and theirs == 0
    assert (
        client.post("/api/resume/analyze", data={"text": text, "user_id": alice.id}, headers=bob.headers).status_code
        == 403
    )
