import pytest

from app.jobs.errors import JDTooLargeError, UnsupportedJDFormatError
from app.jobs.service import JobDescriptionAnalyzerService
from app.models.enums import EvidenceSource, GapSeverity, SkillGapStatus, SkillLevel, SkillMatchStatus
from app.models.job_description import JobDescription, JobDescriptionSkill
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from app.models.skill_gap import SkillGap
from app.models.user import User

_JD = b"""ML Engineer at Acme

REQUIREMENTS
- Strong experience with Python
- Machine Learning
- Terraform

PREFERRED QUALIFICATIONS
- Docker
"""


def _seed(db):
    skills = {}
    for slug, name in [("python", "Python"), ("machine-learning", "Machine Learning"), ("docker", "Docker")]:
        skills[slug] = Skill(slug=slug, name=name)
        db.add(skills[slug])
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    user = User(email="gap@example.com", password_hash="h")
    db.add(user)
    db.commit()
    return user, skills


def _give(db, user, skill, level, confidence=0.8):
    db.add(
        UserSkill(
            user_id=user.id,
            skill_id=skill.id,
            current_level=level,
            confidence=confidence,
            source=EvidenceSource.MANUAL,
            evidence=[],
        )
    )
    db.commit()


async def test_jd_and_requirements_persisted(db_session):
    user, _ = _seed(db_session)
    analysis, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    jd = db_session.query(JobDescription).filter_by(id=extras.job_description_id).one()
    assert jd.user_id == user.id and jd.title == analysis.title
    rows = db_session.query(JobDescriptionSkill).filter_by(job_description_id=jd.id).all()
    assert {r.skill.slug for r in rows} == {"python", "machine-learning", "docker"}


async def test_unmatched_skill_reported_and_not_inserted(db_session):
    user, _ = _seed(db_session)
    before = db_session.query(Skill).count()
    analysis, _ = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    assert "terraform" in analysis.unmatched_skills
    assert db_session.query(Skill).count() == before


async def test_gap_statuses_and_persistence(db_session):
    user, skills = _seed(db_session)
    _give(db_session, user, skills["python"], SkillLevel.BEGINNER)  # needs advanced -> weak
    analysis, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)

    by_slug = {r.skill_slug: r for r in extras.skill_gaps}
    assert by_slug["python"].match_status == SkillMatchStatus.WEAK
    assert by_slug["machine-learning"].match_status == SkillMatchStatus.MISSING
    assert by_slug["docker"].match_status == SkillMatchStatus.MISSING
    assert "Python" in by_slug["machine-learning"].prerequisites

    gaps = {g.skill.slug: g for g in db_session.query(SkillGap).filter_by(user_id=user.id).all()}
    assert gaps["python"].match_status == SkillMatchStatus.WEAK
    assert gaps["python"].current_level == SkillLevel.BEGINNER
    assert gaps["python"].target_level == SkillLevel.ADVANCED
    assert gaps["python"].priority_score == by_slug["python"].priority_score
    assert gaps["python"].source_job_description_id == extras.job_description_id


async def test_matched_skill_creates_no_gap_row(db_session):
    user, skills = _seed(db_session)
    _give(db_session, user, skills["python"], SkillLevel.EXPERT)
    _, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    assert [r.skill_slug for r in extras.matched_skills] == ["python"]
    assert db_session.query(SkillGap).filter_by(user_id=user.id).count() == 2


async def test_gaps_sorted_by_priority_desc_and_overall_score(db_session):
    user, _ = _seed(db_session)
    _, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    scores = [g.priority_score for g in extras.skill_gaps]
    assert scores == sorted(scores, reverse=True)
    assert extras.overall_match_score == 0.0
    assert extras.user_skill_summary.missing_count == 3


async def test_prerequisite_gap_boosts_priority(db_session):
    user, skills = _seed(db_session)
    _, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    ml_with_gap = next(g for g in extras.skill_gaps if g.skill_slug == "machine-learning").priority_score
    _give(db_session, user, skills["python"], SkillLevel.EXPERT)
    _, extras2 = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id=user.id)
    ml_without_gap = next(g for g in extras2.skill_gaps if g.skill_slug == "machine-learning").priority_score
    assert ml_with_gap > ml_without_gap


async def test_reanalysis_upserts_without_duplicates(db_session):
    user, skills = _seed(db_session)
    svc = JobDescriptionAnalyzerService(db_session)
    _, first = await svc.analyze(_JD, user_id=user.id)
    _give(db_session, user, skills["python"], SkillLevel.EXPERT)
    _, second = await svc.analyze(_JD, user_id=user.id)

    assert first.job_description_id == second.job_description_id
    assert db_session.query(JobDescription).count() == 1
    assert db_session.query(JobDescriptionSkill).count() == 3
    assert db_session.query(SkillGap).filter_by(user_id=user.id).count() == 3  # one row per skill, no duplicates
    python_gap = db_session.query(SkillGap).join(Skill).filter(Skill.slug == "python").one()
    assert python_gap.match_status == SkillMatchStatus.MATCHED
    assert python_gap.status == SkillGapStatus.CLOSED and python_gap.severity == GapSeverity.NONE


async def test_no_user_skips_comparison(db_session):
    _seed(db_session)
    analysis, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD)
    assert extras.overall_match_score is None and extras.skill_gaps == []
    assert any("skipped" in w for w in analysis.warnings)
    assert db_session.query(JobDescription).one().user_id is None
    assert db_session.query(SkillGap).count() == 0


async def test_unknown_user_id_warns_and_does_not_persist_gaps(db_session):
    _seed(db_session)
    analysis, extras = await JobDescriptionAnalyzerService(db_session).analyze(_JD, user_id="nope")
    assert any("not found" in w for w in analysis.warnings)
    assert extras.skill_gaps == []


async def test_oversized_input_rejected(db_session):
    with pytest.raises(JDTooLargeError):
        await JobDescriptionAnalyzerService(db_session).analyze(b"x" * 2_000_001)


async def test_pdf_unsupported(db_session):
    with pytest.raises(UnsupportedJDFormatError):
        await JobDescriptionAnalyzerService(db_session).analyze(b"%PDF", filename="jd.pdf")


async def test_empty_input_warns(db_session):
    analysis, _ = await JobDescriptionAnalyzerService(db_session).analyze(b"   ")
    assert any("empty" in w for w in analysis.warnings)
    assert analysis.required_skills == []


async def test_severity_critical_for_missing_critical_required(db_session):
    user, _ = _seed(db_session)
    jd = b"Role\n\nREQUIREMENTS\n- Essential: strong experience with Python\n\nRESPONSIBILITIES\n- Write Python daily\n"
    _, extras = await JobDescriptionAnalyzerService(db_session).analyze(jd, user_id=user.id)
    python = extras.skill_gaps[0]
    assert python.severity == GapSeverity.CRITICAL and python.expected_level == SkillLevel.ADVANCED
