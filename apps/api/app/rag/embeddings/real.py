"""
Real (non-demo) embedding provider, implemented against OpenAI's
embeddings API directly over httpx (no SDK dependency — same pattern as
app/agent/llm/real.py's Anthropic integration and mcp-servers' real
providers).

NOT exercised against a live API in this project's test suite (no
EMBEDDING_API_KEY configured in this environment) — same honesty as
every other "real" provider in this codebase. DemoEmbeddingProvider is
what's actually verified end to end.

Only EMBEDDING_PROVIDER=openai is implemented concretely; the interface
is what makes adding another vendor later not touch anything downstream.
"""

import httpx

from app.core.config import Settings, get_settings
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.errors import EmbeddingProviderError, EmbeddingUnavailableError

_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class RealEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        if self._settings.EMBEDDING_PROVIDER != "openai":
            raise NotImplementedError(
                f"EMBEDDING_PROVIDER={self._settings.EMBEDDING_PROVIDER!r} has no RealEmbeddingProvider "
                "implementation yet. Only 'openai' is implemented; add a branch here to support another "
                "vendor without changing the chunker, vector store, or retriever."
            )
        if not self._settings.EMBEDDING_API_KEY:
            raise EmbeddingUnavailableError(
                "EMBEDDING_PROVIDER=openai but EMBEDDING_API_KEY is not set. Configure EMBEDDING_API_KEY, "
                "or set DEMO_MODE=true to use the deterministic demo embedding provider instead."
            )
        self.dimension = self._settings.EMBEDDING_DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        body = {
            "model": self._settings.EMBEDDING_MODEL,
            "input": texts,
            "dimensions": self.dimension,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.EMBEDDING_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(_OPENAI_EMBEDDINGS_URL, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError("OpenAI embeddings request timed out") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(
                f"OpenAI embeddings request failed: network error ({type(exc).__name__})"
            ) from exc

        if response.status_code >= 400:
            raise EmbeddingProviderError(f"OpenAI embeddings API returned HTTP {response.status_code}")
        try:
            payload = response.json()
            return [item["embedding"] for item in payload["data"]]
        except (ValueError, KeyError) as exc:
            raise EmbeddingProviderError("OpenAI embeddings API returned a malformed response") from exc
