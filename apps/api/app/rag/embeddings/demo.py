"""
Deterministic, dependency-free embeddings for DEMO_MODE — no external API
call, no API key, and explicitly NOT pretending one happened (no
"source": "live" claim anywhere in the RAG pipeline's demo path — the
Document/DocumentChunk rows and vector-store payload are honest about
provider="demo-hashing").

Approach: the classic "hashing trick" (feature hashing). Each token in
the text is hashed into one of `dimension` buckets with a deterministic
sign, bucket values are accumulated, and the result is L2-normalized.
Same text always produces the same vector (required). Texts sharing
vocabulary land closer together than unrelated texts (weak but real
semantic signal — nowhere near a trained embedding model, but enough to
demonstrate the retrieval pipeline actually discriminates on content
rather than returning arbitrary results). This is a known, standard
technique (same idea as scikit-learn's HashingVectorizer), not an ad hoc
invention.
"""

import hashlib
import math
import re

from app.rag.embeddings.base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _token_bucket_and_sign(token: str, dimension: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % dimension
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return bucket, sign


class DemoEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int):
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.lower()):
            bucket, sign = _token_bucket_and_sign(token, self.dimension)
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]
