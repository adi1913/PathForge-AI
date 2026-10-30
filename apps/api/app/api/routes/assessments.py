from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.assessments.errors import AssessmentError
from app.assessments.schemas import (
    AssessmentListItem,
    AssessmentOut,
    AttemptStartOut,
    AttemptStartRequest,
    EvidenceOut,
    GenerateRequest,
    SubmitOut,
    SubmitRequest,
)
from app.assessments.service import AssessmentService
from app.db.session import get_db

router = APIRouter()


def _fail(exc: AssessmentError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/assessments/generate", response_model=AssessmentOut)
async def generate_assessment(request: GenerateRequest, db: Session = Depends(get_db)) -> AssessmentOut:
    try:
        return await AssessmentService(db).generate(request)
    except AssessmentError as exc:
        raise _fail(exc) from exc


@router.get("/assessments", response_model=list[AssessmentListItem])
def list_assessments(user_id: str, skill: str | None = None, db: Session = Depends(get_db)) -> list[AssessmentListItem]:
    return AssessmentService(db).list_assessments(user_id, skill)


# Declared before /assessments/{assessment_id} so "evidence" is not read as an id.
@router.get("/assessments/evidence", response_model=list[EvidenceOut])
def list_assessment_evidence(
    user_id: str, skill: str | None = None, db: Session = Depends(get_db)
) -> list[EvidenceOut]:
    return AssessmentService(db).evidence(user_id, skill)


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def get_assessment(assessment_id: str, user_id: str, db: Session = Depends(get_db)) -> AssessmentOut:
    try:
        return AssessmentService(db).get(assessment_id, user_id)
    except AssessmentError as exc:
        raise _fail(exc) from exc


@router.post("/assessments/{assessment_id}/attempts", response_model=AttemptStartOut)
def start_attempt(assessment_id: str, request: AttemptStartRequest, db: Session = Depends(get_db)) -> AttemptStartOut:
    try:
        return AssessmentService(db).start_attempt(assessment_id, request)
    except AssessmentError as exc:
        raise _fail(exc) from exc


@router.post("/assessments/attempts/{attempt_id}/submit", response_model=SubmitOut)
def submit_attempt(attempt_id: str, request: SubmitRequest, db: Session = Depends(get_db)) -> SubmitOut:
    try:
        return AssessmentService(db).submit(attempt_id, request)
    except AssessmentError as exc:
        raise _fail(exc) from exc
