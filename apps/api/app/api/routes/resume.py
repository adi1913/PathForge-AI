import os

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.resume.errors import ResumeError
from app.resume.service import ResumeAnalyzerService
from app.schemas.resume import ResumeAnalyzeResponse
from app.security.deps import AuthUser, get_current_user

router = APIRouter()

_ALLOWED_MIME_TYPES = {"text/plain", "text/markdown", "application/pdf"}


def _sanitize_filename(filename: str | None) -> str | None:
    """Strips any directory component so a crafted filename (e.g.
    "../../etc/passwd") can never be used as anything but a display
    label — this service never writes the upload to a path derived from
    the filename in the first place, but sanitizing at the boundary is
    cheap insurance."""
    if not filename:
        return None
    return os.path.basename(filename).replace("\x00", "") or None


@router.post("/resume/analyze", response_model=ResumeAnalyzeResponse)
async def analyze_resume(
    db: Session = Depends(get_db),
    file: UploadFile | None = None,
    text: str | None = Form(default=None),
    user_id: str | None = Form(default=None),
    auth: AuthUser = Depends(get_current_user),
) -> ResumeAnalyzeResponse:
    settings = get_settings()
    user_id = auth.bind(user_id)  # the authenticated user, never a caller-chosen one

    if file is None and not text:
        raise HTTPException(status_code=422, detail="Provide either a 'file' upload or a 'text' field")

    if file is not None:
        raw = await file.read()
        if len(raw) > settings.RESUME_MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"File exceeds the {settings.RESUME_MAX_UPLOAD_BYTES}-byte limit"
            )
        filename = _sanitize_filename(file.filename)
        mime_type = file.content_type
    else:
        raw = text.encode("utf-8")
        if len(raw) > settings.RESUME_MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"Text exceeds the {settings.RESUME_MAX_UPLOAD_BYTES}-byte limit"
            )
        filename = None
        mime_type = "text/plain"

    service = ResumeAnalyzerService(db, settings)
    try:
        analysis, persistence = await service.analyze(raw, filename=filename, mime_type=mime_type, user_id=user_id)
    except ResumeError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return ResumeAnalyzeResponse(
        status="completed",
        analysis=analysis,
        document_id=persistence.document_id,
        user_skills_created=persistence.user_skills_created,
        user_skills_updated=persistence.user_skills_updated,
    )
