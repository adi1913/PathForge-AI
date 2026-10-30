"""
Deliberately NOT an async-generator fixture wrapping MCPClientManager's
context manager across the pytest-asyncio setup/teardown boundary: doing
that split connect_all()/close() across what pytest-asyncio may treat as
different asyncio Tasks, which breaks anyio's TaskGroup/CancelScope
(stdio_client uses one internally) — it requires __aenter__/__aexit__ in
the exact same task. Tests instead open `async with MCPClientManager()`
directly in the test body via this helper, keeping the whole lifecycle
in one task.
"""

import pytest


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
