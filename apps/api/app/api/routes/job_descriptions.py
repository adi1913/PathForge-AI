import os

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.jobs.errors import JobDescriptionError
from app.jobs.service import JobDescriptionAnalyzerService
from app.schemas.job_description import JobDescriptionAnalyzeResponse
from app.security.deps import AuthUser, get_current_user

router = APIRouter()


def _sanitize_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    return os.path.basename(filename).replace("\x00", "") or None


@router.post("/job-descriptions/analyze", response_model=JobDescriptionAnalyzeResponse)
async def analyze_job_description(
    db: Session = Depends(get_db),
    file: UploadFile | None = None,
    text: str | None = Form(default=None),
    user_id: str | None = Form(default=None),
    target_role_id: str | None = Form(default=None),
    auth: AuthUser = Depends(get_current_user),
) -> JobDescriptionAnalyzeResponse:
    settings = get_settings()
    user_id = auth.bind(user_id)  # the authenticated user, never a caller-chosen one
    if file is None and not text:
        raise HTTPException(status_code=422, detail="Provide either a 'file' upload or a 'text' field")

    if file is not None:
        raw = await file.read()
        filename = _sanitize_filename(file.filename)
        mime_type = file.content_type
    else:
        raw = text.encode("utf-8")
        filename = None
        mime_type = "text/plain"
    if len(raw) > settings.JD_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Input exceeds the {settings.JD_MAX_UPLOAD_BYTES}-byte limit")

    service = JobDescriptionAnalyzerService(db, settings)
    try:
        analysis, extras = await service.analyze(
            raw, filename=filename, mime_type=mime_type, user_id=user_id, target_role_id=target_role_id
        )
    except JobDescriptionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return JobDescriptionAnalyzeResponse(
        job_description_id=extras.job_description_id,
        job_description=analysis,
        user_skill_summary=extras.user_skill_summary,
        matched_skills=extras.matched_skills,
        weak_skills=extras.weak_skills,
        missing_skills=extras.missing_skills,
        skill_gaps=extras.skill_gaps,
        overall_match_score=extras.overall_match_score,
        critical_gap_count=extras.critical_gap_count,
        high_gap_count=extras.high_gap_count,
        warnings=analysis.warnings,
    )
