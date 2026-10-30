import pytest

from app.models.enums import (
    Difficulty,
    ProgressEventType,
    ResourceType,
    RoadmapItemStatus,
    RoadmapItemType,
    RoadmapStatus,
    SkillLevel,
)
from app.models.learning_resource import LearningResource
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import UserSkill
from app.roadmap.errors import NothingToReplanError, RoadmapArchivedError, RoadmapNotFoundError
from app.roadmap.progress import ProgressService
from app.roadmap.replan import ReplanService
from app.roadmap.schemas import ProgressUpdateRequest, ReplanRequest, RoadmapGenerateRequest
from app.roadmap.service import RoadmapService
from tests.test_roadmap.helpers import _gap, _own, _seed

S = RoadmapItemStatus


def _setup(db, hours=2, with_resource=False):
    """Items: python(480) <- machine-learning(480) <- deep-learning(1380), docker(1380). Total 3720."""
    user, skills = _seed(db)
    _gap(db, user, skills["deep-learning"], priority=80)
    _gap(db, user, skills["docker"], priority=40)
    if with_resource:
        db.add(
            LearningResource(
                title="Docker 101",
                resource_type=ResourceType.COURSE,
                skill_id=skills["docker"].id,
                difficulty=Difficulty.INTERMEDIATE,
                estimated_minutes=60,
            )
        )
        db.commit()
    roadmap = RoadmapService(db).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=hours))
    items = {i.skill_slug: i for i in roadmap.items if i.item_type == RoadmapItemType.SKILL}
    return user, skills, roadmap, items


def _progress(db, user, roadmap, item, status, pct=None):
    return ProgressService(db).update_item(
        roadmap.id, item.id, ProgressUpdateRequest(user_id=user.id, status=status, completion_percentage=pct)
    )


def _replan(db, user, roadmap, **kw):
    return ReplanService(db).replan(roadmap.id, ReplanRequest(user_id=user.id, **kw))


def _skill_slugs(resp):
    return [i.skill_slug for i in resp.roadmap.items if i.item_type == RoadmapItemType.SKILL]


def test_no_items_completed_keeps_plan_and_effort(db_session):
    user, _, roadmap, items = _setup(db_session)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)
    assert resp.replan.remaining_skills == 4 and resp.replan.resolved_skills == 0
    assert resp.replan.remaining_minutes == 3720
    assert _skill_slugs(resp) == [i.skill_slug for i in roadmap.items if i.item_type == RoadmapItemType.SKILL]
    assert resp.replan.changed_items == 0
    assert resp.roadmap.id == roadmap.id


def test_completed_items_preserved_first_and_excluded_from_schedule(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)

    assert resp.replan.resolved_skills == 1 and resp.replan.remaining_minutes == 3240
    out = {i.skill_slug: i for i in resp.roadmap.items}
    assert out["python"].status == S.COMPLETED and out["python"].completion_percentage == 100
    assert out["python"].order_index == 1
    assert out["machine-learning"].week_number == 1  # week 1 = now
    assert [i.order_index for i in resp.roadmap.items] == list(range(1, len(resp.roadmap.items) + 1))


def test_partial_progress_reduces_remaining_effort(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.IN_PROGRESS, 50)
    assert _replan(db_session, user, roadmap, hours_per_day=2).replan.remaining_minutes == 3720 - 240


def test_raised_proficiency_shrinks_estimate(db_session):
    user, skills, roadmap, _ = _setup(db_session)
    _own(db_session, user, skills["python"], SkillLevel.INTERMEDIATE)  # foundation target is beginner -> floor
    assert _replan(db_session, user, roadmap, hours_per_day=2).replan.remaining_minutes == 3720 - 480 + 120


def test_stored_estimates_untouched_so_replan_is_idempotent(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.IN_PROGRESS, 50)
    first = _replan(db_session, user, roadmap, hours_per_day=2)
    second = _replan(db_session, user, roadmap, hours_per_day=2)
    assert first.replan.remaining_minutes == second.replan.remaining_minutes
    assert [(i.id, i.order_index, i.week_number) for i in first.roadmap.items] == [
        (i.id, i.order_index, i.week_number) for i in second.roadmap.items
    ]
    assert db_session.query(RoadmapItem).filter_by(roadmap_id=roadmap.id).count() == len(roadmap.items)


def test_all_items_completed_cannot_be_replanned(db_session):
    user, _, roadmap, items = _setup(db_session)
    for item in items.values():
        _progress(db_session, user, roadmap, item, S.COMPLETED)
    with pytest.raises(NothingToReplanError):
        _replan(db_session, user, roadmap)


def test_skipped_counts_as_resolved(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["docker"], S.SKIPPED)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)
    assert resp.replan.resolved_skills == 1 and resp.replan.remaining_minutes == 3720 - 1380
    assert {i.skill_slug: i.status for i in resp.roadmap.items}["docker"] == S.SKIPPED


def test_blocked_prerequisite_stalls_dependents_and_schedules_them_last(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["machine-learning"], S.BLOCKED)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)

    order = _skill_slugs(resp)
    assert order.index("docker") < order.index("machine-learning") < order.index("deep-learning")
    assert order.index("python") < order.index("machine-learning")  # prerequisites still first
    assert sorted(resp.replan.stalled_skills) == ["Deep Learning", "Machine Learning"]
    assert any("Blocked work" in w for w in resp.roadmap.warnings)
    assert len(order) == 4  # nothing dropped
    assert {i.skill_slug: i.status for i in resp.roadmap.items}["machine-learning"] == S.BLOCKED


def test_feasible_deadline(db_session):
    user, _, roadmap, _ = _setup(db_session)
    resp = _replan(db_session, user, roadmap, hours_per_day=4, duration_days=365)
    assert resp.replan.fits_deadline is True and resp.roadmap.warnings == []
    assert db_session.get(Roadmap, roadmap.id).duration_days == 365


def test_infeasible_deadline_warns_and_keeps_everything(db_session):
    user, _, roadmap, _ = _setup(db_session)
    resp = _replan(db_session, user, roadmap, hours_per_day=1, duration_days=7)
    assert resp.replan.fits_deadline is False and resp.replan.estimated_days > 7
    assert any("deadline" in w for w in resp.roadmap.warnings)
    assert resp.replan.remaining_skills == 4 and len(_skill_slugs(resp)) == 4


def test_changed_availability_changes_schedule(db_session):
    user, _, roadmap, _ = _setup(db_session)
    slow = _replan(db_session, user, roadmap, hours_per_day=1)
    fast = _replan(db_session, user, roadmap, hours_per_day=4)
    assert fast.replan.estimated_days < slow.replan.estimated_days
    assert max(i.week_number for i in fast.roadmap.items) < max(i.week_number for i in slow.roadmap.items)
    assert fast.replan.hours_per_day == 4


def test_repeated_replans_record_history_and_keep_one_roadmap(db_session):
    user, _, roadmap, items = _setup(db_session)
    _replan(db_session, user, roadmap, hours_per_day=2)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    _replan(db_session, user, roadmap, hours_per_day=1)
    third = _replan(db_session, user, roadmap, hours_per_day=3)

    events = db_session.query(ProgressEvent).filter_by(event_type=ProgressEventType.ROADMAP_REPLANNED).all()
    assert len(events) == 3
    assert all((e.event_metadata or {}).get("roadmap_id") == roadmap.id for e in events)
    assert db_session.query(Roadmap).filter_by(user_id=user.id).count() == 1
    assert ProgressService(db_session).get_progress(roadmap.id, user.id).replan_count == 3
    assert third.roadmap.items[0].skill_slug == "python"  # completed work stays first


def test_replan_event_records_changes(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    resp = _replan(db_session, user, roadmap, hours_per_day=1)
    event = db_session.query(ProgressEvent).filter_by(event_type=ProgressEventType.ROADMAP_REPLANNED).one()
    assert event.event_metadata["hours_per_day"] == 1.0
    assert len(event.event_metadata["changes"]) == resp.replan.changed_items


def test_resources_follow_their_skill_item_and_are_not_duplicated(db_session):
    user, _, roadmap, items = _setup(db_session, with_resource=True)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)
    titles = [i.title for i in resp.roadmap.items]
    assert titles.count("Docker 101") == 1
    assert titles.index("Docker 101") == titles.index("Learn Docker") + 1
    resource = next(i for i in resp.roadmap.items if i.title == "Docker 101")
    docker = next(i for i in resp.roadmap.items if i.title == "Learn Docker")
    assert resource.week_number == docker.week_number


def test_replan_never_changes_status_or_user_skills(db_session):
    user, skills, roadmap, items = _setup(db_session)
    _own(db_session, user, skills["python"], SkillLevel.BEGINNER)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    _progress(db_session, user, roadmap, items["docker"], S.IN_PROGRESS, 30)
    before = {i.id: (i.status, i.completion_percentage) for i in db_session.query(RoadmapItem)}
    _replan(db_session, user, roadmap, hours_per_day=2)
    db_session.expire_all()
    assert {i.id: (i.status, i.completion_percentage) for i in db_session.query(RoadmapItem)} == before
    assert db_session.query(UserSkill).one().current_level == SkillLevel.BEGINNER


def test_in_progress_item_goes_first_among_ready(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    _progress(db_session, user, roadmap, items["machine-learning"], S.COMPLETED)
    _progress(db_session, user, roadmap, items["docker"], S.IN_PROGRESS, 10)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)
    remaining = [s for s in _skill_slugs(resp) if s not in ("python", "machine-learning")]
    assert remaining[0] == "docker"  # in-progress ahead of higher-priority deep-learning


def test_replan_persists_after_reload(db_session):
    user, _, roadmap, items = _setup(db_session)
    _progress(db_session, user, roadmap, items["python"], S.COMPLETED)
    resp = _replan(db_session, user, roadmap, hours_per_day=1, duration_days=200)
    db_session.expire_all()
    fetched = RoadmapService(db_session).get(roadmap.id)
    assert [(i.id, i.order_index, i.week_number) for i in fetched.items] == [
        (i.id, i.order_index, i.week_number) for i in resp.roadmap.items
    ]
    assert fetched.summary.deadline_days == 200


def test_completed_roadmap_with_reopened_item_replans_and_is_active(db_session):
    user, _, roadmap, items = _setup(db_session)
    for item in items.values():
        _progress(db_session, user, roadmap, item, S.COMPLETED)
    _progress(db_session, user, roadmap, items["docker"], S.IN_PROGRESS)
    resp = _replan(db_session, user, roadmap, hours_per_day=2)
    assert resp.roadmap.status == RoadmapStatus.ACTIVE and resp.replan.remaining_skills == 1


def test_other_users_roadmap_is_not_found_and_unchanged(db_session):
    from app.models.user import User

    user, _, roadmap, _ = _setup(db_session)
    other = User(email="other@example.com", password_hash="h")
    db_session.add(other)
    db_session.commit()
    before = [(i.id, i.order_index, i.week_number) for i in db_session.query(RoadmapItem).order_by(RoadmapItem.id)]
    with pytest.raises(RoadmapNotFoundError):
        ReplanService(db_session).replan(roadmap.id, ReplanRequest(user_id=other.id, hours_per_day=1))
    assert [
        (i.id, i.order_index, i.week_number) for i in db_session.query(RoadmapItem).order_by(RoadmapItem.id)
    ] == before
    assert db_session.query(ProgressEvent).filter_by(event_type=ProgressEventType.ROADMAP_REPLANNED).count() == 0


def test_unknown_roadmap_and_archived_roadmap(db_session):
    user, skills, roadmap, _ = _setup(db_session)
    with pytest.raises(RoadmapNotFoundError):
        ReplanService(db_session).replan("nope", ReplanRequest(user_id=user.id))
    RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=2))  # archives first
    with pytest.raises(RoadmapArchivedError):
        _replan(db_session, user, roadmap)


def test_pace_falls_back_to_profile_then_default(db_session):
    from app.models.profile import Profile

    user, _, roadmap, _ = _setup(db_session)
    resp = _replan(db_session, user, roadmap)
    assert resp.replan.hours_per_day == 1.0 and any("assumed" in w for w in resp.roadmap.warnings)
    db_session.add(Profile(user_id=user.id, available_hours_per_day=3.0, target_duration_days=90))
    db_session.commit()
    resp = _replan(db_session, user, roadmap)
    assert resp.replan.hours_per_day == 3.0 and resp.replan.deadline_days == 90
