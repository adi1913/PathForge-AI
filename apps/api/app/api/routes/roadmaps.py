from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.roadmap import Roadmap
from app.roadmap.errors import RoadmapError
from app.roadmap.progress import ProgressService
from app.roadmap.replan import ReplanService
from app.roadmap.schemas import (
    ProgressUpdateRequest,
    ProgressUpdateResponse,
    ReplanRequest,
    ReplanResponse,
    RoadmapGenerateRequest,
    RoadmapListItem,
    RoadmapProgressResponse,
    RoadmapResponse,
)
from app.roadmap.service import RoadmapService
from app.security.deps import AuthUser, get_current_user

router = APIRouter()


@router.post("/roadmaps/generate", response_model=RoadmapResponse)
def generate_roadmap(request: RoadmapGenerateRequest, db: Session = Depends(get_db)) -> RoadmapResponse:
    try:
        return RoadmapService(db).generate(request)
    except RoadmapError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapResponse)
def get_roadmap(
    roadmap_id: str, db: Session = Depends(get_db), auth: AuthUser = Depends(get_current_user)
) -> RoadmapResponse:
    roadmap = RoadmapService(db).get(roadmap_id)
    # Foreign and unknown ids are indistinguishable (404), so existence is never leaked.
    if roadmap is None or (auth.authenticated and roadmap.user_id != auth.id):
        raise HTTPException(status_code=404, detail="Roadmap not found")
    return roadmap


@router.get("/roadmaps", response_model=list[RoadmapListItem])
def list_roadmaps(user_id: str, db: Session = Depends(get_db)) -> list[RoadmapListItem]:
    rows = db.query(Roadmap).filter_by(user_id=user_id).order_by(Roadmap.created_at.desc(), Roadmap.id).all()
    return [
        RoadmapListItem(
            id=r.id,
            title=r.title,
            status=r.status,
            generated_by=r.generated_by,
            duration_days=r.duration_days,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.patch("/roadmaps/{roadmap_id}/items/{item_id}/progress", response_model=ProgressUpdateResponse)
def update_item_progress(
    roadmap_id: str, item_id: str, request: ProgressUpdateRequest, db: Session = Depends(get_db)
) -> ProgressUpdateResponse:
    try:
        return ProgressService(db).update_item(roadmap_id, item_id, request)
    except RoadmapError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/roadmaps/{roadmap_id}/progress", response_model=RoadmapProgressResponse)
def get_roadmap_progress(roadmap_id: str, user_id: str, db: Session = Depends(get_db)) -> RoadmapProgressResponse:
    try:
        return ProgressService(db).get_progress(roadmap_id, user_id)
    except RoadmapError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/roadmaps/{roadmap_id}/replan", response_model=ReplanResponse)
def replan_roadmap(roadmap_id: str, request: ReplanRequest, db: Session = Depends(get_db)) -> ReplanResponse:
    try:
        return ReplanService(db).replan(roadmap_id, request)
    except RoadmapError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
