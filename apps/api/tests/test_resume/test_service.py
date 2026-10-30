import pytest

from app.models.document import Document, DocumentChunk
from app.models.skill import Skill, UserSkill
from app.models.user import User
from app.resume.errors import ResumeTooLargeError
from app.resume.service import ResumeAnalyzerService

_RESUME = b"""Jane Smith
jane@example.com

SKILLS
Python, SQL

PROJECTS
RAG Chatbot
Built a RAG chatbot using FastAPI.
"""


def _seed_skills(db):
    for slug, name in [("python", "Python"), ("sql", "SQL"), ("rag", "RAG"), ("fastapi", "FastAPI")]:
        db.add(Skill(slug=slug, name=name))
    db.commit()


def _make_user(db, email="resume-test@example.com"):
    user = User(email=email, password_hash="hashed")
    db.add(user)
    db.commit()
    return user


async def test_analyze_creates_document_and_chunks(db_session):
    _seed_skills(db_session)
    service = ResumeAnalyzerService(db_session)
    analysis, summary = await service.analyze(_RESUME, filename="resume.txt", mime_type="text/plain")

    doc = db_session.query(Document).filter_by(id=summary.document_id).one()
    assert (doc.document_metadata or {}).get("document_type") == "resume"
    assert db_session.query(DocumentChunk).filter_by(document_id=doc.id).count() > 0


async def test_analyze_without_user_id_does_not_persist_user_skills(db_session):
    _seed_skills(db_session)
    service = ResumeAnalyzerService(db_session)
    _, summary = await service.analyze(_RESUME, filename="resume.txt", mime_type="text/plain")
    assert summary.user_skills_created == 0
    assert db_session.query(UserSkill).count() == 0


async def test_analyze_with_user_id_persists_user_skills(db_session):
    _seed_skills(db_session)
    user = _make_user(db_session)
    service = ResumeAnalyzerService(db_session)
    analysis, summary = await service.analyze(_RESUME, filename="resume.txt", mime_type="text/plain", user_id=user.id)
    assert summary.user_skills_created >= 2  # at least python, sql
    stored = db_session.query(UserSkill).filter_by(user_id=user.id).all()
    assert len(stored) == summary.user_skills_created
    assert all(s.source.value == "resume" for s in stored)
    assert all(s.evidence for s in stored)  # evidence is never empty


async def test_reanalyzing_updates_existing_user_skill_not_duplicates(db_session):
    _seed_skills(db_session)
    user = _make_user(db_session)
    service = ResumeAnalyzerService(db_session)
    await service.analyze(_RESUME, filename="resume.txt", mime_type="text/plain", user_id=user.id)
    _, summary2 = await service.analyze(_RESUME, filename="resume.txt", mime_type="text/plain", user_id=user.id)

    assert summary2.user_skills_created == 0
    assert summary2.user_skills_updated >= 2
    python_skill = db_session.query(Skill).filter_by(slug="python").one()
    assert db_session.query(UserSkill).filter_by(user_id=user.id, skill_id=python_skill.id).count() == 1


async def test_unknown_user_id_adds_warning_and_skips_persistence(db_session):
    _seed_skills(db_session)
    service = ResumeAnalyzerService(db_session)
    analysis, summary = await service.analyze(
        _RESUME, filename="resume.txt", mime_type="text/plain", user_id="00000000-0000-0000-0000-000000000000"
    )
    assert summary.user_skills_created == 0
    assert any("not found" in w.lower() for w in analysis.warnings)


async def test_empty_resume_does_not_crash(db_session):
    service = ResumeAnalyzerService(db_session)
    analysis, summary = await service.analyze(b"", filename="empty.txt", mime_type="text/plain")
    assert analysis.skills == []
    assert analysis.experience == []


async def test_oversized_resume_is_rejected(db_session):
    service = ResumeAnalyzerService(db_session)
    huge = b"x" * (service._settings.RESUME_MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ResumeTooLargeError):
        await service.analyze(huge, filename="huge.txt", mime_type="text/plain")


async def test_unmatched_skills_are_reported_not_persisted(db_session):
    _seed_skills(db_session)
    user = _make_user(db_session, "unmatched-test@example.com")
    resume = b"Jane\njane2@example.com\n\nSKILLS\nSomeTotallyMadeUpFramework9000\n"
    service = ResumeAnalyzerService(db_session)
    analysis, summary = await service.analyze(resume, filename="r.txt", mime_type="text/plain", user_id=user.id)
    assert "SomeTotallyMadeUpFramework9000" in analysis.unmatched_skills
    assert all(s.normalized_skill != "sometotallymadeupframework9000" for s in analysis.skills)
    assert summary.user_skills_created == 0
