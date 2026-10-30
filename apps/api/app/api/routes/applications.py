from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.applications.errors import ApplicationError
from app.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationDetail,
    ApplicationListResponse,
    NoteRequest,
    ReadinessResponse,
    StatusUpdateRequest,
)
from app.applications.service import ApplicationService
from app.db.session import get_db
from app.models.enums import ApplicationStatus

router = APIRouter()


def _raise(exc: ApplicationError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/applications", response_model=ApplicationDetail, status_code=201)
def create_application(request: ApplicationCreateRequest, db: Session = Depends(get_db)) -> ApplicationDetail:
    try:
        return ApplicationService(db).create(request)
    except ApplicationError as exc:
        _raise(exc)


@router.get("/applications", response_model=ApplicationListResponse)
def list_applications(
    user_id: str,
    status: ApplicationStatus | None = None,
    target_role_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ApplicationListResponse:
    return ApplicationService(db).list(
        user_id, status=status, target_role_id=target_role_id, limit=limit, offset=offset
    )


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def get_application(application_id: str, user_id: str, db: Session = Depends(get_db)) -> ApplicationDetail:
    try:
        return ApplicationService(db).get(application_id, user_id)
    except ApplicationError as exc:
        _raise(exc)


@router.patch("/applications/{application_id}/status", response_model=ApplicationDetail)
def update_application_status(
    application_id: str, request: StatusUpdateRequest, db: Session = Depends(get_db)
) -> ApplicationDetail:
    try:
        return ApplicationService(db).update_status(application_id, request)
    except ApplicationError as exc:
        _raise(exc)


@router.post("/applications/{application_id}/notes", response_model=ApplicationDetail)
def add_application_note(application_id: str, request: NoteRequest, db: Session = Depends(get_db)) -> ApplicationDetail:
    try:
        return ApplicationService(db).add_note(application_id, request)
    except ApplicationError as exc:
        _raise(exc)


@router.get("/applications/{application_id}/readiness", response_model=ReadinessResponse)
def get_application_readiness(application_id: str, user_id: str, db: Session = Depends(get_db)) -> ReadinessResponse:
    try:
        return ApplicationService(db).readiness(application_id, user_id)
    except ApplicationError as exc:
        _raise(exc)
