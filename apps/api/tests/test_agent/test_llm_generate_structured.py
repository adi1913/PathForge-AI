import pytest
from pydantic import BaseModel

from app.agent.errors import LLMUnavailableError, MalformedLLMResponseError
from app.agent.llm.demo import DemoLLMProvider


class _Extracted(BaseModel):
    name: str
    count: int


async def test_demo_llm_refuses_structured_generation():
    provider = DemoLLMProvider()
    with pytest.raises(LLMUnavailableError):
        await provider.generate_structured("system", "user", _Extracted)


async def test_real_llm_generate_structured_validates_and_returns_schema(monkeypatch):
    from app.agent.llm.real import RealLLMProvider
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "fake-key-for-test")
    get_settings.cache_clear()
    try:
        provider = RealLLMProvider(get_settings())

        async def fake_post(body):
            return {
                "content": [
                    {"type": "tool_use", "name": "emit_structured_output", "input": {"name": "widget", "count": 3}}
                ]
            }

        provider._post = fake_post
        result = await provider.generate_structured("sys", "usr", _Extracted)
        assert result == _Extracted(name="widget", count=3)
    finally:
        get_settings.cache_clear()


async def test_real_llm_generate_structured_repairs_once_then_fails(monkeypatch):
    from app.agent.llm.real import RealLLMProvider
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "fake-key-for-test")
    get_settings.cache_clear()
    try:
        provider = RealLLMProvider(get_settings())
        call_count = 0

        async def fake_post(body):
            nonlocal call_count
            call_count += 1
            # Always returns invalid data (missing required "count") —
            # proves the single repair attempt happens, then gives up.
            return {"content": [{"type": "tool_use", "name": "emit_structured_output", "input": {"name": "widget"}}]}

        provider._post = fake_post
        with pytest.raises(MalformedLLMResponseError):
            await provider.generate_structured("sys", "usr", _Extracted)
        assert call_count == 2  # original attempt + exactly one repair
    finally:
        get_settings.cache_clear()
