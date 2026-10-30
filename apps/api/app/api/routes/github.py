from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repo_evidence.errors import RepoEvalError
from app.repo_evidence.schemas import (
    EvaluateRequest,
    EvaluationResponse,
    EvidenceListItem,
    RepositoryListItem,
)
from app.repo_evidence.service import RepositoryEvaluationService

router = APIRouter()


def _manager(request: Request):
    manager = getattr(request.app.state, "mcp_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="MCP client is not initialized")
    return manager


@router.post("/github/evaluate", response_model=EvaluationResponse)
async def evaluate_repository(
    payload: EvaluateRequest, request: Request, db: Session = Depends(get_db)
) -> EvaluationResponse:
    try:
        return await RepositoryEvaluationService(db, _manager(request)).evaluate(payload)
    except RepoEvalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/github/repositories", response_model=list[RepositoryListItem])
def list_repositories(user_id: str, request: Request, db: Session = Depends(get_db)) -> list[RepositoryListItem]:
    return RepositoryEvaluationService(db, _manager(request)).list_repositories(user_id)


@router.get("/github/evaluations/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(
    evaluation_id: str, user_id: str, request: Request, db: Session = Depends(get_db)
) -> EvaluationResponse:
    try:
        return RepositoryEvaluationService(db, _manager(request)).get_evaluation(evaluation_id, user_id)
    except RepoEvalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/github/evidence", response_model=list[EvidenceListItem])
def list_evidence(
    user_id: str, request: Request, skill: str | None = None, db: Session = Depends(get_db)
) -> list[EvidenceListItem]:
    return RepositoryEvaluationService(db, _manager(request)).list_evidence(user_id, skill)
