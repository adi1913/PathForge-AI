import pytest

from app.jobs.errors import UnsupportedJDFormatError
from app.jobs.parsers import get_jd_parser, resolve_content_type
from app.jobs.sections import detect_sections


def test_text_parser_returns_text():
    assert "Python" in get_jd_parser("text").parse(b"Need Python").text


def test_markdown_parser_flattens_headings():
    parsed = get_jd_parser("markdown").parse(b"# AI Engineer\n\n## Requirements\n- Python\n")
    assert "Requirements" in parsed.text and "Python" in parsed.text


def test_pdf_is_rejected_with_clear_error():
    with pytest.raises(UnsupportedJDFormatError):
        get_jd_parser(resolve_content_type("jd.pdf", None))


def test_resolve_content_type_by_extension_and_default():
    assert resolve_content_type("jd.md", None) == "markdown"
    assert resolve_content_type("jd.txt", None) == "text"
    assert resolve_content_type(None, None) == "text"


@pytest.mark.parametrize(
    "heading,canonical",
    [
        ("Requirements", "required_qualifications"),
        ("Must Have", "required_qualifications"),
        ("Minimum Qualifications", "required_qualifications"),
        ("Preferred Qualifications", "preferred_qualifications"),
        ("Nice to Have", "preferred_qualifications"),
        ("What You'll Do", "responsibilities"),
        ("Responsibilities", "responsibilities"),
    ],
)
def test_heading_variations_map_to_canonical(heading, canonical):
    sections = detect_sections(f"Title\n\n{heading}\n- Python\n", max_sections=30)
    assert canonical in sections and "Python" in sections[canonical]


def test_missing_sections_yield_only_header():
    sections = detect_sections("Just a paragraph with no headings at all.", max_sections=30)
    assert list(sections) == ["header"]


def test_unknown_allcaps_heading_preserved_and_titlecase_not_heading():
    sections = detect_sections("T\n\nWORKING HOURS\n9 to 5\n\nSome Title Case Line\nmore\n", max_sections=30)
    assert "WORKING HOURS" in sections
    assert "Some Title Case Line" not in sections


def test_max_sections_bound():
    text = "\n".join(f"SECTION{chr(65 + i)}{chr(65 + i)}{chr(65 + i)}\nbody" for i in range(10))
    assert len(detect_sections(text, max_sections=3)) <= 3


def test_allcaps_bullet_items_are_content_not_headings():
    text = "T\n\nREQUIREMENTS\n- Python\n- RAG\n- MCP\n\nPREFERRED QUALIFICATIONS\n- AWS\n"
    sections = detect_sections(text, max_sections=30)
    assert "- RAG" not in sections and "- MCP" not in sections
    assert "RAG" in sections["required_qualifications"]
    assert "AWS" in sections["preferred_qualifications"]
