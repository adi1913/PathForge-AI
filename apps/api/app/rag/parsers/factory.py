from app.rag.errors import UnsupportedContentTypeError
from app.rag.parsers.base import DocumentParser
from app.rag.parsers.markdown_parser import MarkdownParser
from app.rag.parsers.text_parser import PlainTextParser

_PARSERS: dict[str, DocumentParser] = {
    "text": PlainTextParser(),
    "plain": PlainTextParser(),
    "markdown": MarkdownParser(),
    "md": MarkdownParser(),
}


def get_parser(content_type: str) -> DocumentParser:
    parser = _PARSERS.get(content_type.lower())
    if parser is None:
        raise UnsupportedContentTypeError(content_type)
    return parser
