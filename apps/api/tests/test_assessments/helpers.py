"""Shared seeding/answer helpers. Tests may read answer keys from the DB; the API never exposes them."""

from app.assessments import grading
from app.assessments.schemas import AnswerIn, GenerateRequest, SubmitRequest
from app.assessments.service import AssessmentService
from app.models.assessment import Question
from app.models.enums import (
    Difficulty,
    EvidenceSource,
    GapSeverity,
    ResourceType,
    SkillGapStatus,
    SkillImportance,
    SkillLevel,
    SkillMatchStatus,
)
from app.models.learning_resource import LearningResource
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from app.models.skill_gap import SkillGap
from app.models.user import User


def seed(db):
    """python <- machine-learning <- rag ; docker standalone. User owns python (solid) only."""
    skills = {}
    for slug, name in [
        ("python", "Python"),
        ("machine-learning", "Machine Learning"),
        ("rag", "RAG"),
        ("docker", "Docker"),
        ("git", "Git"),
    ]:
        skills[slug] = Skill(slug=slug, name=name)
        db.add(skills[slug])
    db.flush()
    db.add(SkillPrerequisite(skill_id=skills["machine-learning"].id, prerequisite_skill_id=skills["python"].id))
    db.add(SkillPrerequisite(skill_id=skills["rag"].id, prerequisite_skill_id=skills["machine-learning"].id))
    user = User(email="learner@example.com", password_hash="h")
    other = User(email="other@example.com", password_hash="h")
    db.add_all([user, other])
    db.commit()
    return user, other, skills


def own(db, user, skill, level=SkillLevel.INTERMEDIATE, confidence=0.6, source=EvidenceSource.RESUME):
    row = UserSkill(
        user_id=user.id,
        skill_id=skill.id,
        current_level=level,
        confidence=confidence,
        source=source,
        evidence=[{"type": "resume", "text": "x", "section": "skills"}],
    )
    db.add(row)
    db.commit()
    return row


def gap(db, user, skill, priority=80.0, target=SkillLevel.INTERMEDIATE):
    db.add(
        SkillGap(
            user_id=user.id,
            skill_id=skill.id,
            current_level=SkillLevel.NONE,
            target_level=target,
            priority_score=priority,
            match_status=SkillMatchStatus.MISSING,
            severity=GapSeverity.HIGH,
            importance=SkillImportance.HIGH,
            status=SkillGapStatus.OPEN,
        )
    )
    db.commit()


def beginner_resource(db, skill, title="Intro resource"):
    db.add(
        LearningResource(
            title=title,
            resource_type=ResourceType.COURSE,
            skill_id=skill.id,
            difficulty=Difficulty.BEGINNER,
            estimated_minutes=60,
            provider="demo",
        )
    )
    db.commit()


def answers_for(db, assessment_id, mode):
    """mode: 'correct' | 'wrong' | 'mcq_only'. Built from the stored key (tests only)."""
    out = []
    questions = db.query(Question).filter_by(assessment_id=assessment_id).order_by(Question.order_index).all()
    for q in questions:
        if q.question_type.value == "multiple_choice":
            right = q.expected_answer
            wrong = next(x for x in "ABCD" if x != right)
            out.append(AnswerIn(question_id=q.id, answer=right if mode in ("correct", "mcq_only") else wrong))
        elif mode == "correct":
            parts = [c.any_of[0] for c in grading.parse_rubric(q.evaluation_rubric)]
            out.append(AnswerIn(question_id=q.id, answer=" ".join(parts) + " and some more words to be long enough"))
        else:
            out.append(AnswerIn(question_id=q.id, answer="I have no idea at all about this topic really"))
    return out


async def run_attempt(db, user, assessment_id, mode, service=None):
    service = service or AssessmentService(db)
    from app.assessments.schemas import AttemptStartRequest

    started = service.start_attempt(assessment_id, AttemptStartRequest(user_id=user.id))
    return service.submit(
        started.attempt_id, SubmitRequest(user_id=user.id, answers=answers_for(db, assessment_id, mode))
    )


async def generate(db, user, slug="rag", kind="quiz", count=5, service=None, **extra):
    service = service or AssessmentService(db)
    return await service.generate(
        GenerateRequest(user_id=user.id, skill_slug=slug, assessment_type=kind, question_count=count, **extra)
    )
