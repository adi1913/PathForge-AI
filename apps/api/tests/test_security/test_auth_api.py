import logging

from app.models.user import User
from tests.test_security.conftest import PASSWORD, register


def _bad_login(client, email):
    return client.post("/api/auth/login", json={"email": email, "password": "wrong-password-1"})


def _db():
    import app.db.session as s

    return s.SessionLocal()


def test_register_returns_token_and_user_without_secrets(client):
    resp = register(client, "New.User@Example.com", name="New")
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["email"] == "new.user@example.com" and body["user"]["display_name"] == "New"
    assert body["user"]["is_admin"] is False
    assert PASSWORD not in resp.text and "password_hash" not in resp.text and "scrypt" not in resp.text


def test_password_stored_hashed(client):
    register(client, "a@example.com")
    db = _db()
    stored = db.query(User).one().password_hash
    db.close()
    assert stored.startswith("scrypt$") and PASSWORD not in stored


def test_duplicate_email_conflicts_case_insensitively(client):
    assert register(client, "dup@example.com").status_code == 201
    assert register(client, "DUP@example.com").status_code == 409


def test_password_length_rules(client):
    assert register(client, "a@example.com", password="short").status_code == 422
    assert register(client, "b@example.com", password="x" * 129).status_code == 422


def test_invalid_email_and_validation_error_never_echo_password(client):
    resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "hunter2-hunter2"})
    assert resp.status_code == 422
    assert "hunter2-hunter2" not in resp.text and "input" not in resp.text


def test_registration_can_be_disabled(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    get_settings.cache_clear()
    assert register(client, "a@example.com").status_code == 403


def test_login_success_and_me(client, alice):
    resp = client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == alice.id


def test_login_failures_are_indistinguishable(client, alice):
    wrong = client.post("/api/auth/login", json={"email": alice.email, "password": "wrong-password-1"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid credentials"}


def test_inactive_user_cannot_login_or_use_existing_token(client, alice):
    db = _db()
    db.query(User).filter_by(id=alice.id).one().is_active = False
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD})
    assert login.status_code == 401 and login.json() == {"detail": "Invalid credentials"}
    assert client.get("/api/auth/me", headers=alice.headers).status_code == 401
    assert client.get("/api/roadmaps", params={"user_id": alice.id}, headers=alice.headers).status_code == 401


def test_token_for_deleted_user_rejected(client, alice):
    db = _db()
    db.delete(db.get(User, alice.id))
    db.commit()
    db.close()
    assert client.get("/api/auth/me", headers=alice.headers).status_code == 401


def test_login_throttle_returns_429_with_retry_after_and_is_per_key(client, alice, bob, monkeypatch):
    from app.api.routes import auth as auth_routes
    from app.core.config import get_settings

    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    get_settings.cache_clear()
    auth_routes.reset_throttles()
    for _ in range(3):
        assert (
            client.post("/api/auth/login", json={"email": alice.email, "password": "wrong-password-1"}).status_code
            == 401
        )
    blocked = client.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert client.post("/api/auth/login", json={"email": bob.email, "password": PASSWORD}).status_code == 200


def test_success_clears_failure_counter(client, alice, monkeypatch):
    from app.api.routes import auth as auth_routes
    from app.core.config import get_settings

    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    get_settings.cache_clear()
    auth_routes.reset_throttles()
    for _ in range(2):
        client.post("/api/auth/login", json={"email": alice.email, "password": "wrong-password-1"})
    assert client.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD}).status_code == 200
    for _ in range(2):
        assert (
            client.post("/api/auth/login", json={"email": alice.email, "password": "wrong-password-1"}).status_code
            == 401
        )


def test_register_throttle(client):
    from app.api.routes.auth import REGISTER_MAX_PER_WINDOW

    codes = [register(client, f"user{i}@example.com").status_code for i in range(REGISTER_MAX_PER_WINDOW + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {201}


def test_auth_events_never_log_credentials(client, caplog):
    caplog.set_level(logging.DEBUG)
    register(client, "log@example.com")
    client.post("/api/auth/login", json={"email": "log@example.com", "password": "wrong-password-1"})
    ok = client.post("/api/auth/login", json={"email": "log@example.com", "password": PASSWORD}).json()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert PASSWORD not in text and "wrong-password-1" not in text and ok["access_token"] not in text
