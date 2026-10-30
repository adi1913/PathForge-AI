import re

from app.rag.parsers.base import DocumentParser, ParsedBlock, ParsedDocument, normalize_text

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^(```|~~~)")


class MarkdownParser(DocumentParser):
    """A deliberately small, dependency-free Markdown structural parser —
    not a full CommonMark renderer. It only needs to recognize enough
    structure (headings, fenced code, paragraphs) for the chunker to make
    good split decisions; it does not need to produce HTML."""

    def parse(self, raw_content: str) -> ParsedDocument:
        text = normalize_text(raw_content)
        lines = text.split("\n")

        blocks: list[ParsedBlock] = []
        heading_stack: list[tuple[int, str]] = []  # (level, text), ancestors only

        paragraph_buffer: list[str] = []
        code_buffer: list[str] = []
        in_code = False
        fence_marker = ""

        def current_path() -> list[str]:
            return [h[1] for h in heading_stack]

        def flush_paragraph() -> None:
            if paragraph_buffer:
                blocks.append(
                    ParsedBlock(kind="paragraph", text="\n".join(paragraph_buffer).strip(), heading_path=current_path())
                )
                paragraph_buffer.clear()

        for line in lines:
            if in_code:
                if line.strip().startswith(fence_marker):
                    blocks.append(ParsedBlock(kind="code", text="\n".join(code_buffer), heading_path=current_path()))
                    code_buffer.clear()
                    in_code = False
                else:
                    code_buffer.append(line)
                continue

            fence_match = _FENCE_RE.match(line.strip())
            if fence_match:
                flush_paragraph()
                in_code = True
                fence_marker = fence_match.group(1)
                continue

            heading_match = _HEADING_RE.match(line)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                # Pop back to this heading's true ancestors BEFORE reading
                # current_path(), or a same-or-deeper-level previous
                # sibling would incorrectly show up as this heading's parent.
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                blocks.append(ParsedBlock(kind="heading", text=heading_text, heading_path=current_path(), level=level))
                heading_stack.append((level, heading_text))
                continue

            if line.strip() == "":
                flush_paragraph()
                continue

            paragraph_buffer.append(line)

        flush_paragraph()
        if code_buffer:  # unterminated fence at EOF — salvage what we have
            blocks.append(ParsedBlock(kind="code", text="\n".join(code_buffer), heading_path=current_path()))

        title = next((b.text for b in blocks if b.kind == "heading" and b.level == 1), None)
        if title is None:
            first_paragraph = next((b.text for b in blocks if b.kind == "paragraph"), None)
            title = first_paragraph[:100] if first_paragraph else None

        return ParsedDocument(title=title, blocks=blocks)
