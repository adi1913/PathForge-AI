from app.models.enums import (
    RoadmapItemStatus,
    RoadmapItemType,
    RoadmapStatus,
    SkillLevel,
)
from app.models.roadmap import Roadmap
from app.models.skill import UserSkill
from app.roadmap.schemas import RoadmapGenerateRequest
from app.roadmap.service import RoadmapService
from tests.test_assessments.helpers import beginner_resource, gap, generate, own, run_attempt, seed


def _roadmap(db, user, hours=2.0):
    return RoadmapService(db).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=hours))


def _items(db, roadmap_id, skill_slug=None, item_type=None):
    roadmap = db.get(Roadmap, roadmap_id)
    db.refresh(roadmap)
    return [
        i
        for i in roadmap.items
        if (skill_slug is None or (i.skill and i.skill.slug == skill_slug))
        and (item_type is None or i.item_type == item_type)
    ]


async def _setup(db, python_conf=0.8):
    user, other, skills = seed(db)
    own(db, user, skills["python"], confidence=python_conf)
    gap(db, user, skills["machine-learning"])
    beginner_resource(db, skills["machine-learning"])
    roadmap = _roadmap(db, user)
    ml_item = next(
        i for i in roadmap.items if i.skill_slug == "machine-learning" and i.item_type == RoadmapItemType.SKILL
    )
    return user, skills, roadmap, ml_item


async def test_strong_result_shrinks_once_skips_beginner_material_and_replans(db_session):
    user, skills, roadmap, ml_item = await _setup(db_session)
    before = ml_item.estimated_minutes
    a = await generate(db_session, user, "machine-learning", roadmap_item_id=ml_item.id)
    result = await run_attempt(db_session, user, a.id, "correct")
    assert result.outcome.value == "strong" and result.adaptation.replanned
    kinds = {x.action for x in result.adaptation.actions}
    assert kinds == {"reduced_estimate", "skipped_beginner_resource"}

    skill_row = _items(db_session, roadmap.id, "machine-learning", RoadmapItemType.SKILL)[0]
    assert skill_row.estimated_minutes == max(120, round(before * 0.5)) < before
    assert skill_row.status == RoadmapItemStatus.NOT_STARTED  # never completed / mastered by an assessment
    resource = _items(db_session, roadmap.id, "machine-learning", RoadmapItemType.LEARNING_RESOURCE)[0]
    assert resource.status == RoadmapItemStatus.SKIPPED

    # a second strong result on a different question set must not shrink again
    after_first = skill_row.estimated_minutes
    a2 = await generate(db_session, user, "machine-learning", "quiz", 6, roadmap_item_id=ml_item.id)
    second = await run_attempt(db_session, user, a2.id, "correct")
    assert all(x.action != "reduced_estimate" for x in second.adaptation.actions)
    db_session.refresh(skill_row)
    assert skill_row.estimated_minutes == after_first


async def test_weak_result_adds_prerequisite_revision_and_exercises_in_order_without_duplicates(db_session):
    user, skills, roadmap, ml_item = await _setup(db_session, python_conf=0.2)  # python has no solid evidence
    a = await generate(db_session, user, "machine-learning", roadmap_item_id=ml_item.id)
    result = await run_attempt(db_session, user, a.id, "wrong")
    assert result.outcome.value == "weak" and result.adaptation.replanned
    assert {x.action for x in result.adaptation.actions} == {"added_prerequisite", "added_revision", "added_exercises"}

    foundation = _items(db_session, roadmap.id, "python", RoadmapItemType.SKILL)[0]
    ml = _items(db_session, roadmap.id, "machine-learning", RoadmapItemType.SKILL)[0]
    assert foundation.title == "Foundation: Learn Python" and foundation.id in ml.prerequisite_item_ids
    assert foundation.order_index < ml.order_index  # prerequisite ordering survives the re-plan
    revision = next(i for i in _items(db_session, roadmap.id) if i.title == "Revision: Machine Learning")
    exercises = next(i for i in _items(db_session, roadmap.id) if i.title == "Practice exercises: Machine Learning")
    assert revision.item_type == RoadmapItemType.LEARNING_RESOURCE and exercises.item_type == RoadmapItemType.PROJECT
    assert revision.order_index > ml.order_index and "no external resource" in revision.description
    assert ml.status == RoadmapItemStatus.NOT_STARTED

    again = await generate(db_session, user, "machine-learning", "quiz", 6, roadmap_item_id=ml_item.id)
    second = await run_attempt(db_session, user, again.id, "wrong")
    titles = [i.title for i in _items(db_session, roadmap.id)]
    assert titles.count("Revision: Machine Learning") == 1 and titles.count("Foundation: Learn Python") == 1
    assert second.adaptation.warnings == ["Roadmap already reflects this result."]


async def test_weak_result_with_solid_prerequisite_adds_only_revision_and_exercises(db_session):
    user, skills, roadmap, ml_item = await _setup(db_session, python_conf=0.8)
    a = await generate(db_session, user, "machine-learning", roadmap_item_id=ml_item.id)
    result = await run_attempt(db_session, user, a.id, "wrong")
    assert {x.action for x in result.adaptation.actions} == {"added_revision", "added_exercises"}


async def test_passed_result_changes_nothing_and_user_skill_level_is_untouched(db_session):
    user, skills, roadmap, ml_item = await _setup(db_session)
    own(db_session, user, skills["machine-learning"], SkillLevel.BEGINNER, 0.5)
    a = await generate(db_session, user, "machine-learning", "mixed", 7, roadmap_item_id=ml_item.id)
    result = await run_attempt(db_session, user, a.id, "mcq_only")  # MCQ right, rubric answers missing
    assert result.outcome.value == "passed", result.score_percent
    assert result.adaptation.actions == [] and not result.adaptation.replanned
    row = db_session.get(UserSkill, (user.id, skills["machine-learning"].id))
    assert row.current_level == SkillLevel.BEGINNER


async def test_no_roadmap_and_archived_roadmap_are_reported_not_changed(db_session):
    user, other, skills = seed(db_session)
    a = await generate(db_session, user, "rag")
    result = await run_attempt(db_session, user, a.id, "wrong")
    assert result.adaptation.actions == [] and "No active roadmap item" in result.adaptation.warnings[0]

    user2, skills2, roadmap, ml_item = await _setup_second(db_session)
    db_session.get(Roadmap, roadmap.id).status = RoadmapStatus.ARCHIVED
    db_session.commit()
    a2 = await generate(db_session, user2, "machine-learning", roadmap_item_id=ml_item.id)
    archived = await run_attempt(db_session, user2, a2.id, "wrong")
    assert archived.adaptation.actions == []
    assert [i.title for i in _items(db_session, roadmap.id)].count("Revision: Machine Learning") == 0


async def _setup_second(db):
    from app.models.user import User

    user2 = User(email="second@example.com", password_hash="h")
    db.add(user2)
    db.commit()
    from app.models.skill import Skill

    skills = {s.slug: s for s in db.query(Skill).all()}
    own(db, user2, skills["python"])
    gap(db, user2, skills["machine-learning"])
    roadmap = _roadmap(db, user2)
    item = next(i for i in roadmap.items if i.skill_slug == "machine-learning" and i.item_type == RoadmapItemType.SKILL)
    return user2, skills, roadmap, item


async def test_foreign_roadmap_item_cannot_be_used(db_session):
    import pytest

    from app.assessments.errors import RoadmapItemForAssessmentError

    user, skills, roadmap, ml_item = await _setup(db_session)
    from app.models.user import User

    intruder = User(email="intruder@example.com", password_hash="h")
    db_session.add(intruder)
    db_session.commit()
    with pytest.raises(RoadmapItemForAssessmentError):
        await generate(db_session, intruder, "machine-learning", roadmap_item_id=ml_item.id)
