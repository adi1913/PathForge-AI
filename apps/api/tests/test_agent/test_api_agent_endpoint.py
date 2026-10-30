"""
The single most important test in Phase 4: proves the full chain works
for real —

    HTTP request -> FastAPI -> AgentOrchestrator -> MCPClientManager
    -> real MCP protocol (stdio subprocess) -> real MCP server
    -> DemoGitHubProvider -> MCP result -> DemoLLMProvider -> AgentResponse

No mocking of MCP anywhere in this file. The TestClient's `with` block
triggers FastAPI's lifespan, which is what spawns the three real MCP
server subprocesses (see app/main.py).
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _demo_mode_and_schema(monkeypatch, tmp_path):
    """Isolated on-disk SQLite DB for this test module (not the
    in-memory db_session fixture, and not the developer's real
    pathforge.db) — the FastAPI app builds its own engine from
    DATABASE_URL at import time, so this has to be a real file the
    app's own session machinery can open."""
    monkeypatch.setenv("DEMO_MODE", "true")
    db_path = tmp_path / "agent_e2e_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)


def _fresh_app():
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


def test_agent_run_end_to_end_github_intent():
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/agent/run", json={"user_request": "Find good RAG projects on GitHub"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert any(t["tool_name"] == "search_github_repositories" for t in body["tools_used"])
    assert any(t["success"] for t in body["tools_used"])
    assert body["answer"]
    assert body["confidence"] in {"low", "medium", "high"}


def test_agent_run_end_to_end_career_intent():
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/agent/run", json={"user_request": "What should I learn to become an AI Engineer?"})

    assert response.status_code == 200
    body = response.json()
    tool_names = {t["tool_name"] for t in body["tools_used"]}
    assert "search_technology_requirements" in tool_names
    assert "search_learning_resources" in tool_names


def test_agent_run_validates_empty_request():
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/agent/run", json={"user_request": ""})

    assert response.status_code == 422  # pydantic min_length validation, never reaches the orchestrator


def test_health_check_still_works_alongside_agent():
    with TestClient(_fresh_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
