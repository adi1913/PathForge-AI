"""Fixtures for the Phase 12 security tests: auth is switched ON (the rest of the suite runs trusted-caller mode)."""

import importlib

import pytest
from fastapi.testclient import TestClient

SECRET = "test-secret-key-0123456789-abcdefghijklmnop"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def secure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'security.db'}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")
    monkeypatch.setenv("ADMIN_EMAILS", '["admin@example.com"]')
    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    from app.api.routes import auth as auth_routes
    from app.observability.metrics import metrics

    auth_routes.reset_throttles()
    metrics.reset()
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)
    get_settings.cache_clear()
    auth_routes.reset_throttles()


@pytest.fixture()
def app():
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def register(client, email, password=PASSWORD, name=None):
    body = {"email": email, "password": password}
    if name:
        body["display_name"] = name
    return client.post("/api/auth/register", json=body)


class Account:
    def __init__(self, client, email):
        resp = register(client, email)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        self.email = email
        self.token = data["access_token"]
        self.id = data["user"]["id"]
        self.headers = {"Authorization": f"Bearer {self.token}"}


@pytest.fixture()
def alice(client):
    return Account(client, "alice@example.com")


@pytest.fixture()
def bob(client):
    return Account(client, "bob@example.com")


@pytest.fixture()
def admin(client):
    return Account(client, "admin@example.com")
