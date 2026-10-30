"""Builds the mentor's view of the learner from stored state only. It deliberately never reads
Question.expected_answer / evaluation_rubric: the mentor can describe results, never the answer key."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.assessment import AssessmentEvidence
from app.models.enums import AssessmentOutcome, RoadmapItemStatus, RoadmapItemType, RoadmapStatus
from app.models.profile import Profile
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import Skill, UserSkill
from app.roadmap.progress import RESOLVED, summarize
from app.roadmap.schemas import ProgressSummary

_RECENT_ASSESSMENTS = 5


@dataclass
class SkillState:
    slug: str
    name: str
    level: str
    confidence: float | None
    source: str


@dataclass
class AssessmentState:
    skill_slug: str
    skill_name: str
    score_percent: float
    outcome: str
    attempt_number: int


@dataclass
class MentorContext:
    target_role: str | None = None
    skills: list[SkillState] = field(default_factory=list)
    roadmap_id: str | None = None
    roadmap_title: str | None = None
    progress: ProgressSummary | None = None
    completed_titles: list[str] = field(default_factory=list)
    in_progress_titles: list[str] = field(default_factory=list)
    next_item: RoadmapItem | None = None
    assessments: list[AssessmentState] = field(default_factory=list)
    weak_skills: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Counts/ids only — safe to store in message metadata."""
        return {
            "skills": len(self.skills),
            "roadmap_id": self.roadmap_id,
            "completed_items": len(self.completed_titles),
            "assessments": len(self.assessments),
            "weak_skills": list(self.weak_skills),
        }


def build_context(db: Session, user_id: str) -> MentorContext:
    ctx = MentorContext()
    profile = db.query(Profile).filter_by(user_id=user_id).one_or_none()
    roadmap = (
        db.query(Roadmap)
        .filter_by(user_id=user_id, status=RoadmapStatus.ACTIVE)
        .order_by(Roadmap.created_at.desc(), Roadmap.id)
        .first()
    )
    ctx.target_role = (profile.target_role if profile and profile.target_role else None) or (
        roadmap.target_role.name if roadmap and roadmap.target_role else None
    )
    if ctx.target_role is None:
        ctx.missing.append("No target role is recorded on your profile or roadmap.")

    rows = (
        db.query(UserSkill, Skill)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .filter(UserSkill.user_id == user_id)
        .all()
    )
    ctx.skills = sorted(
        (SkillState(s.slug, s.name, us.current_level.value, us.confidence, us.source.value) for us, s in rows),
        key=lambda s: s.slug,
    )
    if not ctx.skills:
        ctx.missing.append("No skills are recorded for you yet (analyze a resume first).")

    if roadmap is None:
        ctx.missing.append("You have no active roadmap, so topic and progress answers are limited.")
    else:
        ctx.roadmap_id, ctx.roadmap_title = roadmap.id, roadmap.title
        ctx.progress = summarize(roadmap)
        skill_items = [i for i in roadmap.items if i.item_type == RoadmapItemType.SKILL]
        ctx.completed_titles = [i.title for i in skill_items if i.status == RoadmapItemStatus.COMPLETED]
        ctx.in_progress_titles = [i.title for i in skill_items if i.status == RoadmapItemStatus.IN_PROGRESS]
        pending = [i for i in skill_items if i.status not in RESOLVED]
        in_progress = [i for i in pending if i.status == RoadmapItemStatus.IN_PROGRESS]
        ctx.next_item = (in_progress or pending or [None])[0] if (in_progress or pending) else None

    evidence = (
        db.query(AssessmentEvidence)
        .filter_by(user_id=user_id)
        .order_by(AssessmentEvidence.created_at.desc(), AssessmentEvidence.id)
        .all()
    )
    skill_by_id = (
        {s.id: s for s in db.query(Skill).filter(Skill.id.in_({e.skill_id for e in evidence}))} if evidence else {}
    )
    ctx.assessments = [
        AssessmentState(
            skill_by_id[e.skill_id].slug,
            skill_by_id[e.skill_id].name,
            e.score_percent,
            e.outcome.value,
            e.attempt_number,
        )
        for e in evidence[:_RECENT_ASSESSMENTS]
    ]
    latest_by_skill: dict[str, AssessmentEvidence] = {}
    for e in evidence:  # newest first, so setdefault keeps the latest per skill
        latest_by_skill.setdefault(e.skill_id, e)
    ctx.weak_skills = sorted(
        skill_by_id[sid].name for sid, e in latest_by_skill.items() if e.outcome == AssessmentOutcome.WEAK
    )
    if not evidence:
        ctx.missing.append("You have no assessment history yet.")
    return ctx
