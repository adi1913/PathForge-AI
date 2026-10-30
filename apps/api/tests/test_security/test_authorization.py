"""Every protected route rejects anonymous callers; a token can only act for its own user."""

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security.tokens import AUDIENCE, ISSUER
from tests.test_security.conftest import SECRET

PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/health/ready"),
    ("GET", "/api/metrics"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
}
METHODS = {"get", "post", "patch", "put", "delete"}


def _operations(schema):
    for path, item in schema["paths"].items():
        for method, op in item.items():
            if method in METHODS:
                yield method.upper(), path, op


def _concrete(path):
    return re.sub(r"\{[^}]+\}", "x", path)


def _protected(client):
    schema = client.get("/api/openapi.json").json()
    ops = [(m, p, op) for m, p, op in _operations(schema) if (m, p) not in PUBLIC]
    assert len(ops) >= 30  # guards against the sweep silently covering nothing
    return schema, ops


def _body_props(schema, op):
    out = {}
    for ctype, media in op.get("requestBody", {}).get("content", {}).items():
        sch = media["schema"]
        if "$ref" in sch:
            sch = schema["components"]["schemas"][sch["$ref"].split("/")[-1]]
        out[ctype] = sch.get("properties", {})
    return out


def test_every_protected_route_requires_authentication(client):
    _, ops = _protected(client)
    for method, path, _ in ops:
        resp = client.request(method, _concrete(path))
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"
        assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["Bearer", "Bearer ", "Bearer not.a.jwt", "Basic dXNlcjpwYXNz", "bearer-without-space", "Token abc"],
)
def test_malformed_credentials_rejected_on_every_route(client, header):
    _, ops = _protected(client)
    for method, path, _ in ops:
        resp = client.request(method, _concrete(path), headers={"Authorization": header})
        assert resp.status_code == 401, f"{method} {path} {header!r} -> {resp.status_code}"


def _forged(user_id, **over):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        **over,
    }
    return jwt.encode(claims, over.pop("key", SECRET), algorithm="HS256")


def test_expired_wrong_audience_wrong_key_and_tampered_tokens_get_401(client, alice):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    bad = [
        _forged(alice.id, exp=int(past.timestamp())),
        _forged(alice.id, aud="other"),
        _forged(alice.id, iss="other"),
        jwt.encode({"sub": alice.id}, "y" * 64, algorithm="HS256"),
        alice.token[:-3] + ("AAA" if not alice.token.endswith("AAA") else "BBB"),
        jwt.encode({"sub": alice.id, "iss": ISSUER, "aud": AUDIENCE}, None, algorithm="none"),
    ]
    for token in bad:
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        resp = client.get("/api/roadmaps", params={"user_id": alice.id}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


def test_valid_token_for_unknown_subject_is_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {_forged('ghost-user')}"})
    assert resp.status_code == 401


def test_user_id_of_another_user_is_403_everywhere_it_is_accepted(client, alice, bob):
    schema, ops = _protected(client)
    checked = 0
    for method, path, op in ops:
        url = _concrete(path)
        if any(p["name"] == "user_id" and p["in"] == "query" for p in op.get("parameters", [])):
            resp = client.request(method, url, params={"user_id": bob.id}, headers=alice.headers)
            assert resp.status_code == 403, f"query {method} {path} -> {resp.status_code}"
            checked += 1
        for ctype, props in _body_props(schema, op).items():
            if "user_id" not in props:
                continue
            if ctype == "application/json":
                resp = client.request(method, url, json={"user_id": bob.id}, headers=alice.headers)
            else:
                resp = client.request(method, url, data={"user_id": bob.id}, headers=alice.headers)
            assert resp.status_code == 403, f"body {method} {path} -> {resp.status_code}"
            checked += 1
    assert checked >= 28  # 13 query + 15 body user_id entry points at the time of writing


def test_own_user_id_is_accepted_and_foreign_ids_are_404_not_403(client, alice, bob):
    own = client.get("/api/roadmaps", params={"user_id": alice.id}, headers=alice.headers)
    assert own.status_code == 200 and own.json() == []
    # alice's own id, but a resource that does not exist / belongs to nobody she owns -> 404
    for url in (
        "/api/applications/nope",
        "/api/assessments/nope",
        "/api/mentor/sessions/nope",
        "/api/github/evaluations/nope",
        "/api/roadmaps/nope/progress",
    ):
        assert client.get(url, params={"user_id": alice.id}, headers=alice.headers).status_code == 404, url


def test_roadmap_by_id_has_owner_check(client, alice, bob):
    import app.db.session as s
    from app.models.roadmap import Roadmap

    db = s.SessionLocal()
    row = Roadmap(user_id=alice.id, title="Alice plan", duration_days=10)
    db.add(row)
    db.commit()
    rid = row.id
    db.close()
    assert client.get(f"/api/roadmaps/{rid}", headers=alice.headers).status_code == 200
    foreign = client.get(f"/api/roadmaps/{rid}", headers=bob.headers)
    missing = client.get("/api/roadmaps/does-not-exist", headers=bob.headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()  # existence is not revealed
    assert client.get(f"/api/roadmaps/{rid}").status_code == 401


def test_agent_run_defaults_to_token_user_and_rejects_foreign_user(client, alice, bob):
    forged = client.post("/api/agent/run", json={"message": "hi", "user_id": bob.id}, headers=alice.headers)
    assert forged.status_code == 403
    anon = client.post("/api/agent/run", json={"message": "hi"})
    assert anon.status_code == 401


def test_rag_ingest_is_admin_only_and_search_needs_login(client, alice, admin):
    doc = {"documents": [{"title": "t", "content": "some content about rag", "source": "unit"}]}
    assert client.post("/api/rag/ingest", json=doc).status_code == 401
    assert client.post("/api/rag/ingest", json=doc, headers=alice.headers).status_code == 403
    assert client.post("/api/rag/search", json={"query": "rag"}).status_code == 401
    assert client.post("/api/rag/search", json={"query": "rag"}, headers=alice.headers).status_code != 401
    assert client.post("/api/rag/ingest", json=doc, headers=admin.headers).status_code != 403


def test_is_admin_flag_comes_from_allow_list_only(client, alice, admin):
    assert client.get("/api/auth/me", headers=alice.headers).json()["is_admin"] is False
    assert client.get("/api/auth/me", headers=admin.headers).json()["is_admin"] is True
