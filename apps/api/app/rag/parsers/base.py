"""
DocumentParser turns raw document text into a structured
`ParsedDocument` — a flat list of typed blocks (heading/paragraph/code)
with each block's nearest-heading path attached. The chunker (Phase 5's
chunking/chunker.py) works off this structure rather than raw text, so
it can make structure-aware decisions (don't split a code block, keep a
heading's path as chunk metadata) without re-parsing.

Adding a new input format (e.g. PDF, later) means adding a new
`DocumentParser` implementation that produces the same `ParsedDocument`
shape — nothing downstream changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "code"]


@dataclass
class ParsedBlock:
    kind: BlockKind
    text: str
    heading_path: list[str] = field(default_factory=list)
    level: int | None = None  # heading level (1-6), only set when kind == "heading"


@dataclass
class ParsedDocument:
    title: str | None
    blocks: list[ParsedBlock]


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, raw_content: str) -> ParsedDocument: ...


def normalize_text(raw_content: str) -> str:
    """Shared normalization every parser applies before structural
    parsing: consistent line endings, trimmed trailing whitespace per
    line, collapsed runs of 3+ blank lines to 2 (paragraph separator)."""
    text = raw_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    normalized_lines: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 2:
                normalized_lines.append(line)
        else:
            blank_run = 0
            normalized_lines.append(line)
    return "\n".join(normalized_lines).strip()
