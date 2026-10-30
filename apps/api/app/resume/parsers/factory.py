from app.resume.errors import UnsupportedResumeFormatError
from app.resume.parsers.base import ResumeParser
from app.resume.parsers.markdown_parser import MarkdownResumeParser
from app.resume.parsers.pdf_parser import PDFResumeParser
from app.resume.parsers.text_parser import TextResumeParser

_PARSERS: dict[str, ResumeParser] = {
    "text": TextResumeParser(),
    "text/plain": TextResumeParser(),
    "markdown": MarkdownResumeParser(),
    "text/markdown": MarkdownResumeParser(),
    "md": MarkdownResumeParser(),
    "pdf": PDFResumeParser(),
    "application/pdf": PDFResumeParser(),
}

_EXTENSION_MAP = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown", ".txt": "text"}


def get_resume_parser(content_type: str) -> ResumeParser:
    parser = _PARSERS.get(content_type.lower())
    if parser is None:
        raise UnsupportedResumeFormatError(content_type)
    return parser


def resolve_content_type(filename: str | None, mime_type: str | None) -> str:
    """Determines which parser to use from whatever the client gave us —
    prefer an explicit MIME type, fall back to the filename extension.
    Never trusts the filename for anything beyond this (see
    app.resume.upload for filename sanitization applied separately)."""
    if mime_type and mime_type.lower() in _PARSERS:
        return mime_type.lower()
    if filename:
        for ext, content_type in _EXTENSION_MAP.items():
            if filename.lower().endswith(ext):
                return content_type
    return "text"
