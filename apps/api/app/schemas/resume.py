from pydantic import BaseModel

from app.resume.schemas import ResumeAnalysis


class ResumeAnalyzeResponse(BaseModel):
    status: str
    analysis: ResumeAnalysis
    document_id: str
    user_skills_created: int
    user_skills_updated: int
