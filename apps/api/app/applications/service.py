"""Application tracking: create/link, list, detail, validated status changes, notes.
Every mutation appends an ApplicationEvent in the same transaction; any failure rolls back."""

import logging
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.applications.errors import (
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationInputError,
    ReferenceNotFoundError,
)
from app.applications.readiness import compute_readiness
from app.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationListResponse,
    ApplicationOut,
    NoteRequest,
    ReadinessResponse,
    StatusUpdateRequest,
)
from app.applications.transitions import SCHEDULABLE, check_transition
from app.models.application import ApplicationEvent, JobApplication
from app.models.enums import ApplicationEventType, ApplicationStatus
from app.models.job_description import JobDescription
from app.models.target_role import TargetRole
from app.models.user import User

logger = logging.getLogger("pathforge.applications")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _out(app: JobApplication) -> ApplicationOut:
    return ApplicationOut(
        id=app.id,
        job_description_id=app.job_description_id,
        target_role_id=app.target_role_id,
        company=app.company,
        job_title=app.job_title,
        status=app.status,
        applied_on=app.applied_on,
        scheduled_at=_aware(app.scheduled_at) if app.scheduled_at else None,
        notes=app.notes,
        created_at=_aware(app.created_at),
        updated_at=_aware(app.updated_at),
    )


class ApplicationService:
    def __init__(self, db: Session):
        self._db = db

    def _owned(self, application_id: str, user_id: str) -> JobApplication:
        app = self._db.query(JobApplication).filter_by(id=application_id, user_id=user_id).one_or_none()
        if app is None:
            raise ApplicationNotFoundError()
        return app

    def _event(self, app: JobApplication, event_type, *, from_status=None, to_status=None, note=None) -> None:
        self._db.add(
            ApplicationEvent(
                application_id=app.id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                note=note,
            )
        )

    def create(self, request: ApplicationCreateRequest) -> ApplicationDetail:
        if self._db.get(User, request.user_id) is None:
            raise ReferenceNotFoundError("User")
        jd = None
        if request.job_description_id is not None:
            jd = (
                self._db.query(JobDescription)
                .filter_by(id=request.job_description_id, user_id=request.user_id)
                .one_or_none()
            )
            if jd is None:
                raise ReferenceNotFoundError("Job description")
        if request.target_role_id is not None and self._db.get(TargetRole, request.target_role_id) is None:
            raise ReferenceNotFoundError("Target role")
        job_title = request.job_title or (jd.title if jd else None)
        if not job_title:
            raise InvalidApplicationInputError("job_title is required when no job description (with a title) is linked")
        if jd is not None:
            if self._db.query(JobApplication).filter_by(user_id=request.user_id, job_description_id=jd.id).first():
                raise DuplicateApplicationError()

        app = JobApplication(
            user_id=request.user_id,
            job_description_id=jd.id if jd else None,
            target_role_id=request.target_role_id,
            company=request.company or (jd.company if jd else None),
            job_title=job_title,
            status=ApplicationStatus.INTERESTED,
            notes=request.notes,
        )
        try:
            self._db.add(app)
            self._db.flush()
            self._event(app, ApplicationEventType.CREATED, to_status=app.status, note=request.notes)
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateApplicationError() from exc
        logger.info("Application created: status=%s linked_jd=%s", app.status.value, jd is not None)
        return self._detail(app)

    def list(
        self,
        user_id: str,
        *,
        status: ApplicationStatus | None = None,
        target_role_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationListResponse:
        query = self._db.query(JobApplication).filter_by(user_id=user_id)
        if status is not None:
            query = query.filter(JobApplication.status == status)
        if target_role_id is not None:
            query = query.filter(JobApplication.target_role_id == target_role_id)
        total = query.count()
        rows = query.order_by(JobApplication.updated_at.desc(), JobApplication.id).offset(offset).limit(limit).all()
        return ApplicationListResponse(items=[_out(r) for r in rows], total=total, limit=limit, offset=offset)

    def get(self, application_id: str, user_id: str) -> ApplicationDetail:
        return self._detail(self._owned(application_id, user_id))

    def update_status(self, application_id: str, request: StatusUpdateRequest) -> ApplicationDetail:
        app = self._owned(application_id, request.user_id)
        new = request.status
        check_transition(app.status, new)
        if request.scheduled_at is not None and new not in SCHEDULABLE:
            raise InvalidApplicationInputError("scheduled_at is only valid with status 'assessment' or 'interview'")
        if request.applied_on is not None and new != ApplicationStatus.APPLIED:
            raise InvalidApplicationInputError("applied_on is only valid with status 'applied'")
        if request.applied_on is not None and request.applied_on > date.today():
            raise InvalidApplicationInputError("applied_on cannot be in the future")

        old = app.status
        try:
            app.status = new
            if new == ApplicationStatus.APPLIED:
                app.applied_on = request.applied_on or datetime.now(timezone.utc).date()
            app.scheduled_at = _aware(request.scheduled_at) if request.scheduled_at else None
            if request.note:
                app.notes = request.note
            self._event(app, ApplicationEventType.STATUS_CHANGED, from_status=old, to_status=new, note=request.note)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        logger.info("Application status: %s -> %s", old.value, new.value)
        return self._detail(app)

    def add_note(self, application_id: str, request: NoteRequest) -> ApplicationDetail:
        app = self._owned(application_id, request.user_id)
        try:
            app.notes = request.note
            self._event(app, ApplicationEventType.NOTE_ADDED, note=request.note)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        return self._detail(app)

    def readiness(self, application_id: str, user_id: str) -> ReadinessResponse:
        return compute_readiness(self._db, self._owned(application_id, user_id))

    def _detail(self, app: JobApplication) -> ApplicationDetail:
        self._db.refresh(app)
        events = [
            ApplicationEventOut(
                id=e.id,
                event_type=e.event_type,
                from_status=e.from_status,
                to_status=e.to_status,
                note=e.note,
                occurred_at=_aware(e.occurred_at),
            )
            for e in app.events
        ]
        return ApplicationDetail(**_out(app).model_dump(), events=events)
