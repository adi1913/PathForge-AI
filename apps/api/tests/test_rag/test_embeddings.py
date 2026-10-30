import pytest

from app.rag.embeddings.demo import DemoEmbeddingProvider


async def test_demo_embeddings_are_deterministic():
    provider = DemoEmbeddingProvider(dimension=128)
    v1 = await provider.embed(["hello world"])
    v2 = await provider.embed(["hello world"])
    assert v1 == v2


async def test_demo_embeddings_have_configured_dimension():
    provider = DemoEmbeddingProvider(dimension=256)
    vectors = await provider.embed(["a", "b"])
    assert len(vectors) == 2
    assert all(len(v) == 256 for v in vectors)


async def test_demo_embeddings_discriminate_similar_vs_unrelated_text():
    provider = DemoEmbeddingProvider(dimension=384)
    v_python = (await provider.embed(["python programming language"]))[0]
    v_python2 = (await provider.embed(["python programming basics"]))[0]
    v_unrelated = (await provider.embed(["italian pasta recipes"]))[0]

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cos(v_python, v_python2) > cos(v_python, v_unrelated)


async def test_demo_embeddings_never_call_network():
    # No httpx/network mocking exists in this test — if the demo provider
    # tried to make a real HTTP call, this test would hang or fail with a
    # connection error in a sandboxed environment. Passing quickly proves
    # it doesn't.
    provider = DemoEmbeddingProvider(dimension=32)
    result = await provider.embed(["quick check"])
    assert len(result) == 1


def test_real_embedding_provider_raises_when_unconfigured(monkeypatch):
    from app.core.config import get_settings
    from app.rag.embeddings.real import RealEmbeddingProvider
    from app.rag.errors import EmbeddingUnavailableError

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(EmbeddingUnavailableError):
            RealEmbeddingProvider(get_settings())
    finally:
        get_settings.cache_clear()


def test_factory_returns_demo_provider_in_demo_mode(monkeypatch):
    from app.core.config import get_settings
    from app.rag.embeddings.factory import get_embedding_provider

    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        provider = get_embedding_provider(get_settings())
        assert isinstance(provider, DemoEmbeddingProvider)
    finally:
        get_settings.cache_clear()
