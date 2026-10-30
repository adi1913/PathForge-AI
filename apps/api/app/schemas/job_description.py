from pydantic import BaseModel

from app.jobs.schemas import JobDescriptionAnalysis, SkillGapResult, UserSkillSummary


class JobDescriptionAnalyzeResponse(BaseModel):
    job_description_id: str
    job_description: JobDescriptionAnalysis
    user_skill_summary: UserSkillSummary
    matched_skills: list[SkillGapResult]
    weak_skills: list[SkillGapResult]
    missing_skills: list[SkillGapResult]
    skill_gaps: list[SkillGapResult]
    overall_match_score: float | None
    critical_gap_count: int
    high_gap_count: int
    warnings: list[str]
