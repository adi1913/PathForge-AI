from datetime import date, datetime, timedelta, timezone

import pytest

from app.applications.errors import (
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationInputError,
    InvalidStatusTransitionError,
    ReferenceNotFoundError,
)
from app.applications.schemas import ApplicationCreateRequest, NoteRequest, StatusUpdateRequest
from app.applications.service import ApplicationService
from app.models.application import ApplicationEvent, JobApplication
from app.models.enums import ApplicationEventType
from app.models.enums import ApplicationStatus as S
from app.models.target_role import TargetRole
from tests.test_applications.helpers import make_jd, seed


def _create(svc, user, **kw):
    return svc.create(ApplicationCreateRequest(user_id=user.id, **kw))


def _status(svc, app, user, status, **kw):
    return svc.update_status(app.id, StatusUpdateRequest(user_id=user.id, status=status, **kw))


def test_create_from_jd_defaults_title_company_without_copying_skills(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    app = _create(ApplicationService(db_session), user, job_description_id=jd.id)
    assert (app.job_title, app.company, app.status) == ("ML Engineer", "Globex", S.INTERESTED)
    assert app.job_description_id == jd.id
    assert [e.event_type for e in app.events] == [ApplicationEventType.CREATED]


def test_explicit_fields_override_jd_defaults(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    app = _create(ApplicationService(db_session), user, job_description_id=jd.id, job_title="Staff ML", company="X")
    assert (app.job_title, app.company) == ("Staff ML", "X")


def test_manual_application_needs_title_and_can_repeat(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    with pytest.raises(InvalidApplicationInputError):
        _create(svc, user, company="Acme")
    _create(svc, user, job_title="Data Analyst")
    _create(svc, user, job_title="Data Analyst")
    assert svc.list(user.id).total == 2


def test_missing_and_foreign_references(db_session):
    user, other, skills = seed(db_session)
    svc = ApplicationService(db_session)
    with pytest.raises(ReferenceNotFoundError):
        _create(svc, user, job_description_id="nope")
    foreign_jd = make_jd(db_session, other, skills)
    with pytest.raises(ReferenceNotFoundError):
        _create(svc, user, job_description_id=foreign_jd.id)
    with pytest.raises(ReferenceNotFoundError):
        _create(svc, user, job_title="x", target_role_id="nope")
    with pytest.raises(ReferenceNotFoundError):
        svc.create(ApplicationCreateRequest(user_id="ghost", job_title="x"))


def test_duplicate_jd_link_rejected(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    svc = ApplicationService(db_session)
    _create(svc, user, job_description_id=jd.id)
    with pytest.raises(DuplicateApplicationError):
        _create(svc, user, job_description_id=jd.id)
    assert db_session.query(JobApplication).count() == 1


def test_status_flow_records_events_and_dates(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_title="AI Eng")
    app = _status(svc, app, user, S.PREPARING)
    app = _status(svc, app, user, S.APPLIED, applied_on=date.today() - timedelta(days=2), note="via referral")
    assert app.applied_on == date.today() - timedelta(days=2)
    when = datetime.now(timezone.utc) + timedelta(days=3)
    app = _status(svc, app, user, S.INTERVIEW, scheduled_at=when)
    assert app.scheduled_at is not None
    app = _status(svc, app, user, S.OFFER)
    assert app.scheduled_at is None  # cleared on non-schedulable status
    assert [
        (e.from_status, e.to_status) for e in app.events if e.event_type == ApplicationEventType.STATUS_CHANGED
    ] == [
        (S.INTERESTED, S.PREPARING),
        (S.PREPARING, S.APPLIED),
        (S.APPLIED, S.INTERVIEW),
        (S.INTERVIEW, S.OFFER),
    ]
    assert app.notes == "via referral"


def test_applied_without_date_defaults_to_today(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    created = _create(svc, user, job_title="x")
    app = _status(svc, created, user, S.APPLIED)
    assert app.applied_on == datetime.now(timezone.utc).date()


def test_invalid_updates_leave_no_trace(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_title="x")
    events_before = db_session.query(ApplicationEvent).count()
    with pytest.raises(InvalidStatusTransitionError):
        _status(svc, app, user, S.OFFER)
    with pytest.raises(InvalidStatusTransitionError):
        _status(svc, app, user, S.INTERESTED)  # same state
    with pytest.raises(InvalidApplicationInputError):
        _status(svc, app, user, S.PREPARING, scheduled_at=datetime.now(timezone.utc))
    with pytest.raises(InvalidApplicationInputError):
        _status(svc, app, user, S.PREPARING, applied_on=date.today())
    with pytest.raises(InvalidApplicationInputError):
        _status(svc, app, user, S.APPLIED, applied_on=date.today() + timedelta(days=1))
    assert db_session.query(ApplicationEvent).count() == events_before
    assert db_session.get(JobApplication, app.id).status == S.INTERESTED


def test_terminal_status_is_final_and_repeated_updates_append(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_title="x")
    app = _status(svc, app, user, S.PREPARING)
    app = _status(svc, app, user, S.INTERESTED)
    app = _status(svc, app, user, S.PREPARING)  # bouncing is legal and each is recorded
    assert len(app.events) == 4
    app = _status(svc, app, user, S.WITHDRAWN)
    with pytest.raises(InvalidStatusTransitionError):
        _status(svc, app, user, S.APPLIED)


def test_notes_append_events(db_session):
    user, _, _ = seed(db_session)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_title="x")
    app = svc.add_note(app.id, NoteRequest(user_id=user.id, note="  recruiter called  "))
    assert app.notes == "recruiter called"
    assert app.events[-1].event_type == ApplicationEventType.NOTE_ADDED


def test_cross_user_and_unknown_are_not_found(db_session):
    user, other, _ = seed(db_session)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_title="x")
    for call in (
        lambda: svc.get(app.id, other.id),
        lambda: svc.get("missing", user.id),
        lambda: svc.update_status(app.id, StatusUpdateRequest(user_id=other.id, status=S.APPLIED)),
        lambda: svc.add_note(app.id, NoteRequest(user_id=other.id, note="hi")),
        lambda: svc.readiness(app.id, other.id),
    ):
        with pytest.raises(ApplicationNotFoundError):
            call()
    assert svc.list(other.id).total == 0


def test_list_filter_pagination_and_persistence(db_session):
    user, _, _ = seed(db_session)
    role = TargetRole(name="AI Engineer", slug="ai-engineer")
    db_session.add(role)
    db_session.commit()
    svc = ApplicationService(db_session)
    made = [_create(svc, user, job_title=f"job{i}", target_role_id=role.id if i < 3 else None) for i in range(5)]
    _status(svc, made[0], user, S.APPLIED)
    assert svc.list(user.id, status=S.APPLIED).total == 1
    assert svc.list(user.id, target_role_id=role.id).total == 3
    page1 = svc.list(user.id, limit=2, offset=0)
    page2 = svc.list(user.id, limit=2, offset=2)
    page3 = svc.list(user.id, limit=2, offset=4)
    ids = [i.id for p in (page1, page2, page3) for i in p.items]
    assert len(ids) == 5 == len(set(ids)) and page1.total == 5
    db_session.expire_all()  # reload from the DB
    assert svc.get(made[0].id, user.id).status == S.APPLIED


def test_deleting_jd_keeps_application_and_history(db_session):
    user, _, skills = seed(db_session)
    jd = make_jd(db_session, user, skills)
    svc = ApplicationService(db_session)
    app = _create(svc, user, job_description_id=jd.id)
    db_session.delete(jd)
    db_session.commit()
    kept = svc.get(app.id, user.id)
    assert kept.job_description_id is None and len(kept.events) == 1


def test_deleting_user_cascades(db_session):
    user, _, _ = seed(db_session)
    _create(ApplicationService(db_session), user, job_title="x")
    db_session.delete(user)
    db_session.commit()
    assert db_session.query(JobApplication).count() == 0
    assert db_session.query(ApplicationEvent).count() == 0
