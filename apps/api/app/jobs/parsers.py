"""JD parsers. A JD is plain text or Markdown, so this reuses the Phase 6
text/Markdown parsers rather than duplicating them. PDF can be added later
by registering another parser here without touching the service."""

from app.jobs.errors import UnsupportedJDFormatError
from app.resume.parsers.base import ResumeParser as JobDescriptionParser
from app.resume.parsers.markdown_parser import MarkdownResumeParser
from app.resume.parsers.text_parser import TextResumeParser

_PARSERS: dict[str, JobDescriptionParser] = {
    "text": TextResumeParser(),
    "text/plain": TextResumeParser(),
    "markdown": MarkdownResumeParser(),
    "text/markdown": MarkdownResumeParser(),
    "md": MarkdownResumeParser(),
}

_EXTENSION_MAP = {".md": "markdown", ".markdown": "markdown", ".txt": "text"}


def get_jd_parser(content_type: str) -> JobDescriptionParser:
    parser = _PARSERS.get(content_type.lower())
    if parser is None:
        raise UnsupportedJDFormatError(content_type)
    return parser


def resolve_content_type(filename: str | None, mime_type: str | None) -> str:
    if mime_type and mime_type.lower() in _PARSERS:
        return mime_type.lower()
    if filename:
        lowered = filename.lower()
        for ext, content_type in _EXTENSION_MAP.items():
            if lowered.endswith(ext):
                return content_type
        if lowered.endswith(".pdf"):
            return "application/pdf"  # recognized but unsupported -> clear error from get_jd_parser
    return "text"


__all__ = ["JobDescriptionParser", "get_jd_parser", "resolve_content_type"]
