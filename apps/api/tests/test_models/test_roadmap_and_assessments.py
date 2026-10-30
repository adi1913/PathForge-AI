from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    Project,
    ProjectEvaluation,
    Question,
    Roadmap,
    RoadmapItem,
    Skill,
    User,
)
from app.models.enums import (
    AssessmentType,
    QuestionType,
    RoadmapItemStatus,
    RoadmapItemType,
)


def make_user(db, email="roadmap@example.com"):
    user = User(email=email, password_hash="hashed")
    db.add(user)
    db.flush()
    return user


def test_roadmap_items_ordered_deterministically(db_session):
    user = make_user(db_session)
    roadmap = Roadmap(user_id=user.id, title="AI Engineer Plan")
    db_session.add(roadmap)
    db_session.flush()

    db_session.add_all(
        [
            RoadmapItem(roadmap_id=roadmap.id, title="Week 3", order_index=2, item_type=RoadmapItemType.SKILL),
            RoadmapItem(roadmap_id=roadmap.id, title="Week 1", order_index=0, item_type=RoadmapItemType.SKILL),
            RoadmapItem(roadmap_id=roadmap.id, title="Week 2", order_index=1, item_type=RoadmapItemType.SKILL),
        ]
    )
    db_session.commit()

    db_session.refresh(roadmap)
    assert [item.title for item in roadmap.items] == ["Week 1", "Week 2", "Week 3"]


def test_roadmap_item_order_index_unique_within_roadmap(db_session):
    user = make_user(db_session, "order@example.com")
    roadmap = Roadmap(user_id=user.id, title="Plan")
    db_session.add(roadmap)
    db_session.flush()

    db_session.add(RoadmapItem(roadmap_id=roadmap.id, title="A", order_index=0))
    db_session.commit()

    db_session.add(RoadmapItem(roadmap_id=roadmap.id, title="B", order_index=0))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_roadmap_item_status_defaults_and_updates(db_session):
    user = make_user(db_session, "status@example.com")
    roadmap = Roadmap(user_id=user.id, title="Plan")
    db_session.add(roadmap)
    db_session.flush()

    item = RoadmapItem(roadmap_id=roadmap.id, title="Learn RAG", order_index=0)
    db_session.add(item)
    db_session.commit()

    assert item.status == RoadmapItemStatus.NOT_STARTED
    assert item.completion_percentage == 0.0

    item.status = RoadmapItemStatus.COMPLETED
    item.completion_percentage = 100.0
    db_session.commit()
    db_session.refresh(item)
    assert item.status == RoadmapItemStatus.COMPLETED


def test_assessment_attempt_and_answer_history(db_session):
    user = make_user(db_session, "assess@example.com")
    skill = Skill(slug="rag-assess", name="RAG")
    db_session.add(skill)
    db_session.flush()

    assessment = Assessment(user_id=user.id, skill_id=skill.id, title="RAG basics", assessment_type=AssessmentType.QUIZ)
    db_session.add(assessment)
    db_session.flush()

    question = Question(
        assessment_id=assessment.id,
        question_text="What does RAG stand for?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        options=["Retrieval-Augmented Generation", "Random Access Graph"],
        expected_answer="Retrieval-Augmented Generation",
    )
    db_session.add(question)
    db_session.flush()

    attempt = AssessmentAttempt(
        assessment_id=assessment.id,
        user_id=user.id,
        started_at=datetime.now(timezone.utc),
        score=95.0,
    )
    db_session.add(attempt)
    db_session.flush()

    db_session.add(
        AssessmentAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            answer="Retrieval-Augmented Generation",
            is_correct=True,
            score=1.0,
        )
    )
    db_session.commit()

    db_session.refresh(attempt)
    assert len(attempt.answers) == 1
    assert attempt.answers[0].is_correct is True
    # expected_answer must never be silently dropped from storage (that
    # would break grading) — it just must never reach a public API schema,
    # which is enforced at the schema layer, not here.
    assert question.expected_answer == "Retrieval-Augmented Generation"


def test_assessment_cascade_delete_removes_questions_and_attempts(db_session):
    user = make_user(db_session, "cascade@example.com")
    assessment = Assessment(user_id=user.id, title="Temp quiz", assessment_type=AssessmentType.QUIZ)
    db_session.add(assessment)
    db_session.flush()
    db_session.add(Question(assessment_id=assessment.id, question_text="Q?", question_type=QuestionType.SHORT_ANSWER))
    db_session.commit()

    db_session.delete(assessment)
    db_session.commit()

    assert db_session.query(Question).count() == 0


def test_project_evaluation_score_range_constraint(db_session):
    user = make_user(db_session, "eval@example.com")
    project = Project(user_id=user.id, title="Bot detector")
    db_session.add(project)
    db_session.flush()

    db_session.add(ProjectEvaluation(project_id=project.id, overall_score=150))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_project_evaluation_valid_scores(db_session):
    user = make_user(db_session, "eval2@example.com")
    project = Project(user_id=user.id, title="Bot detector 2")
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectEvaluation(
            project_id=project.id,
            overall_score=82,
            code_quality_score=17,
            testing_score=10,
            strengths=["clean architecture"],
            weaknesses=["low test coverage"],
        )
    )
    db_session.commit()

    saved = db_session.query(ProjectEvaluation).filter_by(project_id=project.id).one()
    assert saved.overall_score == 82
    assert saved.weaknesses == ["low test coverage"]
