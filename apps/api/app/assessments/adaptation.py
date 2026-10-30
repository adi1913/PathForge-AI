"""Assessment -> roadmap adaptation (docs/phase12_spec.md §7). Deterministic, no LLM.

strong : halve the skill item's estimate once (floor MIN_ITEM_MINUTES) and skip its NOT_STARTED beginner
         resources. The skill item is never completed or marked mastered.
weak   : add missing direct prerequisites, one revision item and one exercises item (no duplicates).
passed / insufficient : no roadmap change.
Every change is a ProgressEvent tagged source="assessment_adaptation"; a Phase 9 re-plan then re-sequences.
UserSkill is never touched here."""

import logging

from sqlalchemy.orm import Session

from app.assessments.schemas import AdaptationAction, AdaptationOut
from app.core.config import Settings, get_settings
from app.models.assessment import Assessment
from app.models.enums import (
    AssessmentOutcome,
    Difficulty,
    ProgressEventType,
    RoadmapItemStatus,
    RoadmapItemType,
    RoadmapStatus,
    SkillLevel,
)
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import Skill, UserSkill
from app.roadmap.errors import RoadmapError
from app.roadmap.planner import MIN_ITEM_MINUTES, estimate_minutes
from app.roadmap.replan import ReplanService
from app.roadmap.schemas import ReplanRequest

logger = logging.getLogger("pathforge.assessments")

SOURCE = "assessment_adaptation"
SHRINK_FACTOR = 0.5
REVISION_MINUTES = 60
EXERCISE_MINUTES = 90
_SOLID_CONFIDENCE = 0.4
_RESOLVED = (RoadmapItemStatus.COMPLETED, RoadmapItemStatus.SKIPPED)


class AdaptationService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()

    def adapt(self, assessment: Assessment, outcome: AssessmentOutcome, attempt_id: str) -> AdaptationOut:
        if outcome not in (AssessmentOutcome.STRONG, AssessmentOutcome.WEAK):
            return self._none(None, "No roadmap change for this outcome.")
        roadmap, skill_item = self._locate(assessment)
        if roadmap is None or skill_item is None:
            return self._none(None, "No active roadmap item for this skill, so the roadmap was not changed.")

        actions: list[AdaptationAction] = []
        meta = {"roadmap_id": roadmap.id, "source": SOURCE, "attempt_id": attempt_id, "outcome": outcome.value}
        if outcome == AssessmentOutcome.STRONG:
            self._strong(roadmap, skill_item, assessment, meta, actions)
        else:
            self._weak(roadmap, skill_item, assessment, meta, actions)
        warnings: list[str] = []
        if not actions:
            return AdaptationOut(
                roadmap_id=roadmap.id, actions=[], replanned=False, warnings=["Roadmap already reflects this result."]
            )
        self._db.commit()  # the changes stand even if the re-plan below cannot run

        replanned = False
        try:
            response = ReplanService(self._db, self._settings).replan(
                roadmap.id, ReplanRequest(user_id=assessment.user_id)
            )
            replanned = True
            warnings.extend(response.roadmap.warnings)
        except RoadmapError as exc:
            warnings.append(f"Roadmap changed but could not be re-planned: {exc.message}")
        if skill_item.status == RoadmapItemStatus.COMPLETED and outcome == AssessmentOutcome.WEAK:
            warnings.append(
                "The skill item was already completed and stays completed; revision/exercise items were added."
            )
        return AdaptationOut(roadmap_id=roadmap.id, actions=actions, replanned=replanned, warnings=warnings)

    # --- locate ---------------------------------------------------------------------------------

    def _locate(self, assessment: Assessment) -> tuple[Roadmap | None, RoadmapItem | None]:
        candidates: list[Roadmap] = []
        if assessment.roadmap_item_id:
            item = self._db.get(RoadmapItem, assessment.roadmap_item_id)
            if item is not None:
                candidates.append(item.roadmap)
        candidates += (
            self._db.query(Roadmap)
            .filter_by(user_id=assessment.user_id, status=RoadmapStatus.ACTIVE)
            .order_by(Roadmap.created_at.desc(), Roadmap.id)
            .all()
        )
        for roadmap in candidates:
            if roadmap.user_id != assessment.user_id or roadmap.status == RoadmapStatus.ARCHIVED:
                continue
            for item in roadmap.items:
                if item.item_type == RoadmapItemType.SKILL and item.skill_id == assessment.skill_id:
                    return roadmap, item
        return None, None

    @staticmethod
    def _none(roadmap_id: str | None, reason: str) -> AdaptationOut:
        return AdaptationOut(roadmap_id=roadmap_id, actions=[], replanned=False, warnings=[reason])

    # --- strong ---------------------------------------------------------------------------------

    def _strong(self, roadmap, skill_item, assessment, meta, actions) -> None:
        if skill_item.status not in _RESOLVED and not self._already_shrunk(assessment.user_id, skill_item.id):
            old = skill_item.estimated_minutes or MIN_ITEM_MINUTES
            new = max(MIN_ITEM_MINUTES, round(old * SHRINK_FACTOR))
            if new < old:
                skill_item.estimated_minutes = new
                self._event(
                    assessment.user_id,
                    skill_item.id,
                    ProgressEventType.ITEM_PROGRESS_UPDATED,
                    f"{old} min",
                    f"{new} min",
                    {**meta, "action": "shrink_estimate"},
                )
                actions.append(
                    AdaptationAction(
                        action="reduced_estimate",
                        item_title=skill_item.title,
                        detail=f"Estimate reduced from {old} to {new} minutes after a strong result.",
                    )
                )
        for item in roadmap.items:
            if (
                item.item_type == RoadmapItemType.LEARNING_RESOURCE
                and item.skill_id == assessment.skill_id
                and item.difficulty == Difficulty.BEGINNER
                and item.status == RoadmapItemStatus.NOT_STARTED
                and not item.title.startswith("Revision:")
            ):
                item.status = RoadmapItemStatus.SKIPPED
                self._event(
                    assessment.user_id,
                    item.id,
                    ProgressEventType.ITEM_SKIPPED,
                    "not_started:0",
                    "skipped:0",
                    {**meta, "action": "skip_beginner_resource"},
                )
                actions.append(
                    AdaptationAction(
                        action="skipped_beginner_resource",
                        item_title=item.title,
                        detail="Beginner material skipped after a strong result (can be reopened).",
                    )
                )

    def _already_shrunk(self, user_id: str, item_id: str) -> bool:
        events = self._db.query(ProgressEvent).filter_by(
            user_id=user_id, roadmap_item_id=item_id, event_type=ProgressEventType.ITEM_PROGRESS_UPDATED
        )
        return any((e.event_metadata or {}).get("action") == "shrink_estimate" for e in events)

    # --- weak -----------------------------------------------------------------------------------

    def _weak(self, roadmap, skill_item, assessment, meta, actions) -> None:
        skill = self._db.get(Skill, assessment.skill_id)
        user_id = assessment.user_id
        next_order = max((i.order_index for i in roadmap.items), default=0)
        in_roadmap = {i.skill_id for i in roadmap.items if i.item_type == RoadmapItemType.SKILL}
        owned = {us.skill_id: us for us in self._db.query(UserSkill).filter_by(user_id=user_id)}

        for prereq in sorted(skill.prerequisites, key=lambda s: s.slug):
            us = owned.get(prereq.id)
            solid = (
                us is not None
                and us.current_level != SkillLevel.NONE
                and (us.confidence if us.confidence is not None else 0.5) >= _SOLID_CONFIDENCE
            )
            if prereq.id in in_roadmap or solid:
                continue
            next_order += 1
            item = RoadmapItem(
                roadmap_id=roadmap.id,
                skill_id=prereq.id,
                item_type=RoadmapItemType.SKILL,
                title=f"Foundation: Learn {prereq.name}",
                description=(
                    f"Added after a weak {skill.name} assessment: a prerequisite with no solid evidence. "
                    "Reach beginner level."
                ),
                order_index=next_order,
                week_number=skill_item.week_number,
                estimated_minutes=estimate_minutes(SkillLevel.NONE, SkillLevel.BEGINNER),
                difficulty=Difficulty.BEGINNER,
                prerequisite_item_ids=[],
            )
            self._db.add(item)
            self._db.flush()
            skill_item.prerequisite_item_ids = [*(skill_item.prerequisite_item_ids or []), item.id]
            self._event(
                user_id,
                item.id,
                ProgressEventType.ITEM_PROGRESS_UPDATED,
                None,
                "not_started:0",
                {**meta, "action": "add_prerequisite"},
            )
            actions.append(
                AdaptationAction(
                    action="added_prerequisite",
                    item_title=item.title,
                    detail=f"{prereq.name} is a prerequisite of {skill.name} and has no solid evidence.",
                )
            )

        extras = [
            (
                f"Revision: {skill.name}",
                RoadmapItemType.LEARNING_RESOURCE,
                REVISION_MINUTES,
                "added_revision",
                "Self-review of the topics you missed in your assessment (no external resource is attached).",
            ),
            (
                f"Practice exercises: {skill.name}",
                RoadmapItemType.PROJECT,
                EXERCISE_MINUTES,
                "added_exercises",
                "Hands-on practice on the areas the assessment showed as weak.",
            ),
        ]
        existing = {(i.item_type, i.title) for i in roadmap.items}
        for title, item_type, minutes, action, description in extras:
            if (item_type, title) in existing:
                continue
            next_order += 1
            item = RoadmapItem(
                roadmap_id=roadmap.id,
                skill_id=skill.id,
                item_type=item_type,
                title=title,
                description=description,
                order_index=next_order,
                week_number=skill_item.week_number,
                estimated_minutes=minutes,
                difficulty=skill_item.difficulty,
                prerequisite_item_ids=[skill_item.id],
            )
            self._db.add(item)
            self._db.flush()
            self._event(
                user_id,
                item.id,
                ProgressEventType.ITEM_PROGRESS_UPDATED,
                None,
                "not_started:0",
                {**meta, "action": action},
            )
            actions.append(AdaptationAction(action=action, item_title=title, detail=description))
        if roadmap.status == RoadmapStatus.COMPLETED and any(a.action == "added_prerequisite" for a in actions):
            roadmap.status = RoadmapStatus.ACTIVE

    def _event(self, user_id, item_id, event_type, previous, new, metadata) -> None:
        self._db.add(
            ProgressEvent(
                user_id=user_id,
                roadmap_item_id=item_id,
                event_type=event_type,
                previous_value=previous,
                new_value=new,
                event_metadata=metadata,
            )
        )
