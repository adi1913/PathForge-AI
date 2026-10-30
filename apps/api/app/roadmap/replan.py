"""Adaptive re-planning: re-orders and re-schedules the *remaining* skill
items of an existing roadmap, in place, from recorded progress, current
UserSkill levels, revised daily time and an optional revised deadline.
Deterministic (no LLM); never changes item status/progress or UserSkill."""

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import ProgressEventType, RoadmapItemStatus, RoadmapItemType, RoadmapStatus, SkillLevel
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import UserSkill
from app.models.skill_gap import SkillGap
from app.models.user import User
from app.roadmap.access import load_owned_roadmap
from app.roadmap.errors import NothingToReplanError, RoadmapArchivedError
from app.roadmap.planner import (
    MIN_ITEM_MINUTES,
    PlanNode,
    days_needed,
    estimate_minutes,
    order_for_replan,
    schedule,
)
from app.roadmap.progress import RESOLVED
from app.roadmap.schemas import ReplanRequest, ReplanResponse, ReplanSummary, RoadmapSummary
from app.roadmap.service import RoadmapService, resolve_pace

logger = logging.getLogger("pathforge.roadmap")

_TEMP_ORDER_BASE = 1_000_000  # parks order_index values while rows are renumbered (unique per roadmap)


class ReplanService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()

    def replan(self, roadmap_id: str, request: ReplanRequest) -> ReplanResponse:
        roadmap = load_owned_roadmap(self._db, roadmap_id, request.user_id)
        if roadmap.status == RoadmapStatus.ARCHIVED:
            raise RoadmapArchivedError()

        skills = [i for i in roadmap.items if i.item_type == RoadmapItemType.SKILL]
        resolved = [i for i in skills if i.status in RESOLVED]
        remaining = [i for i in skills if i.status not in RESOLVED]
        if not remaining:
            raise NothingToReplanError()

        warnings: list[str] = []
        user = self._db.query(User).filter_by(id=request.user_id).one()
        hours_per_day, deadline_days = resolve_pace(
            self._db, user.id, request.hours_per_day, request.duration_days, warnings
        )

        nodes, minutes_by_id = self._build_nodes(user.id, remaining, {i.id for i in remaining})
        blocked = {i.id for i in remaining if i.status == RoadmapItemStatus.BLOCKED}
        in_progress = {i.id for i in remaining if i.status == RoadmapItemStatus.IN_PROGRESS}
        ordered, had_cycle, stalled = order_for_replan(nodes, blocked, in_progress)
        if had_cycle:
            warnings.append("The item prerequisites contain a cycle; affected items were ordered by priority.")
        if stalled:
            titles = ", ".join(sorted(nodes[sid].name for sid in stalled))
            warnings.append(
                f"Blocked work is scheduled last: {titles} are blocked or depend on a blocked skill; "
                "unblock the blocked item(s) to start them."
            )
        if resolved and any(i.status == RoadmapItemStatus.SKIPPED for i in resolved):
            skipped_ids = {i.id for i in resolved if i.status == RoadmapItemStatus.SKIPPED}
            if any(set(i.prerequisite_item_ids or []) & skipped_ids for i in remaining):
                warnings.append(
                    "Some remaining skills depend on a skipped prerequisite; their prerequisite was not learned."
                )

        study_days = self._settings.ROADMAP_STUDY_DAYS_PER_WEEK
        weekly_minutes = max(1, int(hours_per_day * 60 * study_days))
        planned = schedule(ordered, weekly_minutes, minutes_by_id)
        total_minutes = sum(p.minutes for p in planned)
        estimated_days = days_needed(total_minutes, hours_per_day, study_days)
        fits = None if deadline_days is None else estimated_days <= deadline_days
        if fits is False:
            warnings.append(
                f"At {hours_per_day:g}h/day the remaining work needs about {estimated_days} days, exceeding the "
                f"{deadline_days}-day deadline; increase daily time, extend the deadline or reduce scope."
            )

        changes = self._apply(roadmap, resolved, remaining, planned, request.duration_days)
        self._db.add(
            ProgressEvent(
                user_id=user.id,
                roadmap_item_id=None,
                event_type=ProgressEventType.ROADMAP_REPLANNED,
                previous_value=f"{len(remaining)} remaining skills",
                new_value=f"{total_minutes} min remaining",
                event_metadata={
                    "roadmap_id": roadmap.id,
                    "hours_per_day": hours_per_day,
                    "deadline_days": deadline_days,
                    "fits_deadline": fits,
                    "stalled_item_ids": sorted(stalled),
                    "changes": changes,
                },
            )
        )
        if roadmap.status == RoadmapStatus.COMPLETED:
            roadmap.status = RoadmapStatus.ACTIVE
        self._db.commit()
        self._db.refresh(roadmap)
        logger.info(
            "Roadmap re-planned: remaining=%d resolved=%d minutes=%d est_days=%d moved=%d warnings=%d",
            len(remaining),
            len(resolved),
            total_minutes,
            estimated_days,
            len(changes),
            len(warnings),
        )

        weeks = -(-total_minutes // weekly_minutes)
        summary = RoadmapSummary(
            total_estimated_minutes=total_minutes,
            estimated_weeks=weeks,
            estimated_days=estimated_days,
            hours_per_day=hours_per_day,
            study_days_per_week=study_days,
            deadline_days=deadline_days,
            fits_deadline=fits,
        )
        return ReplanResponse(
            roadmap=RoadmapService.to_response(roadmap, summary, warnings),
            replan=ReplanSummary(
                remaining_skills=len(remaining),
                resolved_skills=len(resolved),
                remaining_minutes=total_minutes,
                estimated_days=estimated_days,
                estimated_weeks=weeks,
                hours_per_day=hours_per_day,
                study_days_per_week=study_days,
                deadline_days=deadline_days,
                fits_deadline=fits,
                stalled_skills=sorted(nodes[sid].name for sid in stalled),
                changed_items=len(changes),
            ),
        )

    # --- inputs ---------------------------------------------------------------------------------

    def _build_nodes(
        self, user_id: str, remaining: list[RoadmapItem], remaining_ids: set[str]
    ) -> tuple[dict[str, PlanNode], dict[str, int]]:
        """Nodes are keyed by roadmap *item* id (PlanNode.skill_id is just the key)."""
        skill_ids = [i.skill_id for i in remaining if i.skill_id]
        levels = {
            us.skill_id: us.current_level
            for us in self._db.query(UserSkill).filter(UserSkill.user_id == user_id, UserSkill.skill_id.in_(skill_ids))
        }
        gaps = {
            g.skill_id: g
            for g in self._db.query(SkillGap).filter(SkillGap.user_id == user_id, SkillGap.skill_id.in_(skill_ids))
        }
        nodes: dict[str, PlanNode] = {}
        minutes: dict[str, int] = {}
        for item in remaining:
            gap = gaps.get(item.skill_id)
            current = levels.get(item.skill_id, SkillLevel.NONE)
            target = gap.target_level if gap else SkillLevel.BEGINNER
            nodes[item.id] = PlanNode(
                skill_id=item.id,
                slug=item.skill.slug if item.skill else item.id,
                name=item.skill.name if item.skill else item.title,
                current_level=current,
                target_level=target,
                priority_score=(gap.priority_score or 0.0) if gap else 0.0,
                prerequisite_ids={p for p in (item.prerequisite_item_ids or []) if p in remaining_ids},
                is_foundation=item.title.startswith("Foundation:"),
            )
            # Remaining effort can only shrink: bounded by what is left of the stored
            # budget AND by what the current proficiency still requires.
            left_of_budget = (item.estimated_minutes or MIN_ITEM_MINUTES) * (1 - item.completion_percentage / 100)
            minutes[item.id] = max(1, round(min(left_of_budget, estimate_minutes(current, target))))
        return nodes, minutes

    # --- persistence ----------------------------------------------------------------------------

    def _apply(
        self,
        roadmap: Roadmap,
        resolved: list[RoadmapItem],
        remaining: list[RoadmapItem],
        planned: list,
        revised_deadline: int | None,
    ) -> list[dict]:
        by_id = {i.id: i for i in roadmap.items}
        resources_of: dict[str, list[RoadmapItem]] = {}
        attached: set[str] = set()
        for item in roadmap.items:
            if item.item_type == RoadmapItemType.SKILL:
                continue
            for pid in item.prerequisite_item_ids or []:
                if pid in by_id and by_id[pid].item_type == RoadmapItemType.SKILL:
                    resources_of.setdefault(pid, []).append(item)
                    attached.add(item.id)
                    break

        def with_resources(skill_items: list[RoadmapItem]) -> list[RoadmapItem]:
            out: list[RoadmapItem] = []
            for item in sorted(skill_items, key=lambda i: i.order_index):
                out.append(item)
                out.extend(sorted(resources_of.get(item.id, []), key=lambda r: r.order_index))
            return out

        remaining_by_id = {i.id: i for i in remaining}
        new_sequence = with_resources(resolved)
        new_sequence += sorted(
            (i for i in roadmap.items if i.item_type != RoadmapItemType.SKILL and i.id not in attached),
            key=lambda i: i.order_index,
        )
        before = {i.id: (i.order_index, i.week_number) for i in remaining}
        week_of: dict[str, int] = {}
        for plan in planned:
            skill_item = remaining_by_id[plan.node.skill_id]
            week_of[skill_item.id] = plan.start_week
            new_sequence.append(skill_item)
            new_sequence.extend(sorted(resources_of.get(skill_item.id, []), key=lambda r: r.order_index))

        for offset, item in enumerate(roadmap.items):  # park, so renumbering never collides
            item.order_index = _TEMP_ORDER_BASE + offset
        self._db.flush()
        for index, item in enumerate(new_sequence, start=1):
            item.order_index = index
        for skill_item_id, week in week_of.items():
            remaining_by_id[skill_item_id].week_number = week
            for resource in resources_of.get(skill_item_id, []):
                resource.week_number = week
        if revised_deadline is not None:
            roadmap.duration_days = revised_deadline
        self._db.flush()

        changes = []
        for item in remaining:
            old_order, old_week = before[item.id]
            if (old_order, old_week) != (item.order_index, item.week_number):
                changes.append(
                    {
                        "item_id": item.id,
                        "order_index": [old_order, item.order_index],
                        "week_number": [old_week, item.week_number],
                    }
                )
        return changes
