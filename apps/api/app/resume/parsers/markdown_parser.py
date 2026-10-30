"""
Reuses app.rag.parsers.markdown_parser.MarkdownParser (Phase 5) rather
than writing a second Markdown parser — it already correctly handles
headings, sibling/ancestor tracking, and fenced code blocks. This module
just flattens those blocks back into plain text with heading lines kept
distinct, which is what app.resume.sections.SectionDetector needs (it
works line-by-line looking for heading-shaped lines).
"""

from app.rag.parsers.base import normalize_text
from app.rag.parsers.markdown_parser import MarkdownParser
from app.resume.parsers.base import ParsedResumeText, ResumeParser

_underlying = MarkdownParser()


class MarkdownResumeParser(ResumeParser):
    def parse(self, raw: bytes) -> ParsedResumeText:
        warnings = []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            warnings.append("Resume text contained non-UTF-8 bytes; some characters may have been replaced.")

        parsed = _underlying.parse(text)
        lines: list[str] = []
        for block in parsed.blocks:
            lines.append(block.text)
            lines.append("")  # blank line separator, consistent with normalize_text's paragraph convention

        return ParsedResumeText(text=normalize_text("\n".join(lines)), warnings=warnings)
