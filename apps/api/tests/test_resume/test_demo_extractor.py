from app.resume.extraction.demo_extractor import DemoResumeExtractor
from app.resume.sections import detect_sections

_FIXTURE = """Jane Smith
jane.smith@example.com | 555-987-6543 | https://github.com/janesmith

SUMMARY
Backend engineer focused on scalable APIs and machine learning systems.

SKILLS
Python, SQL, FastAPI, Docker, Machine Learning

WORK EXPERIENCE
Senior Engineer at Acme Corp
Jan 2021 - Present
Built and deployed a production RAG pipeline using FastAPI and Qdrant to serve internal search.

PROJECTS
RAG Chatbot
Built a RAG chatbot using FastAPI, Qdrant and OpenAI embeddings.
- Reduced response latency by 40%
- Served 10k+ users

EDUCATION
B.Sc Computer Science, State University
2016 - 2020

CERTIFICATIONS
AWS Certified Solutions Architect, Amazon, 2022

ACHIEVEMENTS
- Won internal hackathon 2022
"""


async def _extract():
    sections = detect_sections(_FIXTURE, max_sections=30)
    return await DemoResumeExtractor().extract(_FIXTURE, sections)


async def test_contact_extraction():
    result = await _extract()
    assert result.contact_name == "Jane Smith"
    assert result.contact_email == "jane.smith@example.com"
    assert result.contact_phone is not None
    assert "https://github.com/janesmith" in result.contact_links


async def test_explicit_skill_mentions_from_skills_section():
    result = await _extract()
    explicit = [m for m in result.skill_mentions if m.evidence_type == "explicit_mention"]
    names = {m.skill_name for m in explicit}
    assert {"Python", "SQL", "FastAPI", "Docker", "Machine Learning"} <= names


async def test_skill_not_automatically_advanced_from_single_mention():
    # This is the core "don't overclaim" requirement: a skills-list
    # mention alone must be evidence_type explicit_mention, never
    # elevated to demonstrated_usage/work_experience just because it's
    # also a real technology name.
    result = await _extract()
    docker_mentions = [m for m in result.skill_mentions if m.skill_name == "Docker"]
    assert len(docker_mentions) == 1
    assert docker_mentions[0].evidence_type == "explicit_mention"


async def test_project_evidence_is_tagged_demonstrated_usage():
    result = await _extract()
    project_evidence = [m for m in result.skill_mentions if m.evidence_type == "demonstrated_usage"]
    assert any(m.skill_name == "rag" for m in project_evidence)
    assert any(m.skill_name == "fastapi" for m in project_evidence)


async def test_work_experience_evidence_is_tagged_work_experience():
    result = await _extract()
    work_evidence = [m for m in result.skill_mentions if m.evidence_type == "work_experience"]
    assert any(m.skill_name == "qdrant" for m in work_evidence)


async def test_experience_extraction():
    result = await _extract()
    assert len(result.experience) == 1
    exp = result.experience[0]
    assert exp["company"] == "Acme Corp"
    assert exp["role"] == "Senior Engineer"
    assert exp["is_current"] is True
    assert exp["start_date"] == "Jan 2021"


async def test_project_extraction_with_achievements():
    result = await _extract()
    assert len(result.projects) == 1
    project = result.projects[0]
    assert project["name"] == "RAG Chatbot"
    assert "Reduced response latency by 40%" in project["achievements"]


async def test_education_extraction():
    result = await _extract()
    assert len(result.education) == 1
    edu = result.education[0]
    assert edu["degree"] == "B.Sc"
    assert "State University" in edu["institution"]
    assert edu["start_date"] == "2016"
    assert edu["end_date"] == "2020"


async def test_certification_extraction():
    result = await _extract()
    assert len(result.certifications) == 1
    cert = result.certifications[0]
    assert cert["name"] == "AWS Certified Solutions Architect"
    assert cert["issuer"] == "Amazon"
    assert cert["date"] == "2022"


async def test_achievements_extraction():
    result = await _extract()
    assert any("hackathon" in a.lower() for a in result.achievements)


async def test_empty_resume_produces_empty_structured_result():
    sections = detect_sections("", max_sections=30)
    result = await DemoResumeExtractor().extract("", sections)
    assert result.skill_mentions == []
    assert result.experience == []
    assert result.projects == []
    assert result.contact_email is None
