import pytest

from app.resume.errors import ResumeParsingFailedError, UnsupportedResumeFormatError
from app.resume.parsers.factory import get_resume_parser, resolve_content_type
from app.resume.parsers.markdown_parser import MarkdownResumeParser
from app.resume.parsers.pdf_parser import PDFResumeParser
from app.resume.parsers.text_parser import TextResumeParser


def test_text_parser_decodes_utf8():
    result = TextResumeParser().parse("Hello résumé".encode())
    assert "Hello" in result.text
    assert result.warnings == []


def test_text_parser_handles_bad_bytes_with_warning():
    result = TextResumeParser().parse(b"Hello \xff\xfe World")
    assert result.warnings  # replaced rather than crashing


def test_markdown_parser_flattens_headings_for_section_detection():
    md = b"# Jane Doe\n\n## Skills\n\nPython, SQL\n"
    result = MarkdownResumeParser().parse(md)
    assert "Skills" in result.text
    assert "Python, SQL" in result.text


def test_pdf_parser_extracts_real_text():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="SKILLS")
    pdf.ln()
    pdf.cell(text="Python, SQL, Docker")
    data = bytes(pdf.output())

    result = PDFResumeParser().parse(data)
    assert "Python" in result.text
    assert result.warnings == []


def test_pdf_parser_reports_scanned_image_as_warning_not_crash():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()  # blank page, no text at all — simulates a scanned image with no text layer
    data = bytes(pdf.output())

    result = PDFResumeParser().parse(data)
    assert result.text.strip() == ""
    assert any("scanned image" in w.lower() or "no extractable text" in w.lower() for w in result.warnings)


def test_pdf_parser_rejects_invalid_pdf_bytes():
    with pytest.raises(ResumeParsingFailedError):
        PDFResumeParser().parse(b"this is definitely not a valid PDF file")


def test_factory_rejects_unsupported_format():
    with pytest.raises(UnsupportedResumeFormatError):
        get_resume_parser("application/msword")


def test_resolve_content_type_prefers_mime_type():
    assert resolve_content_type("resume.txt", "application/pdf") == "application/pdf"


def test_resolve_content_type_falls_back_to_extension():
    assert resolve_content_type("resume.pdf", None) == "pdf"
    assert resolve_content_type("resume.md", None) == "markdown"


def test_resolve_content_type_defaults_to_text():
    assert resolve_content_type(None, None) == "text"
