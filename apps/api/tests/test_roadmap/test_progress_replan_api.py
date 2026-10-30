"""HTTP end-to-end for Phase 9: JD analysis -> roadmap -> progress updates ->
progress report -> adaptive re-plan -> fetch, plus ownership and validation."""

import importlib

import pytest
from fastapi.testclient import TestClient

_JD = "ML Engineer at Globex\n\nREQUIREMENTS\n- Machine Learning\n- Docker\n\nPREFERRED QUALIFICATIONS\n- Python\n"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'replan_e2e.db'}")
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


def _seed_users():
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
    owner = User(email="owner@example.com", password_hash="h")
    other = User(email="intruder@example.com", password_hash="h")
    db.add_all([owner, other])
    db.commit()
    ids = owner.id, other.id
    db.close()
    return ids


def _roadmap(client, owner):
    client.post("/api/job-descriptions/analyze", data={"text": _JD, "user_id": owner})
    return client.post("/api/roadmaps/generate", json={"user_id": owner, "hours_per_day": 2}).json()


def _item(roadmap, slug):
    return next(i for i in roadmap["items"] if i["skill_slug"] == slug and i["item_type"] == "skill")


def _patch(client, roadmap, item, user, **body):
    return client.patch(f"/api/roadmaps/{roadmap['id']}/items/{item['id']}/progress", json={"user_id": user, **body})


def test_progress_and_replan_end_to_end_with_persistence():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        python, ml = _item(roadmap, "python"), _item(roadmap, "machine-learning")

        started = _patch(client, roadmap, python, owner, status="in_progress", completion_percentage=40)
        assert started.status_code == 200 and started.json()["item"]["completion_percentage"] == 40
        done = _patch(client, roadmap, python, owner, status="completed")
        assert done.json()["summary"]["completed"] == 1

        warned = _patch(client, roadmap, ml, owner, status="in_progress")  # python done -> no warning
        assert warned.status_code == 200 and warned.json()["warnings"] == []

        progress = client.get(f"/api/roadmaps/{roadmap['id']}/progress", params={"user_id": owner}).json()
        assert progress["summary"]["completed"] == 1 and progress["summary"]["in_progress"] == 1
        py_progress = next(i for i in progress["items"] if i["skill_slug"] == "python")
        assert py_progress["started_at"] and py_progress["completed_at"]
        assert progress["recent_events"][0]["event_type"] == "item_started"

        replan = client.post(
            f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner, "hours_per_day": 4, "duration_days": 120}
        )
        assert replan.status_code == 200, replan.text
        body = replan.json()
        assert body["replan"]["resolved_skills"] == 1 and body["replan"]["remaining_skills"] == 2
        assert body["replan"]["fits_deadline"] is True
        assert body["roadmap"]["id"] == roadmap["id"]
        order = [i["skill_slug"] for i in body["roadmap"]["items"] if i["item_type"] == "skill"]
        assert order[0] == "python" and order.index("machine-learning") < order.index("docker")

    # a brand new app instance reads the same persisted state
    with TestClient(_app()) as client:
        fetched = client.get(f"/api/roadmaps/{roadmap['id']}").json()
        assert _item(fetched, "python")["status"] == "completed"
        assert _item(fetched, "machine-learning")["status"] == "in_progress"
        assert [i["order_index"] for i in fetched["items"]] == [i["order_index"] for i in body["roadmap"]["items"]]
        again = client.get(f"/api/roadmaps/{roadmap['id']}/progress", params={"user_id": owner}).json()
        assert again["replan_count"] == 1


def test_replan_twice_over_http_is_stable():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        first = client.post(f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner, "hours_per_day": 2}).json()
        second = client.post(
            f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner, "hours_per_day": 2}
        ).json()
        assert [(i["id"], i["order_index"], i["week_number"]) for i in first["roadmap"]["items"]] == [
            (i["id"], i["order_index"], i["week_number"]) for i in second["roadmap"]["items"]
        ]


def test_infeasible_deadline_reported():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        body = client.post(
            f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner, "hours_per_day": 1, "duration_days": 3}
        ).json()
    assert body["replan"]["fits_deadline"] is False
    assert any("deadline" in w for w in body["roadmap"]["warnings"])
    assert body["replan"]["remaining_skills"] == 3


def test_other_user_cannot_read_update_or_replan():
    owner, intruder = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        item = _item(roadmap, "python")
        assert _patch(client, roadmap, item, intruder, status="completed").status_code == 404
        assert client.get(f"/api/roadmaps/{roadmap['id']}/progress", params={"user_id": intruder}).status_code == 404
        replan = client.post(f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": intruder})
        assert replan.status_code == 404
        assert _item(client.get(f"/api/roadmaps/{roadmap['id']}").json(), "python")["status"] == "not_started"


def test_unknown_roadmap_and_item_are_404():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        assert client.get("/api/roadmaps/nope/progress", params={"user_id": owner}).status_code == 404
        assert client.post("/api/roadmaps/nope/replan", json={"user_id": owner}).status_code == 404
        bad_item = client.patch(
            f"/api/roadmaps/{roadmap['id']}/items/nope/progress", json={"user_id": owner, "status": "completed"}
        )
        assert bad_item.status_code == 404


def test_invalid_transition_is_409_and_invalid_input_is_422():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        python = _item(roadmap, "python")
        assert _patch(client, roadmap, python, owner, status="completed").status_code == 200
        assert _patch(client, roadmap, python, owner, status="blocked").status_code == 409  # completed -> blocked
        assert _patch(client, roadmap, python, owner, status="mastered").status_code == 422
        assert (
            _patch(client, roadmap, python, owner, status="in_progress", completion_percentage=150).status_code == 422
        )
        assert _patch(client, roadmap, python, owner, status="reopen").status_code == 422
        assert (
            client.patch(
                f"/api/roadmaps/{roadmap['id']}/items/{python['id']}/progress", json={"status": "completed"}
            ).status_code
            == 422
        )  # user_id required
        docker = _item(roadmap, "docker")
        assert _patch(client, roadmap, docker, owner, status="completed", completion_percentage=50).status_code == 422
        assert (
            _patch(client, roadmap, docker, owner, status="in_progress", completion_percentage=100).status_code == 422
        )


@pytest.mark.parametrize(
    "payload", [{"hours_per_day": 0}, {"hours_per_day": 17}, {"duration_days": 0}, {"duration_days": 2000}]
)
def test_replan_invalid_availability_is_422(payload):
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        assert (
            client.post(f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner, **payload}).status_code == 422
        )


def test_all_completed_roadmap_replan_is_409():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        roadmap = _roadmap(client, owner)
        for slug in ("python", "machine-learning", "docker"):
            assert _patch(client, roadmap, _item(roadmap, slug), owner, status="completed").status_code == 200
        assert client.get(f"/api/roadmaps/{roadmap['id']}").json()["status"] == "completed"
        response = client.post(f"/api/roadmaps/{roadmap['id']}/replan", json={"user_id": owner})
        assert response.status_code == 409 and "nothing left" in response.json()["detail"]


def test_archived_roadmap_rejects_progress_and_replan():
    owner, _ = _seed_users()
    with TestClient(_app()) as client:
        old = _roadmap(client, owner)
        new = client.post("/api/roadmaps/generate", json={"user_id": owner, "hours_per_day": 2}).json()  # archives old
        assert new["id"] != old["id"]
        replan = client.post(f"/api/roadmaps/{old['id']}/replan", json={"user_id": owner})
        assert replan.status_code == 409 and "archived" in replan.json()["detail"]
        assert _patch(client, old, _item(old, "python"), owner, status="in_progress").status_code == 409
        assert _patch(client, new, _item(new, "python"), owner, status="in_progress").status_code == 200
