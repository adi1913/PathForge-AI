from app.models.enums import EvidenceSource, ImportanceLevel, SkillImportance, SkillLevel
from app.models.job_description import JobDescription, JobDescriptionSkill
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from app.models.user import User


def seed(db):
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [("python", "Python"), ("machine-learning", "Machine Learning"), ("docker", "Docker")]
    }
    db.add_all(skills.values())
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    user = User(email="app@example.com", password_hash="h")
    other = User(email="other@example.com", password_hash="h")
    db.add_all([user, other])
    db.commit()
    return user, other, skills


def make_jd(db, user, skills, *, title="ML Engineer", company="Globex", rows=None):
    jd = JobDescription(user_id=user.id, title=title, company=company, raw_text=f"{title} {company} {id(rows)}")
    db.add(jd)
    db.flush()
    rows = (
        rows
        if rows is not None
        else [
            ("python", ImportanceLevel.REQUIRED, SkillImportance.HIGH, SkillLevel.INTERMEDIATE),
            ("machine-learning", ImportanceLevel.REQUIRED, SkillImportance.CRITICAL, SkillLevel.ADVANCED),
            ("docker", ImportanceLevel.PREFERRED, SkillImportance.LOW, SkillLevel.BEGINNER),
        ]
    )
    for slug, kind, crit, level in rows:
        db.add(
            JobDescriptionSkill(
                job_description_id=jd.id,
                skill_id=skills[slug].id,
                importance=kind,
                criticality=crit,
                required_level=level,
                confidence=0.8,
            )
        )
    db.commit()
    return jd


def own(db, user, skill, level, *, confidence=0.8, source=EvidenceSource.RESUME):
    db.add(UserSkill(user_id=user.id, skill_id=skill.id, current_level=level, confidence=confidence, source=source))
    db.commit()
