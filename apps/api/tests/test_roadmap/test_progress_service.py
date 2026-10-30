import pytest

from app.models.enums import ProgressEventType, RoadmapItemStatus, RoadmapStatus, SkillLevel
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import UserSkill
from app.models.user import User
from app.roadmap.errors import (
    InvalidProgressInputError,
    InvalidTransitionError,
    RoadmapArchivedError,
    RoadmapItemNotFoundError,
    RoadmapNotFoundError,
)
from app.roadmap.progress import ProgressService
from app.roadmap.schemas import ProgressUpdateRequest, RoadmapGenerateRequest
from app.roadmap.service import RoadmapService
from tests.test_roadmap.helpers import _gap, _own, _seed

S = RoadmapItemStatus


def _setup(db):
    """python <- machine-learning <- deep-learning, all three skill items on the roadmap."""
    user, skills = _seed(db)
    _gap(db, user, skills["deep-learning"], priority=80)
    roadmap = RoadmapService(db).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=2))
    items = {i.skill_slug: i for i in roadmap.items}
    return user, skills, roadmap, items


def _update(db, user, roadmap, item, status, pct=None):
    return ProgressService(db).update_item(
        roadmap.id, item.id, ProgressUpdateRequest(user_id=user.id, status=status, completion_percentage=pct)
    )


def test_start_then_percent_then_complete_records_events_and_timestamps(db_session):
    user, _, roadmap, items = _setup(db_session)
    py = items["python"]
    started = _update(db_session, user, roadmap, py, S.IN_PROGRESS)
    assert started.item.status == S.IN_PROGRESS and started.item.completion_percentage == 0
    assert started.item.started_at is not None and started.item.completed_at is None

    partial = _update(db_session, user, roadmap, py, S.IN_PROGRESS, 40)
    assert partial.item.completion_percentage == 40

    done = _update(db_session, user, roadmap, py, S.COMPLETED)
    assert done.item.completion_percentage == 100 and done.item.completed_at is not None
    assert done.summary.completed == 1

    types = [e.event_type for e in db_session.query(ProgressEvent).order_by(ProgressEvent.created_at, ProgressEvent.id)]
    assert types == [
        ProgressEventType.ITEM_STARTED,
        ProgressEventType.ITEM_PROGRESS_UPDATED,
        ProgressEventType.ITEM_COMPLETED,
    ]
    values = [
        (e.previous_value, e.new_value)
        for e in db_session.query(ProgressEvent).order_by(ProgressEvent.created_at, ProgressEvent.id)
    ]
    assert values == [
        ("not_started:0", "in_progress:0"),
        ("in_progress:0", "in_progress:40"),
        ("in_progress:40", "completed:100"),
    ]


def test_percentage_with_non_in_progress_status_is_rejected(db_session):
    user, _, roadmap, items = _setup(db_session)
    with pytest.raises(InvalidProgressInputError):
        _update(db_session, user, roadmap, items["python"], S.COMPLETED, 50)


def test_in_progress_at_100_is_rejected(db_session):
    user, _, roadmap, items = _setup(db_session)
    with pytest.raises(InvalidProgressInputError):
        _update(db_session, user, roadmap, items["python"], S.IN_PROGRESS, 100)


@pytest.mark.parametrize(
    "path",
    [
        [S.COMPLETED, S.NOT_STARTED],
        [S.COMPLETED, S.BLOCKED],
        [S.COMPLETED, S.SKIPPED],
        [S.COMPLETED, S.COMPLETED],
        [S.BLOCKED, S.COMPLETED],
        [S.SKIPPED, S.COMPLETED],
        [S.IN_PROGRESS, S.IN_PROGRESS],  # same state without a percentage
    ],
)
def test_invalid_transitions_are_rejected(db_session, path):
    user, _, roadmap, items = _setup(db_session)
    item = items["python"]
    with pytest.raises(InvalidTransitionError):
        for status in path:
            _update(db_session, user, roadmap, item, status)


def test_same_state_not_started_is_rejected(db_session):
    user, _, roadmap, items = _setup(db_session)
    with pytest.raises(InvalidTransitionError):
        _update(db_session, user, roadmap, items["python"], S.NOT_STARTED)


def test_blocked_keeps_partial_progress_and_can_resume(db_session):
    user, _, roadmap, items = _setup(db_session)
    py = items["python"]
    _update(db_session, user, roadmap, py, S.IN_PROGRESS, 30)
    blocked = _update(db_session, user, roadmap, py, S.BLOCKED)
    assert blocked.item.status == S.BLOCKED and blocked.item.completion_percentage == 30
    assert blocked.summary.blocked == 1
    resumed = _update(db_session, user, roadmap, py, S.IN_PROGRESS)
    assert resumed.item.completion_percentage == 30


def test_reopen_completed_item_restarts_at_zero_and_reactivates_roadmap(db_session):
    user, _, roadmap, items = _setup(db_session)
    for slug in ("python", "machine-learning", "deep-learning"):
        done = _update(db_session, user, roadmap, items[slug], S.COMPLETED)
    assert done.roadmap_status == RoadmapStatus.COMPLETED
    reopened = _update(db_session, user, roadmap, items["deep-learning"], S.IN_PROGRESS)
    assert reopened.item.completion_percentage == 0 and reopened.roadmap_status == RoadmapStatus.ACTIVE
    assert reopened.item.completed_at is None


def test_skipped_counts_as_resolved_for_roadmap_completion(db_session):
    user, _, roadmap, items = _setup(db_session)
    _update(db_session, user, roadmap, items["python"], S.COMPLETED)
    _update(db_session, user, roadmap, items["machine-learning"], S.SKIPPED)
    last = _update(db_session, user, roadmap, items["deep-learning"], S.COMPLETED)
    assert last.roadmap_status == RoadmapStatus.COMPLETED
    assert last.summary.skipped == 1 and last.summary.percent_by_items == 100.0


def test_prerequisite_warning_but_not_blocked(db_session):
    user, _, roadmap, items = _setup(db_session)
    response = _update(db_session, user, roadmap, items["deep-learning"], S.IN_PROGRESS)
    assert response.item.status == S.IN_PROGRESS
    assert any("Machine Learning" in w for w in response.warnings)
    _update(db_session, user, roadmap, items["machine-learning"], S.COMPLETED)
    assert not any(
        "Machine Learning" in w
        for w in _update(db_session, user, roadmap, items["deep-learning"], S.IN_PROGRESS, 10).warnings
    )


def test_summary_percentages(db_session):
    user, _, roadmap, items = _setup(db_session)  # python 480, ml 480 (both foundations), dl 1380
    _update(db_session, user, roadmap, items["python"], S.COMPLETED)
    resp = _update(db_session, user, roadmap, items["machine-learning"], S.IN_PROGRESS, 50)
    assert resp.summary.total_skills == 3 and resp.summary.completed == 1 and resp.summary.in_progress == 1
    assert resp.summary.percent_by_items == pytest.approx(33.3, abs=0.1)
    expected = 100 * (480 + 480 * 0.5) / (480 + 480 + 1380)
    assert resp.summary.percent_by_effort == pytest.approx(expected, abs=0.1)


def test_completing_item_never_changes_user_skill(db_session):
    user, skills, roadmap, items = _setup(db_session)
    _own(db_session, user, skills["docker"], SkillLevel.BEGINNER)
    before = {(u.skill_id, u.current_level, u.confidence) for u in db_session.query(UserSkill)}
    for slug in ("python", "machine-learning", "deep-learning"):
        _update(db_session, user, roadmap, items[slug], S.COMPLETED)
    after = {(u.skill_id, u.current_level, u.confidence) for u in db_session.query(UserSkill)}
    assert before == after


def test_other_users_roadmap_is_404_and_unchanged(db_session):
    user, _, roadmap, items = _setup(db_session)
    intruder = User(email="intruder@example.com", password_hash="h")
    db_session.add(intruder)
    db_session.commit()
    with pytest.raises(RoadmapNotFoundError):
        _update(db_session, intruder, roadmap, items["python"], S.COMPLETED)
    with pytest.raises(RoadmapNotFoundError):
        ProgressService(db_session).get_progress(roadmap.id, intruder.id)
    assert db_session.query(RoadmapItem).filter_by(id=items["python"].id).one().status == S.NOT_STARTED
    assert db_session.query(ProgressEvent).count() == 0


def test_unknown_roadmap_and_unknown_item(db_session):
    user, _, roadmap, items = _setup(db_session)
    req = ProgressUpdateRequest(user_id=user.id, status=S.IN_PROGRESS)
    with pytest.raises(RoadmapNotFoundError):
        ProgressService(db_session).update_item("nope", items["python"].id, req)
    with pytest.raises(RoadmapItemNotFoundError):
        ProgressService(db_session).update_item(roadmap.id, "nope", req)


def test_item_from_another_roadmap_is_not_found(db_session):
    user, skills, roadmap, items = _setup(db_session)
    second = RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=2))
    # first roadmap is now archived; its item id must not be usable via the new roadmap
    with pytest.raises(RoadmapItemNotFoundError):
        ProgressService(db_session).update_item(
            second.id, items["python"].id, ProgressUpdateRequest(user_id=user.id, status=S.IN_PROGRESS)
        )


def test_archived_roadmap_rejects_updates(db_session):
    user, _, roadmap, items = _setup(db_session)
    RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=2))  # archives first
    with pytest.raises(RoadmapArchivedError):
        _update(db_session, user, roadmap, items["python"], S.IN_PROGRESS)


def test_progress_persists_after_reload(db_session):
    user, _, roadmap, items = _setup(db_session)
    _update(db_session, user, roadmap, items["python"], S.IN_PROGRESS, 25)
    db_session.expire_all()
    reloaded = db_session.query(RoadmapItem).filter_by(id=items["python"].id).one()
    assert reloaded.status == S.IN_PROGRESS and reloaded.completion_percentage == 25
    progress = ProgressService(db_session).get_progress(roadmap.id, user.id)
    py = next(i for i in progress.items if i.skill_slug == "python")
    assert py.completion_percentage == 25 and py.started_at is not None
    assert progress.recent_events[0].event_type == "item_started"


def test_get_progress_lists_skill_items_only_newest_event_first(db_session):
    user, _, roadmap, items = _setup(db_session)
    _update(db_session, user, roadmap, items["python"], S.IN_PROGRESS)
    _update(db_session, user, roadmap, items["python"], S.COMPLETED)
    progress = ProgressService(db_session).get_progress(roadmap.id, user.id)
    assert len(progress.items) == 3 and progress.replan_count == 0
    assert [e.event_type for e in progress.recent_events] == ["item_completed", "item_started"]
    assert db_session.query(Roadmap).filter_by(id=roadmap.id).one().status == RoadmapStatus.ACTIVE
