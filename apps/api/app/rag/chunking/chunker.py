"""
Turns a ParsedDocument's block list into bounded, overlapping chunks.
Structure-aware rather than a blind character-count split: paragraphs
are merged up to chunk_size, headings become part of the following
chunk's heading context (not a chunk on their own), and a code block is
kept intact whenever it fits within chunk_size at all — only split
line-by-line as a last resort if a single code block alone exceeds the
limit.
"""

from dataclasses import dataclass, field

from app.rag.parsers.base import ParsedBlock, ParsedDocument


@dataclass
class Chunk:
    content: str
    chunk_index: int
    heading_path: list[str] = field(default_factory=list)
    content_type: str = "text"  # "text" or "code" — reflects what the chunk is mostly made of


class StructuralChunker:
    def __init__(self, chunk_size: int, chunk_overlap: int, min_chunk_size: int):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        raw_chunks: list[tuple[str, list[str], str]] = []  # (content, heading_path, content_type)
        buffer = ""
        buffer_path: list[str] = []

        def flush() -> None:
            nonlocal buffer, buffer_path
            text = buffer.strip()
            if text:
                raw_chunks.append((text, buffer_path, "text"))
            buffer = ""

        for block in document.blocks:
            if block.kind == "heading":
                # Headings don't become their own chunk; they set the
                # heading context for whatever paragraph text follows.
                continue

            if block.kind == "code":
                flush()
                raw_chunks.extend(self._split_code_block(block))
                continue

            candidate = (buffer + "\n\n" + block.text).strip() if buffer else block.text
            if buffer and block.heading_path != buffer_path:
                # A new section started — don't silently merge two
                # different sections into one chunk just because they'd
                # fit together; flush and start fresh under the new path.
                flush()
                candidate = block.text

            if len(candidate) <= self.chunk_size:
                buffer = candidate
                buffer_path = block.heading_path
            else:
                flush()
                if len(block.text) <= self.chunk_size:
                    buffer = block.text
                    buffer_path = block.heading_path
                else:
                    raw_chunks.extend(self._split_long_text(block.text, block.heading_path))
                    buffer = ""

        flush()

        merged = self._merge_small_trailing_chunks(raw_chunks)
        return [
            Chunk(content=text, chunk_index=i, heading_path=path, content_type=ctype)
            for i, (text, path, ctype) in enumerate(merged)
        ]

    def _split_code_block(self, block: ParsedBlock) -> list[tuple[str, list[str], str]]:
        if len(block.text) <= self.chunk_size:
            return [(block.text, block.heading_path, "code")]
        # Last resort: a single code block bigger than chunk_size gets
        # split on line boundaries (never mid-line) with overlap.
        lines = block.text.split("\n")
        pieces: list[tuple[str, list[str], str]] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > self.chunk_size and current:
                pieces.append(("\n".join(current), block.heading_path, "code"))
                overlap_lines = self._tail_by_chars(current, self.chunk_overlap)
                current = list(overlap_lines)
                current_len = sum(len(line_) + 1 for line_ in current)
            current.append(line)
            current_len += len(line) + 1
        if current:
            pieces.append(("\n".join(current), block.heading_path, "code"))
        return pieces

    def _split_long_text(self, text: str, heading_path: list[str]) -> list[tuple[str, list[str], str]]:
        """Splits a single paragraph longer than chunk_size at word
        boundaries, with character overlap between consecutive pieces."""
        words = text.split(" ")
        pieces: list[tuple[str, list[str], str]] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > self.chunk_size and current:
                pieces.append((current, heading_path, "text"))
                current = self._tail_str_by_chars(current, self.chunk_overlap) + " " + word
            else:
                current = candidate
        if current.strip():
            pieces.append((current.strip(), heading_path, "text"))
        return pieces

    @staticmethod
    def _tail_by_chars(lines: list[str], max_chars: int) -> list[str]:
        result: list[str] = []
        total = 0
        for line in reversed(lines):
            total += len(line) + 1
            result.insert(0, line)
            if total >= max_chars:
                break
        return result

    @staticmethod
    def _tail_str_by_chars(text: str, max_chars: int) -> str:
        return text[-max_chars:] if len(text) > max_chars else text

    def _merge_small_trailing_chunks(
        self, raw_chunks: list[tuple[str, list[str], str]]
    ) -> list[tuple[str, list[str], str]]:
        """A final chunk smaller than min_chunk_size gets merged into the
        previous one (when that stays within chunk_size) rather than
        left as an awkward tiny fragment."""
        if len(raw_chunks) < 2:
            return raw_chunks
        merged = list(raw_chunks)
        last_text, last_path, last_type = merged[-1]
        if len(last_text) < self.min_chunk_size:
            prev_text, prev_path, prev_type = merged[-2]
            combined = prev_text + "\n\n" + last_text
            if len(combined) <= self.chunk_size and prev_type == last_type and prev_path == last_path:
                merged[-2] = (combined, prev_path, prev_type)
                merged.pop()
        return merged
