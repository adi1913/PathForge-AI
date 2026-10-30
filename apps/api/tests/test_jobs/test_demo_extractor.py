from app.jobs.extraction.demo_extractor import DemoJDExtractor
from app.jobs.sections import detect_sections

_JD = """AI Engineer at Acme Corp

SUMMARY
Build AI systems.

RESPONSIBILITIES
- Build RAG pipelines
- Deploy services with Docker

REQUIREMENTS
- Strong experience with Python and FastAPI
- Kubernetes knowledge

PREFERRED QUALIFICATIONS
- Familiarity with MCP

EXPERIENCE
- 3+ years in software

EDUCATION
- B.Tech in CS

CERTIFICATIONS
- AWS Certified
"""


async def _extract(text):
    return await DemoJDExtractor().extract(text, detect_sections(text, 30))


def _by_name(result):
    return {m.skill_name: m for m in result.skill_mentions}


async def test_title_and_company():
    result = await _extract(_JD)
    assert result.title == "AI Engineer at Acme Corp"
    assert result.company == "Acme Corp"
    assert result.role == result.title


async def test_required_and_preferred_split():
    mentions = _by_name(await _extract(_JD))
    assert {
        n
        for n, m in mentions.items()
        if m.requirement_type == "required" and m.source_section == "required_qualifications"
    } == {"python", "fastapi", "kubernetes"}
    assert mentions["mcp"].requirement_type == "preferred"


async def test_responsibility_only_tech_becomes_implicit_required():
    mentions = _by_name(await _extract(_JD))
    assert mentions["docker"].source_section == "responsibilities"
    assert mentions["rag"].requirement_type == "required"


async def test_skill_in_both_sections_keeps_qualification_type_and_adds_responsibility_evidence():
    text = (
        "T\n\nRESPONSIBILITIES\n- Write Python\n- Run Docker\n\n"
        "REQUIREMENTS\n- Python\n\nPREFERRED QUALIFICATIONS\n- Docker\n"
    )
    mentions = (await _extract(text)).skill_mentions
    python = [m for m in mentions if m.skill_name == "python"]
    docker = [m for m in mentions if m.skill_name == "docker"]
    assert {m.source_section for m in python} == {"required_qualifications", "responsibilities"}
    assert {m.requirement_type for m in python} == {"required"}
    assert {m.requirement_type for m in docker} == {"preferred"}  # never promoted by a responsibilities mention


async def test_evidence_is_the_specific_line():
    mentions = _by_name(await _extract(_JD))
    assert mentions["python"].evidence_text == "Strong experience with Python and FastAPI"


async def test_experience_education_certifications_and_responsibilities():
    result = await _extract(_JD)
    assert result.experience_requirements == ["3+ years in software"]
    assert result.education_requirements == ["B.Tech in CS"]
    assert result.certification_requirements == ["AWS Certified"]
    assert "Build RAG pipelines" in result.responsibilities


async def test_different_jds_produce_different_results():
    other = await _extract("Data Analyst\n\nREQUIREMENTS\n- SQL\n- Python\n")
    base = await _extract(_JD)
    assert {m.skill_name for m in other.skill_mentions} != {m.skill_name for m in base.skill_mentions}


async def test_empty_text_yields_empty_extraction():
    result = await _extract("")
    assert result.skill_mentions == [] and result.title is None


async def test_invents_no_skill_not_in_text():
    result = await _extract("Role\n\nREQUIREMENTS\n- Communication skills\n")
    assert result.skill_mentions == []
