"""Read-only readiness summary for an application. Reuses the Phase 7 gap engine
(app.jobs.gap_engine) on the linked JD's stored requirements vs the user's *current*
UserSkill rows. Writes nothing; never changes proficiency."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.applications.schemas import ReadinessResponse, ReadinessSkill, RoadmapProgressRef
from app.jobs.gap_engine import (
    build_reasoning,
    classify_match,
    compute_overall_match_score,
    compute_priority_score,
    compute_severity,
)
from app.jobs.schemas import JobSkillRequirement
from app.models.application import JobApplication
from app.models.enums import EvidenceSource, GapSeverity, ImportanceLevel, RoadmapStatus, SkillMatchStatus
from app.models.job_description import JobDescription, JobDescriptionSkill
from app.models.roadmap import Roadmap
from app.models.skill import UserSkill
from app.models.skill_gap import SkillGap
from app.repo_evidence.queries import evidence_for_user
from app.repo_evidence.schemas import GithubEvidenceRef
from app.roadmap.progress import summarize

DISCLAIMER = (
    "Internal skill-match indicator computed from the job description's extracted requirements and your "
    "recorded skill levels. It is not a hiring probability and does not predict interview or offer outcomes."
)
_MEASURED_SOURCES = {
    EvidenceSource.ASSESSMENT,
    EvidenceSource.PROJECT,
    EvidenceSource.GITHUB,
    EvidenceSource.MENTOR_EVALUATION,
}
_FACTORS = [
    "Required skills weigh 2x preferred skills; criticality weighs 4/3/2/1 (critical/high/medium/low).",
    "Matched = recorded level meets the expected level with confidence >= 0.4; weak = below level or low "
    "confidence (partial credit by level ratio); missing = no evidence (no credit).",
    "Skill levels come from your stored UserSkill rows (measured = assessment/project/GitHub/mentor evidence; "
    "estimated = resume text or manual entry).",
]


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _unavailable(app: JobApplication, reason: str) -> ReadinessResponse:
    return ReadinessResponse(
        application_id=app.id, status="unavailable", reason=reason, factors=_FACTORS, disclaimer=DISCLAIMER
    )


def compute_readiness(db: Session, app: JobApplication) -> ReadinessResponse:
    if app.job_description_id is None:
        return _unavailable(
            app,
            "No job description is linked to this application (or it was deleted), so no requirements are known.",
        )
    jd = db.get(JobDescription, app.job_description_id)
    rows = db.query(JobDescriptionSkill).filter_by(job_description_id=jd.id).all()
    if not rows:
        return _unavailable(app, "The job description has no extracted skills that match the skill catalog.")

    user_skills = {us.skill_id: us for us in db.query(UserSkill).filter_by(user_id=app.user_id).all()}
    results = []
    evaluated = []
    statuses = {}
    for row in sorted(rows, key=lambda r: r.skill.slug):
        requirement = JobSkillRequirement(
            raw_name=row.skill.name,
            normalized_skill_id=row.skill_id,
            normalized_skill_name=row.skill.name,
            requirement_type="required" if row.importance == ImportanceLevel.REQUIRED else "preferred",
            importance=row.criticality,
            expected_level=row.required_level,
            evidence_text=(row.evidence or "")[:500],
            confidence=row.confidence if row.confidence is not None else 0.5,
            reasoning=row.reasoning or "",
        )
        status, current, confidence = classify_match(requirement, user_skills.get(row.skill_id))
        statuses[row.skill_id] = status
        results.append((requirement, status, current, confidence, row))
    gap_ids = {sid for sid, st in statuses.items() if st != SkillMatchStatus.MATCHED}

    evidence_by_slug: dict[str, list[GithubEvidenceRef]] = {}
    for item in evidence_for_user(db, app.user_id, [row.skill_id for _, _, _, _, row in results]):
        evidence_by_slug.setdefault(item.skill_slug, []).append(
            GithubEvidenceRef(**item.model_dump(include=set(GithubEvidenceRef.model_fields)))
        )

    skills: list[ReadinessSkill] = []
    for requirement, status, current, confidence, row in results:
        user_skill = user_skills.get(row.skill_id)
        severity = compute_severity(status, requirement.importance, requirement.expected_level, current)
        prereq_gaps = sum(1 for p in row.skill.prerequisites if p.id in gap_ids)
        if status == SkillMatchStatus.MISSING:
            data_kind, source = "none", None
        else:
            data_kind = "measured" if user_skill.source in _MEASURED_SOURCES else "estimated"
            source = user_skill.source.value
        skills.append(
            ReadinessSkill(
                skill_name=row.skill.name,
                requirement_type=requirement.requirement_type,
                importance=requirement.importance.value,
                expected_level=requirement.expected_level,
                current_level=current,
                match_status=status,
                severity=severity,
                priority_score=compute_priority_score(
                    requirement.requirement_type, requirement.importance, severity, prereq_gaps
                ),
                confidence=max(0.0, min(1.0, confidence)),
                data_kind=data_kind,
                evidence_source=source,
                reasoning=build_reasoning(requirement, status, current, severity),
                github_evidence=evidence_by_slug.get(row.skill.slug, []),
            )
        )
        evaluated.append((requirement, status, current))
    skills.sort(key=lambda s: (-s.priority_score, s.skill_name))

    unmatched = list((jd.analysis_metadata or {}).get("unmatched_skills", []))
    # Last time this JD's analysis touched the DB: the JD row itself or a gap it produced.
    gap_times = [_utc(g.updated_at) for g in db.query(SkillGap).filter_by(source_job_description_id=jd.id)]
    jd_at = max([_utc(jd.updated_at), *gap_times])
    skills_at = max((_utc(us.updated_at) for us in user_skills.values()), default=None)
    stale = skills_at is not None and jd_at is not None and skills_at > jd_at

    warnings: list[str] = []
    if not user_skills:
        warnings.append("No skills are recorded for this user, so every requirement counts as missing.")
    if any(s.data_kind == "estimated" for s in skills):
        warnings.append("Some skill levels are estimates from resume/manual entry rather than measured evidence.")
    unproven = sorted(s.skill_name for s in skills if s.github_evidence and s.match_status != SkillMatchStatus.MATCHED)
    if unproven:
        warnings.append(
            "Repository evidence exists for "
            + ", ".join(unproven)
            + " but your recorded level is missing or below the requirement. Repository evidence is an "
            "observation, not proficiency, and does not change the score."
        )
    if unmatched:
        warnings.append(f"{len(unmatched)} requirement(s) are not in the skill catalog and are not scored.")
    if stale:
        warnings.append(
            "Your skills changed after this job description was analyzed; stored skill gaps and any roadmap built "
            "from them may be outdated. Re-run the job description analysis to refresh them."
        )

    roadmap_row = (
        db.query(Roadmap)
        .filter_by(user_id=app.user_id, status=RoadmapStatus.ACTIVE)
        .order_by(Roadmap.created_at.desc(), Roadmap.id)
        .first()
    )
    roadmap = (
        RoadmapProgressRef(
            roadmap_id=roadmap_row.id,
            title=roadmap_row.title,
            percent_by_effort=summarize(roadmap_row).percent_by_effort,
        )
        if roadmap_row
        else None
    )
    return ReadinessResponse(
        application_id=app.id,
        status="computed",
        overall_match_score=compute_overall_match_score(evaluated),
        matched_count=sum(1 for s in skills if s.match_status == SkillMatchStatus.MATCHED),
        weak_count=sum(1 for s in skills if s.match_status == SkillMatchStatus.WEAK),
        missing_count=sum(1 for s in skills if s.match_status == SkillMatchStatus.MISSING),
        critical_gap_count=sum(1 for s in skills if s.severity == GapSeverity.CRITICAL),
        high_gap_count=sum(1 for s in skills if s.severity == GapSeverity.HIGH),
        skills=skills,
        unmatched_requirements=unmatched,
        jd_analyzed_at=jd_at,
        skills_last_updated=skills_at,
        persisted_gaps_may_be_stale=stale,
        roadmap=roadmap,
        factors=_FACTORS,
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )
