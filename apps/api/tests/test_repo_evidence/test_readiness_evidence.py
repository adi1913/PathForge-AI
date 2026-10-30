"""Phase 10 readiness + Phase 11 repository evidence: shown side by side, score untouched."""

from app.applications.schemas import ApplicationCreateRequest
from app.applications.service import ApplicationService
from app.models.enums import EvidenceSource, ImportanceLevel, SkillImportance, SkillLevel
from app.models.skill import UserSkill
from app.repo_evidence.schemas import EvaluateRequest
from app.repo_evidence.service import RepositoryEvaluationService
from tests.test_applications.helpers import make_jd
from tests.test_repo_evidence.helpers import FakeManager, seed

_ROWS = [
    ("python", ImportanceLevel.REQUIRED, SkillImportance.HIGH, SkillLevel.INTERMEDIATE),
    ("fastapi", ImportanceLevel.REQUIRED, SkillImportance.HIGH, SkillLevel.INTERMEDIATE),
    ("docker", ImportanceLevel.PREFERRED, SkillImportance.LOW, SkillLevel.BEGINNER),
]


def _readiness(db, user, jd):
    svc = ApplicationService(db)
    app = svc.create(ApplicationCreateRequest(user_id=user.id, job_description_id=jd.id))
    return svc.readiness(app.id, user.id)


async def _evaluate(db, user):
    await RepositoryEvaluationService(db, FakeManager()).evaluate(
        EvaluateRequest(user_id=user.id, repository_url="octocat/rag-demo")
    )


async def test_evidence_is_shown_but_score_and_status_are_unchanged(db_session):
    user, _, skills = seed(db_session)
    db_session.add(
        UserSkill(
            user_id=user.id,
            skill_id=skills["python"].id,
            current_level=SkillLevel.ADVANCED,
            confidence=0.9,
            source=EvidenceSource.ASSESSMENT,
        )
    )
    db_session.commit()
    jd = make_jd(db_session, user, skills, rows=_ROWS)
    before = _readiness(db_session, user, jd)
    assert all(s.github_evidence == [] for s in before.skills)

    await _evaluate(db_session, user)
    svc = ApplicationService(db_session)
    app_id = svc.list(user.id).items[0].id
    after = svc.readiness(app_id, user.id)

    assert after.overall_match_score == before.overall_match_score
    assert [(s.skill_name, s.match_status, s.severity, s.priority_score) for s in after.skills] == [
        (s.skill_name, s.match_status, s.severity, s.priority_score) for s in before.skills
    ]
    by = {s.skill_name: s for s in after.skills}
    fastapi = by["FastAPI"]
    assert fastapi.match_status.value == "missing"  # evidence did not turn a missing skill into a match
    assert {e.evidence_type.value for e in fastapi.github_evidence} == {"dependency_manifest", "readme_mention"}
    assert fastapi.github_evidence[0].repository == "octocat/rag-demo"
    assert by["Docker"].github_evidence and by["Python"].github_evidence
    warning = next(w for w in after.warnings if "Repository evidence exists for" in w)
    assert "FastAPI" in warning and "Docker" in warning and "Python" not in warning
    assert "not proficiency" in warning


async def test_only_latest_evaluation_is_used_and_user_skills_untouched(db_session):
    user, other, skills = seed(db_session)
    jd = make_jd(db_session, user, skills, rows=_ROWS)
    await _evaluate(db_session, user)
    await _evaluate(db_session, user)
    await _evaluate(db_session, other)  # another user's evidence must not leak in
    r = _readiness(db_session, user, jd)
    fastapi = next(s for s in r.skills if s.skill_name == "FastAPI")
    assert len(fastapi.github_evidence) == 2
    assert db_session.query(UserSkill).count() == 0
