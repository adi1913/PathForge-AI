import pytest

from app.rag.errors import UnsupportedContentTypeError
from app.rag.parsers.factory import get_parser
from app.rag.parsers.markdown_parser import MarkdownParser
from app.rag.parsers.text_parser import PlainTextParser


def test_plain_text_parser_splits_paragraphs():
    doc = PlainTextParser().parse("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")
    assert len(doc.blocks) == 3
    assert all(b.kind == "paragraph" for b in doc.blocks)
    assert doc.title == "First paragraph."


def test_markdown_parser_extracts_headings_and_paragraphs():
    md = "# Title\n\nIntro text.\n\n## Section One\n\nSection one text."
    doc = MarkdownParser().parse(md)
    kinds = [b.kind for b in doc.blocks]
    assert kinds == ["heading", "paragraph", "heading", "paragraph"]
    assert doc.title == "Title"


def test_markdown_parser_sibling_headings_have_correct_ancestors():
    md = "# Root\n\n## A\n\ntext a\n\n## B\n\ntext b"
    doc = MarkdownParser().parse(md)
    heading_b = next(b for b in doc.blocks if b.kind == "heading" and b.text == "B")
    assert heading_b.heading_path == ["Root"]  # NOT ["Root", "A"]


def test_markdown_parser_preserves_code_blocks_verbatim():
    md = "# Title\n\n```python\ndef f():\n    return 1\n```\n"
    doc = MarkdownParser().parse(md)
    code_block = next(b for b in doc.blocks if b.kind == "code")
    assert code_block.text == "def f():\n    return 1"


def test_markdown_parser_handles_unterminated_code_fence():
    md = "# Title\n\n```python\ndef f():\n    return 1\n"
    doc = MarkdownParser().parse(md)
    code_block = next(b for b in doc.blocks if b.kind == "code")
    assert "def f()" in code_block.text  # salvaged rather than lost


def test_factory_selects_markdown_and_text():
    assert isinstance(get_parser("markdown"), MarkdownParser)
    assert isinstance(get_parser("text"), PlainTextParser)


def test_factory_rejects_unsupported_content_type():
    with pytest.raises(UnsupportedContentTypeError):
        get_parser("pdf")
