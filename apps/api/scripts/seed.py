"""
Development seed data — NOT production data.

Populates a small, realistic AI Engineer skill graph with prerequisite
chains, the AI Engineer target role requirements, and one demo user/
profile so later phases (roadmap generation, agent, dashboard) have
something real to query against.

Idempotent: safe to run more than once (get-or-create by slug/email).

Usage:
    python -m scripts.seed
"""

import sys

from app.core.config import get_settings
from app.db.session import SessionLocal
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
from app.security.passwords import hash_password

# (slug, name, category)
SKILLS = [
    ("python", "Python", "programming"),
    ("git", "Git", "tooling"),
    ("sql", "SQL", "data"),
    ("data-structures", "Data Structures & Algorithms", "fundamentals"),
    ("machine-learning", "Machine Learning", "ml"),
    ("deep-learning", "Deep Learning", "ml"),
    ("llm-genai", "LLMs / Generative AI", "genai"),
    ("rag", "Retrieval-Augmented Generation", "genai"),
    ("ai-agents", "AI Agents", "genai"),
    ("mcp", "Model Context Protocol", "genai"),
    ("fastapi", "FastAPI", "backend"),
    ("docker", "Docker", "infra"),
    ("aws", "AWS", "infra"),
]

# Linear prerequisite chain, per the project brief:
# python -> git -> sql -> data-structures -> machine-learning
#   -> deep-learning -> llm-genai -> rag -> ai-agents -> mcp
PREREQUISITE_CHAIN = [
    "python",
    "git",
    "sql",
    "data-structures",
    "machine-learning",
    "deep-learning",
    "llm-genai",
    "rag",
    "ai-agents",
    "mcp",
]

TARGET_ROLE_SLUG = "ai-engineer"
TARGET_ROLE_NAME = "AI Engineer"
# (skill_slug, required_level, importance)
TARGET_ROLE_REQUIREMENTS = [
    ("python", SkillLevel.ADVANCED, ImportanceLevel.REQUIRED),
    ("machine-learning", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("deep-learning", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("llm-genai", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("rag", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("ai-agents", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("mcp", SkillLevel.INTERMEDIATE, ImportanceLevel.REQUIRED),
    ("docker", SkillLevel.BEGINNER, ImportanceLevel.PREFERRED),
    ("aws", SkillLevel.BEGINNER, ImportanceLevel.PREFERRED),
    ("fastapi", SkillLevel.INTERMEDIATE, ImportanceLevel.PREFERRED),
]

DEMO_USER_EMAIL = "demo@pathforge.ai"
# Documented, DEMO-ONLY credential for local development. Never use outside local.
DEMO_USER_PASSWORD = "demo-password-change-me"


def get_or_create_skill(db, slug: str, name: str, category: str) -> Skill:
    existing = db.query(Skill).filter_by(slug=slug).one_or_none()
    if existing:
        return existing
    skill = Skill(slug=slug, name=name, category=category)
    db.add(skill)
    db.flush()
    return skill


def seed() -> None:
    if get_settings().ENVIRONMENT.lower() == "production":
        print("Refusing to seed demo data (demo user + known password) when ENVIRONMENT=production.")
        sys.exit(1)
    db = SessionLocal()
    try:
        skills_by_slug = {slug: get_or_create_skill(db, slug, name, category) for slug, name, category in SKILLS}
        db.flush()

        # Prerequisite chain
        for dependent_slug, prereq_slug in zip(PREREQUISITE_CHAIN[1:], PREREQUISITE_CHAIN[:-1], strict=True):
            dependent = skills_by_slug[dependent_slug]
            prereq = skills_by_slug[prereq_slug]
            exists = (
                db.query(SkillPrerequisite)
                .filter_by(skill_id=dependent.id, prerequisite_skill_id=prereq.id)
                .one_or_none()
            )
            if not exists:
                db.add(SkillPrerequisite(skill_id=dependent.id, prerequisite_skill_id=prereq.id))

        # Target role
        target_role = db.query(TargetRole).filter_by(slug=TARGET_ROLE_SLUG).one_or_none()
        if not target_role:
            target_role = TargetRole(
                slug=TARGET_ROLE_SLUG,
                name=TARGET_ROLE_NAME,
                description=(
                    "Builds and ships production LLM-powered systems: " "RAG, agents, and MCP-based tool integration."
                ),
            )
            db.add(target_role)
            db.flush()

        for skill_slug, required_level, importance in TARGET_ROLE_REQUIREMENTS:
            skill = skills_by_slug[skill_slug]
            exists = db.query(TargetRoleSkill).filter_by(target_role_id=target_role.id, skill_id=skill.id).one_or_none()
            if not exists:
                db.add(
                    TargetRoleSkill(
                        target_role_id=target_role.id,
                        skill_id=skill.id,
                        required_level=required_level,
                        importance=importance,
                    )
                )

        # Demo user + profile + a couple of self-reported skills, matching
        # the worked example from the project brief (knows Python + basic
        # ML, wants to become an AI Engineer in 4 months at 2h/day).
        user = db.query(User).filter_by(email=DEMO_USER_EMAIL).one_or_none()
        if not user:
            user = User(email=DEMO_USER_EMAIL, password_hash=hash_password(DEMO_USER_PASSWORD))
            db.add(user)
            db.flush()
            db.add(
                Profile(
                    user_id=user.id,
                    display_name="Demo User",
                    target_role=TARGET_ROLE_NAME,
                    available_hours_per_day=2.0,
                    target_duration_days=120,
                    timezone="Asia/Kolkata",
                )
            )
            db.add(
                UserSkill(
                    user_id=user.id,
                    skill_id=skills_by_slug["python"].id,
                    current_level=SkillLevel.ADVANCED,
                    confidence=0.8,
                    source=EvidenceSource.MANUAL,
                    evidence=[{"type": "manual", "note": "self-reported, seed data"}],
                )
            )
            db.add(
                UserSkill(
                    user_id=user.id,
                    skill_id=skills_by_slug["machine-learning"].id,
                    current_level=SkillLevel.BEGINNER,
                    confidence=0.5,
                    source=EvidenceSource.MANUAL,
                    evidence=[{"type": "manual", "note": "self-reported, seed data"}],
                )
            )

        db.commit()
        print(f"Seed complete: {len(SKILLS)} skills, 1 target role, demo user '{DEMO_USER_EMAIL}'.")
        print(f"Demo login (local development only): {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
