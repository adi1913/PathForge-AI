"""
Turns a list of RetrievedChunk into something an LLM can consume while
preserving exactly which source backs which piece of content — so a
future agent can cite sources rather than asserting information came
from "somewhere." Never blindly concatenates unlimited text.
"""

from dataclasses import dataclass, field

from app.rag.retrieval.retriever import RetrievedChunk


@dataclass
class ContextSource:
    document_id: str
    chunk_id: str
    title: str | None
    source: str | None
    heading_path: list[str]
    score: float


@dataclass
class RAGContext:
    text: str
    sources: list[ContextSource] = field(default_factory=list)


def build_context(
    chunks: list[RetrievedChunk],
    max_chunks: int,
    max_chars: int,
    relevance_threshold: float = 0.0,
) -> RAGContext:
    # Relevance threshold first (drop clearly-irrelevant matches)...
    filtered = [c for c in chunks if c.score >= relevance_threshold]

    # ...then de-duplicate by (document_id, chunk_index) — the same chunk
    # should never appear twice even if somehow returned twice upstream...
    seen: set[tuple[str, int]] = set()
    deduped: list[RetrievedChunk] = []
    for c in filtered:
        key = (c.document_id, c.chunk_index)
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    # ...then bound by count...
    bounded = deduped[:max_chunks]

    # ...then bound by total characters, never truncating mid-chunk (drop
    # whole chunks once the budget is spent rather than cutting one off
    # mid-sentence, which would misrepresent the source).
    parts: list[str] = []
    sources: list[ContextSource] = []
    total_chars = 0
    for chunk in bounded:
        heading = " > ".join(chunk.heading_path) if chunk.heading_path else None
        header_bits = [b for b in (chunk.title, heading) if b]
        header = " — ".join(header_bits) if header_bits else "Untitled source"
        block = f"Source: {header}\n{chunk.content}"
        if total_chars + len(block) > max_chars and parts:
            break
        parts.append(block)
        total_chars += len(block)
        sources.append(
            ContextSource(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                source=chunk.source,
                heading_path=chunk.heading_path,
                score=chunk.score,
            )
        )

    return RAGContext(text="\n\n---\n\n".join(parts), sources=sources)
