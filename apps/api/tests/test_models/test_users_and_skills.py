import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Profile,
    Skill,
    SkillPrerequisite,
    TargetRole,
    TargetRoleSkill,
    User,
    UserSkill,
)
from app.models.enums import EvidenceSource, ImportanceLevel, SkillLevel


def make_user(db, email="a@example.com"):
    user = User(email=email, password_hash="hashed")
    db.add(user)
    db.flush()
    return user


def test_user_email_must_be_unique(db_session):
    make_user(db_session, "dup@example.com")
    db_session.commit()

    db_session.add(User(email="dup@example.com", password_hash="hashed2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_profile_one_to_one_and_cascade_delete(db_session):
    user = make_user(db_session)
    db_session.add(Profile(user_id=user.id, display_name="Test User", target_role="AI Engineer"))
    db_session.commit()

    assert user.profile is not None
    assert user.profile.display_name == "Test User"

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(Profile).count() == 0


def test_skill_prerequisite_graph(db_session):
    python = Skill(slug="python", name="Python")
    ml = Skill(slug="ml", name="Machine Learning")
    dl = Skill(slug="dl", name="Deep Learning")
    db_session.add_all([python, ml, dl])
    db_session.flush()

    db_session.add(SkillPrerequisite(skill_id=ml.id, prerequisite_skill_id=python.id))
    db_session.add(SkillPrerequisite(skill_id=dl.id, prerequisite_skill_id=ml.id))
    db_session.commit()

    db_session.refresh(ml)
    db_session.refresh(dl)
    assert [s.slug for s in ml.prerequisites] == ["python"]
    assert [s.slug for s in dl.prerequisites] == ["ml"]
    assert [s.slug for s in python.unlocks] == ["ml"]


def test_skill_prerequisite_cannot_reference_itself(db_session):
    python = Skill(slug="python2", name="Python")
    db_session.add(python)
    db_session.flush()

    db_session.add(SkillPrerequisite(skill_id=python.id, prerequisite_skill_id=python.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_skill_stores_evidence_not_just_a_claim(db_session):
    user = make_user(db_session, "evidence@example.com")
    skill = Skill(slug="rag", name="RAG")
    db_session.add(skill)
    db_session.flush()

    db_session.add(
        UserSkill(
            user_id=user.id,
            skill_id=skill.id,
            current_level=SkillLevel.INTERMEDIATE,
            confidence=0.7,
            source=EvidenceSource.GITHUB,
            evidence=[{"type": "github", "repo": "user/rag-demo"}],
        )
    )
    db_session.commit()

    stored = db_session.query(UserSkill).filter_by(user_id=user.id, skill_id=skill.id).one()
    assert stored.current_level == SkillLevel.INTERMEDIATE
    assert stored.source == EvidenceSource.GITHUB
    assert stored.evidence[0]["repo"] == "user/rag-demo"


def test_user_skill_unique_per_user_and_skill(db_session):
    user = make_user(db_session, "unique-skill@example.com")
    skill = Skill(slug="python3", name="Python")
    db_session.add(skill)
    db_session.flush()

    db_session.add(UserSkill(user_id=user.id, skill_id=skill.id, source=EvidenceSource.MANUAL))
    db_session.commit()

    db_session.add(UserSkill(user_id=user.id, skill_id=skill.id, source=EvidenceSource.MANUAL))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_target_role_required_skills(db_session):
    role = TargetRole(slug="ai-engineer-test", name="AI Engineer")
    skill = Skill(slug="mcp-test", name="MCP")
    db_session.add_all([role, skill])
    db_session.flush()

    db_session.add(
        TargetRoleSkill(
            target_role_id=role.id,
            skill_id=skill.id,
            required_level=SkillLevel.INTERMEDIATE,
            importance=ImportanceLevel.REQUIRED,
        )
    )
    db_session.commit()

    db_session.refresh(role)
    assert len(role.required_skills) == 1
    assert role.required_skills[0].skill.slug == "mcp-test"
    assert role.required_skills[0].importance == ImportanceLevel.REQUIRED
