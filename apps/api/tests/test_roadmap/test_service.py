import pytest

from app.models.enums import (
    Difficulty,
    ResourceType,
    RoadmapItemType,
    RoadmapStatus,
    SkillGapStatus,
    SkillLevel,
    SkillMatchStatus,
)
from app.models.learning_resource import LearningResource
from app.models.profile import Profile
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill_gap import SkillGap
from app.models.target_role import TargetRole
from app.roadmap.errors import NoOpenSkillGapsError, UserNotFoundError
from app.roadmap.schemas import RoadmapGenerateRequest
from app.roadmap.service import RoadmapService
from tests.test_roadmap.helpers import _gap, _own, _seed


def _generate(db, user, **kw):
    return RoadmapService(db).generate(RoadmapGenerateRequest(user_id=user.id, hours_per_day=kw.pop("hours", 2), **kw))


def _skill_items(resp):
    return [i for i in resp.items if i.item_type == RoadmapItemType.SKILL]


def test_foundations_added_and_ordered_before_dependents(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["deep-learning"], priority=80)
    resp = _generate(db_session, user)
    items = _skill_items(resp)
    assert [i.skill_slug for i in items] == ["python", "machine-learning", "deep-learning"]
    assert items[0].title.startswith("Foundation:") and items[1].title.startswith("Foundation:")
    assert not items[2].title.startswith("Foundation:")


def test_owned_prerequisites_are_skipped(db_session):
    user, s = _seed(db_session)
    _own(db_session, user, s["python"])
    _gap(db_session, user, s["machine-learning"], priority=60)
    items = _skill_items(_generate(db_session, user))
    assert [i.skill_slug for i in items] == ["machine-learning"]


def test_prerequisite_item_ids_link_to_prerequisite_items(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["deep-learning"], priority=80)
    items = _skill_items(_generate(db_session, user))
    by_slug = {i.skill_slug: i for i in items}
    assert by_slug["deep-learning"].prerequisite_item_ids == [by_slug["machine-learning"].id]
    assert by_slug["machine-learning"].prerequisite_item_ids == [by_slug["python"].id]
    assert by_slug["python"].prerequisite_item_ids == []


def test_independent_gaps_ordered_by_priority(db_session):
    user, s = _seed(db_session)
    _own(db_session, user, s["python"])
    _gap(db_session, user, s["docker"], priority=30)
    _gap(db_session, user, s["machine-learning"], priority=70)
    assert [i.skill_slug for i in _skill_items(_generate(db_session, user))] == ["machine-learning", "docker"]


def test_closed_deferred_and_matched_gaps_are_ignored(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=50, status=SkillGapStatus.CLOSED)
    _gap(db_session, user, s["python"], priority=50, status=SkillGapStatus.DEFERRED)
    _gap(db_session, user, s["machine-learning"], priority=0, match=SkillMatchStatus.MATCHED)
    with pytest.raises(NoOpenSkillGapsError):
        _generate(db_session, user)


def test_effort_and_week_scheduling(db_session):
    user, s = _seed(db_session)
    _own(db_session, user, s["python"])
    _gap(db_session, user, s["machine-learning"], priority=70, target=SkillLevel.ADVANCED)  # 480+900+1500
    _gap(db_session, user, s["docker"], priority=30, current=SkillLevel.BEGINNER, target=SkillLevel.INTERMEDIATE)  # 900
    resp = _generate(db_session, user, hours=2)  # weekly = 2*60*5 = 600
    ml, docker = _skill_items(resp)
    assert ml.estimated_minutes == 2880 and ml.week_number == 1
    assert docker.estimated_minutes == 900 and docker.week_number == 5  # starts at 2880 -> 2880//600+1
    assert resp.summary.total_estimated_minutes == 3780
    assert resp.summary.estimated_weeks == 7


def test_low_confidence_match_gets_evidence_floor(db_session):
    user, s = _seed(db_session)
    _gap(
        db_session,
        user,
        s["docker"],
        priority=10,
        current=SkillLevel.INTERMEDIATE,
        target=SkillLevel.INTERMEDIATE,
        match=SkillMatchStatus.WEAK,
    )
    assert _skill_items(_generate(db_session, user))[0].estimated_minutes == 120


def test_deadline_warning_when_plan_does_not_fit(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["deep-learning"], priority=80)
    resp = _generate(db_session, user, hours=1, duration_days=7)
    assert resp.summary.fits_deadline is False
    assert any("deadline" in w for w in resp.warnings)
    assert len(_skill_items(resp)) == 3  # nothing silently dropped


def test_deadline_met_has_no_warning(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=10, target=SkillLevel.BEGINNER)
    resp = _generate(db_session, user, hours=4, duration_days=30)
    assert resp.summary.fits_deadline is True and resp.warnings == []


def test_pace_falls_back_to_profile_then_default(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=10)
    resp = RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id))
    assert resp.summary.hours_per_day == 1.0 and any("assumed" in w for w in resp.warnings)

    db_session.add(Profile(user_id=user.id, available_hours_per_day=3.0, target_duration_days=60))
    db_session.commit()
    resp = RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id=user.id))
    assert resp.summary.hours_per_day == 3.0 and resp.summary.deadline_days == 60
    assert not any("assumed" in w for w in resp.warnings)


def test_resources_come_only_from_catalog_max_two_best_difficulty(db_session):
    user, s = _seed(db_session)
    _own(db_session, user, s["python"])
    for title, diff, minutes in [
        ("Intro", Difficulty.BEGINNER, 60),
        ("Mid long", Difficulty.INTERMEDIATE, 300),
        ("Mid short", Difficulty.INTERMEDIATE, 100),
        ("Adv", Difficulty.ADVANCED, 50),
    ]:
        db_session.add(
            LearningResource(
                title=title,
                resource_type=ResourceType.COURSE,
                skill_id=s["machine-learning"].id,
                difficulty=diff,
                estimated_minutes=minutes,
                provider="p",
                url="https://x.test",
            )
        )
    db_session.commit()
    _gap(db_session, user, s["machine-learning"], priority=50)  # target intermediate
    resp = _generate(db_session, user)
    resources = [i for i in resp.items if i.item_type == RoadmapItemType.LEARNING_RESOURCE]
    assert [r.title for r in resources] == ["Mid short", "Mid long"]
    skill_item = _skill_items(resp)[0]
    assert all(r.prerequisite_item_ids == [skill_item.id] for r in resources)
    # resources are within the skill's budget, not added to the total
    assert resp.summary.total_estimated_minutes == skill_item.estimated_minutes


def test_no_resources_when_catalog_empty(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=10)
    assert all(i.item_type == RoadmapItemType.SKILL for i in _generate(db_session, user).items)


def test_order_index_unique_and_sequential(db_session):
    user, s = _seed(db_session)
    db_session.add(
        LearningResource(
            title="R",
            resource_type=ResourceType.DOCUMENTATION,
            skill_id=s["python"].id,
            difficulty=Difficulty.BEGINNER,
            estimated_minutes=30,
        )
    )
    db_session.commit()
    _gap(db_session, user, s["deep-learning"], priority=80)
    resp = _generate(db_session, user)
    assert [i.order_index for i in resp.items] == list(range(1, len(resp.items) + 1))


def test_regeneration_archives_previous_roadmap(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=10)
    first = _generate(db_session, user)
    second = _generate(db_session, user)
    assert first.id != second.id
    statuses = {r.id: r.status for r in db_session.query(Roadmap).filter_by(user_id=user.id)}
    assert statuses[first.id] == RoadmapStatus.ARCHIVED and statuses[second.id] == RoadmapStatus.ACTIVE
    assert second.generated_by == "rules"


def test_same_input_gives_identical_plan(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["deep-learning"], priority=80)
    _gap(db_session, user, s["docker"], priority=40)

    def shape(resp):
        return [(i.skill_slug, i.title, i.estimated_minutes, i.week_number, i.order_index) for i in resp.items]

    assert shape(_generate(db_session, user)) == shape(_generate(db_session, user))


def test_job_description_filter_restricts_gaps(db_session):
    from app.models.job_description import JobDescription

    user, s = _seed(db_session)
    jd = JobDescription(user_id=user.id, raw_text="x")
    db_session.add(jd)
    db_session.commit()
    _gap(db_session, user, s["docker"], priority=10)
    db_session.query(SkillGap).update({SkillGap.source_job_description_id: jd.id})
    _gap(db_session, user, s["python"], priority=90)
    resp = _generate(db_session, user, job_description_id=jd.id)
    assert [i.skill_slug for i in _skill_items(resp)] == ["docker"]


def test_target_role_titles_and_unknown_role_warns(db_session):
    user, s = _seed(db_session)
    role = TargetRole(name="AI Engineer", slug="ai-engineer")
    db_session.add(role)
    db_session.commit()
    _gap(db_session, user, s["docker"], priority=10)
    assert _generate(db_session, user, target_role_id=role.id).title == "Roadmap to AI Engineer"
    resp = _generate(db_session, user, target_role_id="nope")
    assert any("target_role_id" in w for w in resp.warnings) and resp.target_role_id is None


def test_unknown_user_raises(db_session):
    with pytest.raises(UserNotFoundError):
        RoadmapService(db_session).generate(RoadmapGenerateRequest(user_id="ghost"))


def test_get_roundtrip_matches_generated_items(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["deep-learning"], priority=80)
    generated = _generate(db_session, user)
    fetched = RoadmapService(db_session).get(generated.id)
    assert [i.id for i in fetched.items] == [i.id for i in generated.items]
    assert fetched.summary.total_estimated_minutes == generated.summary.total_estimated_minutes
    assert fetched.summary.estimated_days is None  # pace is not stored
    assert RoadmapService(db_session).get("missing") is None


def test_items_persisted_in_db(db_session):
    user, s = _seed(db_session)
    _gap(db_session, user, s["docker"], priority=10)
    resp = _generate(db_session, user)
    assert db_session.query(RoadmapItem).filter_by(roadmap_id=resp.id).count() == len(resp.items)
