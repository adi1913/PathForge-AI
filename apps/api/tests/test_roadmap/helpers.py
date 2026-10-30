"""Shared seeding helpers for roadmap tests."""

from app.models.enums import GapSeverity, SkillGapStatus, SkillImportance, SkillLevel, SkillMatchStatus
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from app.models.skill_gap import SkillGap
from app.models.user import User


def _seed(db):
    """python <- machine-learning <- deep-learning; docker standalone."""
    skills = {}
    for slug, name in [
        ("python", "Python"),
        ("machine-learning", "Machine Learning"),
        ("deep-learning", "Deep Learning"),
        ("docker", "Docker"),
    ]:
        skills[slug] = Skill(slug=slug, name=name)
        db.add(skills[slug])
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    db.add(SkillPrerequisite(skill_id=skills["deep-learning"].id, prerequisite_skill_id=skills["machine-learning"].id))
    user = User(email="road@example.com", password_hash="h")
    db.add(user)
    db.commit()
    return user, skills


def _gap(
    db,
    user,
    skill,
    *,
    priority,
    current=SkillLevel.NONE,
    target=SkillLevel.INTERMEDIATE,
    status=SkillGapStatus.OPEN,
    match=SkillMatchStatus.MISSING,
):
    db.add(
        SkillGap(
            user_id=user.id,
            skill_id=skill.id,
            current_level=current,
            target_level=target,
            priority_score=priority,
            match_status=match,
            severity=GapSeverity.HIGH,
            importance=SkillImportance.HIGH,
            status=status,
        )
    )
    db.commit()


def _own(db, user, skill, level=SkillLevel.INTERMEDIATE):
    db.add(UserSkill(user_id=user.id, skill_id=skill.id, current_level=level, confidence=0.8, evidence=[]))
    db.commit()
