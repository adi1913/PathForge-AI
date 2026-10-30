"""Phase 13: one end-to-end user journey through the whole product with real auth (register -> login -> every feature).

Every request acts as the token's own user; the journey ends by proving a second user sees none of it.
"""

import app.db.session as session_module
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from tests.test_assessments.helpers import answers_for
from tests.test_security.conftest import PASSWORD

_RESUME = (
    "Jane Smith\njane@example.com\n\nSKILLS\nPython, Docker\n\nPROJECTS\n- Built a Python API deployed with Docker\n"
)
_JD = (
    "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n- RAG\n\nPREFERRED QUALIFICATIONS\n- Python\n"
)


def _seed_catalog():
    db = session_module.SessionLocal()
    skills = {
        s: Skill(slug=s, name=n)
        for s, n in [
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
    db.commit()
    db.close()


def _levels(user_id):
    db = session_module.SessionLocal()
    try:
        return {u.skill_id: u.current_level for u in db.query(UserSkill).filter_by(user_id=user_id).all()}
    finally:
        db.close()


def test_full_user_journey_with_authentication(client, bob):
    _seed_catalog()

    # 1. register, then log in again with the password, and confirm identity from the token
    email = "journey@example.com"
    reg = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Journey"})
    assert reg.status_code == 201, reg.text
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password-123"}).status_code == 401
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=headers).json()
    uid = me["id"]
    assert me["email"] == email and "password" not in str(me).lower()
    assert client.get("/api/roadmaps", params={"user_id": uid}).status_code == 401  # no token, no access

    # 2. resume analysis -> evidence-backed user skills
    resume = client.post("/api/resume/analyze", data={"text": _RESUME}, headers=headers)
    assert resume.status_code == 200, resume.text
    after_resume = _levels(uid)
    assert len(after_resume) >= 2

    # 3. job description analysis -> skill gaps
    jd = client.post("/api/job-descriptions/analyze", data={"text": _JD}, headers=headers)
    assert jd.status_code == 200, jd.text
    body = jd.json()
    jd_id = body["job_description_id"]
    missing = {str(m).lower() for m in body["missing_skills"]}
    assert "machine learning" in " ".join(missing) or body["skill_gaps"], body

    # 4. roadmap from the gaps, progress updates, adaptive re-plan
    gen = client.post("/api/roadmaps/generate", json={"user_id": uid}, headers=headers)
    assert gen.status_code == 200, gen.text
    roadmap = gen.json()
    rid, items = roadmap["id"], roadmap["items"]
    assert items
    first = items[0]["id"]
    assert (
        client.patch(
            f"/api/roadmaps/{rid}/items/{first}/progress",
            json={"user_id": uid, "status": "in_progress"},
            headers=headers,
        ).status_code
        == 200
    )
    done = client.patch(
        f"/api/roadmaps/{rid}/items/{first}/progress",
        json={"user_id": uid, "status": "completed"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    prog = client.get(f"/api/roadmaps/{rid}/progress", params={"user_id": uid}, headers=headers)
    assert prog.status_code == 200
    replan = client.post(f"/api/roadmaps/{rid}/replan", json={"user_id": uid, "hours_per_day": 3}, headers=headers)
    assert replan.status_code == 200, replan.text
    assert any(i["id"] == first and i["status"] == "completed" for i in replan.json()["roadmap"]["items"])

    # 5. GitHub evidence
    gh = client.post(
        "/api/github/evaluate", json={"user_id": uid, "repository_url": "octocat/rag-demo"}, headers=headers
    )
    assert gh.status_code == 200, gh.text
    assert client.get("/api/github/evidence", params={"user_id": uid}, headers=headers).status_code == 200

    # 6. assessment -> evidence ledger
    gen_a = client.post(
        "/api/assessments/generate",
        headers=headers,
        json={"user_id": uid, "skill_slug": "python", "assessment_type": "quiz", "question_count": 5},
    )
    assert gen_a.status_code == 200, gen_a.text
    aid = gen_a.json()["id"]
    attempt = client.post(f"/api/assessments/{aid}/attempts", json={"user_id": uid}, headers=headers).json()
    db = session_module.SessionLocal()
    answers = [x.model_dump() for x in answers_for(db, aid, "correct")]
    db.close()
    sub = client.post(
        f"/api/assessments/attempts/{attempt['attempt_id']}/submit",
        json={"user_id": uid, "answers": answers},
        headers=headers,
    )
    assert sub.status_code == 200, sub.text
    assert "expected_answer" not in sub.text and "rubric_keywords" not in sub.text
    assert client.get("/api/assessments/evidence", params={"user_id": uid}, headers=headers).json()

    # 7. mentor
    sid = client.post("/api/mentor/sessions", json={"user_id": uid}, headers=headers).json()["id"]
    msg = client.post(
        f"/api/mentor/sessions/{sid}/messages", json={"user_id": uid, "message": "What next?"}, headers=headers
    )
    assert msg.status_code == 200, msg.text

    # 8. job application lifecycle + readiness
    app_id = client.post(
        "/api/applications", json={"user_id": uid, "job_description_id": jd_id}, headers=headers
    ).json()["id"]
    for status in ("preparing", "applied"):
        r = client.patch(f"/api/applications/{app_id}/status", json={"user_id": uid, "status": status}, headers=headers)
        assert r.status_code == 200, r.text
    bad = client.patch(
        f"/api/applications/{app_id}/status", json={"user_id": uid, "status": "interested"}, headers=headers
    )
    assert bad.status_code in (400, 409, 422)  # an illegal backwards move is refused
    assert (
        client.get(f"/api/applications/{app_id}/readiness", params={"user_id": uid}, headers=headers).status_code == 200
    )

    # No feature in the journey silently changed proficiency levels that the resume step established.
    assert {k: v for k, v in _levels(uid).items() if k in after_resume} == after_resume

    # Operability after real traffic
    assert client.get("/api/health/ready").status_code == 200
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200 and "/roadmaps/{roadmap_id}" in metrics.text and rid not in metrics.text

    # A different user sees none of it.
    other, p = bob.headers, {"user_id": bob.id}
    assert client.get(f"/api/roadmaps/{rid}", headers=other).status_code == 404
    assert client.get(f"/api/applications/{app_id}", params=p, headers=other).status_code == 404
    assert client.get(f"/api/mentor/sessions/{sid}", params=p, headers=other).status_code == 404
    assert client.get("/api/assessments/evidence", params=p, headers=other).json() == []
    assert client.get("/api/github/evidence", params=p, headers=other).json() == []


def test_completion_percentage_is_rejected_with_non_in_progress_status_and_item_unchanged(client, alice):
    """Documented rule: a percentage is only accepted with 'in_progress'. Expect 422 and no state change."""
    _seed_catalog()
    client.post("/api/resume/analyze", data={"text": _RESUME}, headers=alice.headers)
    client.post("/api/job-descriptions/analyze", data={"text": _JD}, headers=alice.headers)
    roadmap = client.post("/api/roadmaps/generate", json={"user_id": alice.id}, headers=alice.headers).json()
    rid, item = roadmap["id"], roadmap["items"][0]
    url = f"/api/roadmaps/{rid}/items/{item['id']}/progress"

    bad = client.patch(
        url, json={"user_id": alice.id, "status": "completed", "completion_percentage": 100}, headers=alice.headers
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "completion_percentage is only accepted together with status 'in_progress'"
    unchanged = client.get(f"/api/roadmaps/{rid}", headers=alice.headers).json()["items"][0]
    assert unchanged["status"] == item["status"] and unchanged["completion_percentage"] == item["completion_percentage"]

    ok = client.patch(
        url, json={"user_id": alice.id, "status": "in_progress", "completion_percentage": 40}, headers=alice.headers
    )
    assert ok.status_code == 200, ok.text
    assert (
        client.patch(url, json={"user_id": alice.id, "status": "completed"}, headers=alice.headers).status_code == 200
    )
