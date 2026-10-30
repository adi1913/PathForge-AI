"""Roadmap generation: SkillGap rows -> foundations -> ordering ->
effort/schedule -> resources -> persisted Roadmap/RoadmapItem rows.
All decisions are deterministic (see app.roadmap.planner); no LLM."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import (
    Difficulty,
    RoadmapItemStatus,
    RoadmapItemType,
    RoadmapStatus,
    SkillGapStatus,
    SkillLevel,
    SkillMatchStatus,
)
from app.models.learning_resource import LearningResource
from app.models.profile import Profile
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import UserSkill
from app.models.skill_gap import SkillGap
from app.models.target_role import TargetRole
from app.models.user import User
from app.roadmap.errors import NoOpenSkillGapsError, UserNotFoundError
from app.roadmap.planner import PlannedItem, PlanNode, days_needed, has_shortfall, order_nodes, schedule
from app.roadmap.schemas import RoadmapGenerateRequest, RoadmapItemOut, RoadmapResponse, RoadmapSummary

logger = logging.getLogger("pathforge.roadmap")

_DEFAULT_HOURS_PER_DAY = 1.0
_MAX_RESOURCES_PER_SKILL = 2
_OPEN_STATUSES = (SkillGapStatus.OPEN, SkillGapStatus.IN_PROGRESS)
_DIFFICULTY_RANK = {Difficulty.BEGINNER: 1, Difficulty.INTERMEDIATE: 2, Difficulty.ADVANCED: 3}


def resolve_pace(
    db: Session, user_id: str, hours_per_day: float | None, duration_days: int | None, warnings: list[str]
) -> tuple[float, int | None]:
    """Request value, else the user's Profile, else (hours only) a 1h/day default with a warning."""
    profile = db.query(Profile).filter_by(user_id=user_id).one_or_none()
    hours = hours_per_day or (profile.available_hours_per_day if profile else None)
    if not hours:
        hours = _DEFAULT_HOURS_PER_DAY
        warnings.append(f"No hours per day supplied or on the profile; assumed {_DEFAULT_HOURS_PER_DAY:g}h/day.")
    deadline = duration_days or (profile.target_duration_days if profile else None)
    return float(hours), deadline


class RoadmapService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()

    def generate(self, request: RoadmapGenerateRequest) -> RoadmapResponse:
        user = self._db.query(User).filter_by(id=request.user_id).one_or_none()
        if user is None:
            raise UserNotFoundError(request.user_id)

        warnings: list[str] = []
        hours_per_day, deadline_days = self._resolve_pace(user, request, warnings)

        gaps = self._open_gaps(user.id, request.job_description_id)
        if not gaps:
            raise NoOpenSkillGapsError()

        nodes = self._build_nodes(user.id, gaps)
        ordered, had_cycle = order_nodes(nodes)
        if had_cycle:
            warnings.append("The skill prerequisite graph contains a cycle; affected skills were ordered by priority.")

        study_days = self._settings.ROADMAP_STUDY_DAYS_PER_WEEK
        weekly_minutes = max(1, int(hours_per_day * 60 * study_days))
        planned = schedule(ordered, weekly_minutes)
        total_minutes = sum(p.minutes for p in planned)
        estimated_days = days_needed(total_minutes, hours_per_day, study_days)
        fits = None if deadline_days is None else estimated_days <= deadline_days
        if fits is False:
            warnings.append(
                f"At {hours_per_day:g}h/day this plan needs about {estimated_days} days, exceeding the "
                f"{deadline_days}-day deadline; increase daily time, extend the deadline or reduce scope."
            )

        target_role = self._resolve_target_role(request.target_role_id, warnings)
        roadmap = self._persist(user, request, target_role, planned, estimated_days, deadline_days, warnings)
        self._db.commit()
        logger.info(
            "Roadmap generated: items=%d total_minutes=%d est_days=%d warnings=%d",
            len(roadmap.items),
            total_minutes,
            estimated_days,
            len(warnings),
        )
        summary = RoadmapSummary(
            total_estimated_minutes=total_minutes,
            estimated_weeks=-(-total_minutes // weekly_minutes),
            estimated_days=estimated_days,
            hours_per_day=hours_per_day,
            study_days_per_week=study_days,
            deadline_days=deadline_days,
            fits_deadline=fits,
        )
        return self.to_response(roadmap, summary, warnings)

    def get(self, roadmap_id: str) -> RoadmapResponse | None:
        roadmap = self._db.query(Roadmap).filter_by(id=roadmap_id).one_or_none()
        if roadmap is None:
            return None
        return self.to_response(roadmap, self._summary_from_items(roadmap), [])

    # --- inputs ---------------------------------------------------------------------------------

    def _resolve_pace(
        self, user: User, request: RoadmapGenerateRequest, warnings: list[str]
    ) -> tuple[float, int | None]:
        return resolve_pace(self._db, user.id, request.hours_per_day, request.duration_days, warnings)

    def _open_gaps(self, user_id: str, job_description_id: str | None) -> list[SkillGap]:
        query = self._db.query(SkillGap).filter(
            SkillGap.user_id == user_id,
            SkillGap.status.in_(_OPEN_STATUSES),
            SkillGap.match_status != SkillMatchStatus.MATCHED,
        )
        if job_description_id is not None:
            query = query.filter(SkillGap.source_job_description_id == job_description_id)
        return query.order_by(SkillGap.created_at, SkillGap.id).all()

    def _resolve_target_role(self, target_role_id: str | None, warnings: list[str]) -> TargetRole | None:
        if target_role_id is None:
            return None
        role = self._db.query(TargetRole).filter_by(id=target_role_id).one_or_none()
        if role is None:
            warnings.append(f"target_role_id '{target_role_id}' was not found and was ignored.")
        return role

    def _build_nodes(self, user_id: str, gaps: list[SkillGap]) -> dict[str, PlanNode]:
        nodes: dict[str, PlanNode] = {
            gap.skill_id: PlanNode(
                skill_id=gap.skill_id,
                slug=gap.skill.slug,
                name=gap.skill.name,
                current_level=gap.current_level,
                target_level=gap.target_level,
                priority_score=gap.priority_score or 0.0,
            )
            for gap in gaps
        }
        owned = {
            us.skill_id
            for us in self._db.query(UserSkill).filter_by(user_id=user_id).all()
            if us.current_level != SkillLevel.NONE
        }

        # Pull in transitive prerequisites the user has no evidence for.
        frontier = [gap.skill for gap in gaps]
        seen: set[str] = set()
        while frontier:
            skill = frontier.pop()
            if skill.id in seen:
                continue
            seen.add(skill.id)
            for prereq in skill.prerequisites:
                if prereq.id not in nodes and prereq.id not in owned:
                    nodes[prereq.id] = PlanNode(
                        skill_id=prereq.id,
                        slug=prereq.slug,
                        name=prereq.name,
                        current_level=SkillLevel.NONE,
                        target_level=SkillLevel.BEGINNER,
                        priority_score=0.0,
                        is_foundation=True,
                    )
                if prereq.id in nodes:
                    nodes[skill.id].prerequisite_ids.add(prereq.id)
                    frontier.append(prereq)
        return nodes

    # --- persistence ----------------------------------------------------------------------------

    def _persist(
        self,
        user: User,
        request: RoadmapGenerateRequest,
        target_role: TargetRole | None,
        planned: list[PlannedItem],
        estimated_days: int,
        deadline_days: int | None,
        warnings: list[str],
    ) -> Roadmap:
        for old in (
            self._db.query(Roadmap)
            .filter(Roadmap.user_id == user.id, Roadmap.status.in_((RoadmapStatus.DRAFT, RoadmapStatus.ACTIVE)))
            .all()
        ):
            old.status = RoadmapStatus.ARCHIVED

        profile = self._db.query(Profile).filter_by(user_id=user.id).one_or_none()
        goal = target_role.name if target_role else (profile.target_role if profile else None)
        roadmap = Roadmap(
            user_id=user.id,
            target_role_id=target_role.id if target_role else None,
            title=f"Roadmap to {goal}" if goal else "Personalized learning roadmap",
            description=(
                f"{len(planned)} skills ordered by prerequisites and priority, generated by deterministic rules "
                f"from your open skill gaps."
            ),
            duration_days=deadline_days or estimated_days,
            status=RoadmapStatus.ACTIVE,
            generated_by="rules",
        )
        self._db.add(roadmap)
        self._db.flush()

        item_id_by_skill = {p.node.skill_id: str(uuid.uuid4()) for p in planned}
        order_index = 0
        for plan in planned:
            order_index += 1
            node = plan.node
            self._db.add(
                RoadmapItem(
                    id=item_id_by_skill[node.skill_id],
                    roadmap_id=roadmap.id,
                    skill_id=node.skill_id,
                    item_type=RoadmapItemType.SKILL,
                    title=f"{'Foundation: ' if node.is_foundation else ''}Learn {node.name}",
                    description=self._describe(plan),
                    order_index=order_index,
                    week_number=plan.start_week,
                    estimated_minutes=plan.minutes,
                    difficulty=plan.difficulty,
                    prerequisite_item_ids=[item_id_by_skill[s] for s in plan.prerequisite_skill_ids],
                )
            )
            for resource in self._pick_resources(node.skill_id, plan.difficulty):
                order_index += 1
                self._db.add(
                    RoadmapItem(
                        roadmap_id=roadmap.id,
                        skill_id=node.skill_id,
                        item_type=RoadmapItemType.LEARNING_RESOURCE,
                        title=resource.title,
                        description=" · ".join(
                            part for part in (resource.provider, resource.url, resource.description) if part
                        ),
                        order_index=order_index,
                        week_number=plan.start_week,
                        estimated_minutes=resource.estimated_minutes,
                        difficulty=resource.difficulty,
                        prerequisite_item_ids=[item_id_by_skill[node.skill_id]],
                    )
                )
        self._db.flush()
        self._db.refresh(roadmap)
        return roadmap

    @staticmethod
    def _describe(plan: PlannedItem) -> str:
        node = plan.node
        if node.is_foundation:
            return f"Prerequisite for later skills; no existing evidence of {node.name}. Reach beginner level."
        if not has_shortfall(node.current_level, node.target_level):
            return f"Build verifiable evidence of {node.name} at {node.target_level.value} level."
        return (
            f"Move {node.name} from {node.current_level.value} to {node.target_level.value} "
            f"(gap priority {node.priority_score:g})."
        )

    def _pick_resources(self, skill_id: str, difficulty: Difficulty) -> list[LearningResource]:
        resources = self._db.query(LearningResource).filter_by(skill_id=skill_id).all()
        resources.sort(
            key=lambda r: (
                abs(_DIFFICULTY_RANK.get(r.difficulty, 2) - _DIFFICULTY_RANK[difficulty]),
                r.estimated_minutes or 10**9,
                r.title,
            )
        )
        return resources[:_MAX_RESOURCES_PER_SKILL]

    # --- response -------------------------------------------------------------------------------

    @staticmethod
    def _summary_from_items(roadmap: Roadmap) -> RoadmapSummary:
        """Stored-effort view of the work still to do (completed/skipped skills are
        excluded, partial progress discounted) — identical to the full plan for a
        roadmap with no progress. A re-plan's response carries the authoritative
        figures, which also reflect current proficiency."""
        remaining = [
            i
            for i in roadmap.items
            if i.item_type == RoadmapItemType.SKILL
            and i.status not in (RoadmapItemStatus.COMPLETED, RoadmapItemStatus.SKIPPED)
        ]
        return RoadmapSummary(
            total_estimated_minutes=round(
                sum((i.estimated_minutes or 0) * (1 - i.completion_percentage / 100) for i in remaining)
            ),
            estimated_weeks=max((i.week_number or 0 for i in remaining), default=0),
            deadline_days=roadmap.duration_days,
        )

    @staticmethod
    def to_response(roadmap: Roadmap, summary: RoadmapSummary, warnings: list[str]) -> RoadmapResponse:
        return RoadmapResponse(
            id=roadmap.id,
            user_id=roadmap.user_id,
            target_role_id=roadmap.target_role_id,
            title=roadmap.title,
            description=roadmap.description,
            status=roadmap.status,
            generated_by=roadmap.generated_by,
            created_at=roadmap.created_at,
            summary=summary,
            items=[
                RoadmapItemOut(
                    id=i.id,
                    order_index=i.order_index,
                    item_type=i.item_type,
                    skill_slug=i.skill.slug if i.skill else None,
                    title=i.title,
                    description=i.description,
                    week_number=i.week_number,
                    estimated_minutes=i.estimated_minutes,
                    difficulty=i.difficulty,
                    status=i.status,
                    completion_percentage=i.completion_percentage,
                    prerequisite_item_ids=list(i.prerequisite_item_ids or []),
                )
                for i in roadmap.items
            ],
            warnings=warnings,
        )
