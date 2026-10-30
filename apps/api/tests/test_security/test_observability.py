import json
import logging

import pytest

from app.core.config import Settings
from app.observability.logging import REDACTED, RedactingFormatter, RedactingJsonFormatter, redact
from app.security.validation import validate_settings
from tests.test_security.conftest import PASSWORD, SECRET

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1MSJ9.c2lnbmF0dXJlLXZhbHVl"


# ---- redaction -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line,secret",
    [
        ("Authorization: Bearer abcdef1234567890", "abcdef1234567890"),
        (f"token seen {JWT}", JWT),
        ("key sk-ant-api03-abcdefghijklmnop", "abcdefghijklmnop"),
        ("login password=hunter2hunter2 ok", "hunter2hunter2"),
        ('{"password": "hunter2hunter2"}', "hunter2hunter2"),
        ("api_key: 12345-secret-value", "12345-secret-value"),
        ("SECRET_KEY=topsecretvalue99", "topsecretvalue99"),
    ],
)
def test_redact_removes_secrets(line, secret):
    out = redact(line)
    assert secret not in out and ("REDACTED" in out)


def test_redact_leaves_ordinary_text():
    assert redact("GET /roadmaps -> 200 (3.2 ms)") == "GET /roadmaps -> 200 (3.2 ms)"


def _record(msg, *args, exc_info=None):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, exc_info)


def test_text_formatter_redacts_args_and_exception_text():
    fmt = RedactingFormatter("%(message)s")
    assert "hunter2hunter2" not in fmt.format(_record("password=%s", "hunter2hunter2"))
    try:
        raise ValueError("bad token=abcdefghijkl")
    except ValueError:
        import sys

        out = fmt.format(_record("failed", exc_info=sys.exc_info()))
    assert "abcdefghijkl" not in out and REDACTED in out


def test_json_formatter_is_valid_json_and_redacts():
    rec = _record("Bearer %s", "abcdefghijklmnop")
    rec.request_id = "rid-12345678"
    parsed = json.loads(RedactingJsonFormatter().format(rec))
    assert parsed["request_id"] == "rid-12345678" and "abcdefghijklmnop" not in parsed["message"]


def test_secrets_not_in_settings_repr():
    s = Settings(SECRET_KEY="s" * 40, METRICS_TOKEN="m" * 20, LLM_API_KEY="k" * 20)
    text = repr(s)
    assert "s" * 40 not in text and "m" * 20 not in text and "k" * 20 not in text


def test_request_logs_carry_request_id_and_no_query_string_or_token(client, alice, caplog):
    caplog.set_level(logging.INFO)
    client.get(
        "/api/roadmaps", params={"user_id": alice.id}, headers={**alice.headers, "X-Request-ID": "trace-abc-12345"}
    )
    access = [r for r in caplog.records if r.name == "pathforge.access" and "/roadmaps" in r.getMessage()]
    assert access and access[-1].request_id == "trace-abc-12345"
    text = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("pathforge"))
    assert alice.id not in text and alice.token not in text and "user_id" not in text


# ---- request id, headers, errors -------------------------------------------------------------------------------
def test_request_id_generated_and_echoed(client):
    rid = client.get("/api/health").headers["X-Request-ID"]
    assert len(rid) >= 8
    assert (
        client.get("/api/health", headers={"X-Request-ID": "caller-id-12345"}).headers["X-Request-ID"]
        == "caller-id-12345"
    )


@pytest.mark.parametrize(
    "bad", ["short", "has space in it!!", "x" * 200, "line\tbreak-12345", "<script>alert(1)</script>"]
)
def test_unsafe_inbound_request_id_replaced(client, bad):
    got = client.get("/api/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
    assert got != bad and got.replace("-", "").isalnum()


def test_security_headers_present_and_csp_skipped_for_docs(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "no-store"
    assert "default-src 'none'" in h["content-security-policy"]
    assert "content-security-policy" not in client.get("/api/docs").headers


def test_unhandled_error_is_generic_500_with_request_id(app, client, caplog):
    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret internal detail password=hunter2hunter2")

    caplog.set_level(logging.ERROR)
    resp = client.get("/api/_boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error" and body["request_id"] == resp.headers["X-Request-ID"]
    assert "secret internal detail" not in resp.text and "Traceback" not in resp.text
    assert any(r.name == "pathforge.error" for r in caplog.records)


def test_oversized_body_rejected_before_parsing(client, monkeypatch):
    big = {"email": "a@example.com", "password": "x" * 100, "display_name": "y" * 7_000_000}
    resp = client.post("/api/auth/register", content=json.dumps(big), headers={"Content-Type": "application/json"})
    assert resp.status_code == 413 and resp.json()["detail"] == "Request body too large"


def test_validation_error_shape_has_no_input_echo(client, alice):
    resp = client.post(
        "/api/roadmaps/generate",
        json={"user_id": alice.id, "hours_per_day": "secret-looking-value"},
        headers=alice.headers,
    )
    assert resp.status_code == 422
    assert "secret-looking-value" not in resp.text


# ---- health / readiness / metrics ------------------------------------------------------------------------------
def test_health_and_ready_are_public_and_reveal_no_secrets(client):
    assert client.get("/api/health").status_code == 200
    ready = client.get("/api/health/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["database"] is True
    assert SECRET not in ready.text and "sqlite" not in ready.text


def test_ready_is_503_when_database_down(app, client):
    from sqlalchemy.exc import OperationalError

    from app.api.routes.ops import get_db

    class Broken:
        def execute(self, *_):
            raise OperationalError("SELECT 1", {}, Exception("down"))

        def close(self):
            pass

    app.dependency_overrides[get_db] = lambda: iter([Broken()])
    try:
        resp = client.get("/api/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 503 and resp.json()["status"] == "not_ready"
    assert "down" not in resp.text


def test_metrics_expose_template_labels_only(client, alice):
    client.get("/api/applications/some-secret-id-123", params={"user_id": alice.id}, headers=alice.headers)
    client.get("/api/not-a-route/with-secret-segment")
    text = client.get("/api/metrics").text
    assert "http_requests_total" in text and "/applications/{application_id}" in text
    assert "some-secret-id-123" not in text and "with-secret-segment" not in text and alice.id not in text
    assert "auth_events_total" in text


def test_metrics_token_rules(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("METRICS_TOKEN", "m-token-0123456789")
    get_settings.cache_clear()
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/metrics", headers={"Authorization": "Bearer m-token-0123456789"}).status_code == 200


def test_metrics_disabled_and_production_without_token_are_404(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("METRICS_ENABLED", "false")
    get_settings.cache_clear()
    assert client.get("/api/metrics").status_code == 404
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    assert client.get("/api/metrics").status_code == 404


# ---- startup validation ----------------------------------------------------------------------------------------
GOOD = {"ENVIRONMENT": "production", "SECRET_KEY": "r" * 48, "AUTH_REQUIRED": True, "DEBUG": False}


def test_production_accepts_safe_settings():
    assert validate_settings(Settings(**GOOD)) == []


@pytest.mark.parametrize(
    "override",
    [
        {"SECRET_KEY": "change-me-in-env"},
        {"SECRET_KEY": "change-me-in-production"},
        {"SECRET_KEY": "short"},
        {"AUTH_REQUIRED": False},
        {"DEBUG": True},
    ],
)
@pytest.mark.parametrize("env", ["production", "staging"])
def test_production_and_staging_refuse_unsafe_settings(override, env):
    with pytest.raises(RuntimeError):
        validate_settings(Settings(**{**GOOD, "ENVIRONMENT": env, **override}))


def test_local_only_warns():
    warnings = validate_settings(Settings(ENVIRONMENT="local", SECRET_KEY="change-me-in-env", AUTH_REQUIRED=False))
    assert warnings and PASSWORD not in " ".join(warnings)
