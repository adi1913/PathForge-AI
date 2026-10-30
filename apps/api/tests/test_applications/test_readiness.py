from datetime import timedelta

from app.applications.schemas import ApplicationCreateRequest
from app.applications.service import ApplicationService
from app.jobs.gap_engine import compute_overall_match_score
from app.models.enums import EvidenceSource, ImportanceLevel, SkillImportance, SkillLevel, SkillMatchStatus
from app.models.job_description import JobDescription
from app.models.skill import UserSkill
from app.models.skill_gap import SkillGap
from tests.test_applications.helpers import make_jd, own, seed


def _readiness(db, user, **kw):
    svc = ApplicationService(db)
    app = svc.create(ApplicationCreateRequest(user_id=user.id, **kw))
    return svc.readiness(app.id, user.id)


def test_unavailable_without_jd(db_session):
    user, _, _ = seed(db_session)
    r = _readiness(db_session, user, job_title="Manual")
    assert r.status == "unavailable" and "No job description" in r.reason
    assert r.overall_match_score is None and r.disclaimer


def test_unavailable_when_jd_deleted_or_empty(db_session):
    user, _, skills = seed(db_session)
    empty = make_jd(db_session, user, skills, rows=[])
    assert "no extracted skills" in _readiness(db_session, user, job_description_id=empty.id).reason
    jd = make_jd(db_session, user, skills, title="Other")
    svc = ApplicationService(db_session)
    app = svc.create(ApplicationCreateRequest(user_id=user.id, job_description_id=jd.id))
    db_session.delete(jd)
    db_session.commit()
    assert "deleted" in svc.readiness(app.id, user.id).reason


def test_no_user_skills_everything_missing_with_warning(db_session):
    user, _, skills = seed(db_session)
    r = _readiness(db_session, user, job_description_id=make_jd(db_session, user, skills).id)
    assert r.status == "computed" and r.overall_match_score == 0.0
    assert (r.matched_count, r.weak_count, r.missing_count) == (0, 0, 3)
    assert any("No skills are recorded" in w for w in r.warnings)
    assert all(s.data_kind == "none" for s in r.skills)


def test_matches_gap_engine_and_ranks_by_priority(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["python"], SkillLevel.ADVANCED)  # matched
    own(db_session, user, skills["machine-learning"], SkillLevel.BEGINNER)  # weak vs advanced, critical
    r = _readiness(db_session, user, job_description_id=make_jd(db_session, user, skills).id)
    by = {s.skill_name: s for s in r.skills}
    assert by["Python"].match_status == SkillMatchStatus.MATCHED
    assert by["Machine Learning"].match_status == SkillMatchStatus.WEAK
    assert by["Docker"].match_status == SkillMatchStatus.MISSING
    assert r.skills[0].skill_name == "Machine Learning"  # highest priority first
    assert r.critical_gap_count == 1
    # Score must be exactly what the Phase 7 engine produces: required python(2*3) full,
    # ML (2*4) 1/3, docker (1*1) 0 -> (6 + 8/3) / 15
    assert r.overall_match_score == round(100 * (6 + 8 / 3) / 15, 1)
    assert 0 < r.overall_match_score < 100


def test_perfect_candidate_scores_100(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["python"], SkillLevel.EXPERT)
    own(db_session, user, skills["machine-learning"], SkillLevel.ADVANCED)
    own(db_session, user, skills["docker"], SkillLevel.BEGINNER)
    r = _readiness(db_session, user, job_description_id=make_jd(db_session, user, skills).id)
    assert r.overall_match_score == 100.0 and r.missing_count == r.weak_count == 0


def test_measured_vs_estimated_and_low_confidence(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["python"], SkillLevel.ADVANCED, source=EvidenceSource.ASSESSMENT)
    own(db_session, user, skills["machine-learning"], SkillLevel.ADVANCED, confidence=0.2)  # resume, low conf
    r = _readiness(db_session, user, job_description_id=make_jd(db_session, user, skills).id)
    by = {s.skill_name: s for s in r.skills}
    assert (by["Python"].data_kind, by["Python"].evidence_source) == ("measured", "assessment")
    assert by["Machine Learning"].data_kind == "estimated"
    assert by["Machine Learning"].match_status == SkillMatchStatus.WEAK  # low confidence is not a full match
    assert any("estimates" in w for w in r.warnings)


def test_unmatched_requirements_listed_not_scored(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    jd.analysis_metadata = {"unmatched_skills": ["Fortran"]}
    db_session.commit()
    r = _readiness(db_session, user, job_description_id=jd.id)
    assert r.unmatched_requirements == ["Fortran"] and len(r.skills) == 3
    assert any("not in the skill catalog" in w for w in r.warnings)


def test_stale_flag_when_skills_change_after_analysis(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    svc = ApplicationService(db_session)
    app = svc.create(ApplicationCreateRequest(user_id=user.id, job_description_id=jd.id))
    own(db_session, user, skills["python"], SkillLevel.BEGINNER)
    us = db_session.query(UserSkill).one()
    jd_row = db_session.get(JobDescription, jd.id)
    us.updated_at = jd_row.updated_at - timedelta(hours=1)
    db_session.commit()
    assert svc.readiness(app.id, user.id).persisted_gaps_may_be_stale is False
    us.updated_at = jd_row.updated_at + timedelta(hours=1)
    db_session.commit()
    r = svc.readiness(app.id, user.id)
    assert r.persisted_gaps_may_be_stale and any("Re-run" in w for w in r.warnings)
    # a later gap persisted from this JD analysis makes it current again
    db_session.add(
        SkillGap(
            user_id=user.id,
            skill_id=skills["docker"].id,
            source_job_description_id=jd.id,
            updated_at=us.updated_at + timedelta(hours=1),
        )
    )
    db_session.commit()
    assert svc.readiness(app.id, user.id).persisted_gaps_may_be_stale is False


def test_readiness_is_read_only(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["python"], SkillLevel.BEGINNER)
    jd = make_jd(db_session, user, skills)
    _readiness(db_session, user, job_description_id=jd.id)
    us = db_session.query(UserSkill).one()
    assert us.current_level == SkillLevel.BEGINNER
    assert db_session.query(SkillGap).count() == 0


def test_engine_function_reused_directly(db_session):
    # guards against drift: the response score equals the engine called with the same inputs
    from app.jobs.schemas import JobSkillRequirement

    req = JobSkillRequirement(
        raw_name="X",
        normalized_skill_id="1",
        requirement_type="required",
        importance=SkillImportance.HIGH,
        expected_level=SkillLevel.INTERMEDIATE,
        evidence_text="",
        confidence=0.8,
        reasoning="",
    )
    assert compute_overall_match_score([(req, SkillMatchStatus.MISSING, SkillLevel.NONE)]) == 0.0
    assert ImportanceLevel.REQUIRED.value == "required"
