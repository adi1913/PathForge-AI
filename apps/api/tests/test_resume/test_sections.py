from app.resume.sections import detect_sections


def test_recognizes_known_section_variants():
    text = "SUMMARY\nA short bio.\n\nTECHNICAL SKILLS\nPython\n\nWORK HISTORY\nDid stuff.\n"
    sections = detect_sections(text, max_sections=30)
    assert "summary" in sections
    assert "skills" in sections
    assert "experience" in sections


def test_preserves_unrecognized_heading_shaped_section():
    text = "PUBLICATIONS\nSome paper.\n\nVOLUNTEER WORK\nHelped out.\n"
    sections = detect_sections(text, max_sections=30)
    assert "publications" in sections
    assert "VOLUNTEER WORK" in sections  # unknown template section preserved, not discarded


def test_does_not_misdetect_name_or_date_lines_as_headings():
    text = "Jane Doe\n\nEXPERIENCE\nEngineer at Acme\nJan 2020 - Present\nDid the work.\n"
    sections = detect_sections(text, max_sections=30)
    assert "header" in sections
    assert "Jane Doe" in sections["header"]
    assert "experience" in sections
    assert "Jan 2020 - Present" in sections["experience"]


def test_content_before_first_heading_goes_to_header():
    text = "Jane Doe\njane@example.com\n\nSKILLS\nPython\n"
    sections = detect_sections(text, max_sections=30)
    assert "jane@example.com" in sections["header"]


def test_max_sections_bound_is_respected():
    lines = []
    for i in range(50):
        lines.append(f"SECTION{i}")
        lines.append(f"content {i}")
        lines.append("")
    text = "\n".join(lines)
    sections = detect_sections(text, max_sections=10)
    assert len(sections) <= 10
