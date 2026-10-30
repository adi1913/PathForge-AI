"""Progress tracking on roadmap items: validated state transitions, an
append-only ProgressEvent trail (also the source of timestamps), and
roadmap-level progress. Never touches UserSkill — completing an item is not
evidence of mastery."""

import logging

from sqlalchemy.orm import Session

from app.models.enums import ProgressEventType, RoadmapItemStatus, RoadmapItemType, RoadmapStatus
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.roadmap.access import load_owned_roadmap
from app.roadmap.errors import (
    InvalidProgressInputError,
    InvalidTransitionError,
    RoadmapArchivedError,
    RoadmapItemNotFoundError,
)
from app.roadmap.planner import MIN_ITEM_MINUTES
from app.roadmap.schemas import (
    ItemProgress,
    ProgressEventOut,
    ProgressSummary,
    ProgressUpdateRequest,
    ProgressUpdateResponse,
    RoadmapProgressResponse,
)

logger = logging.getLogger("pathforge.roadmap")

S = RoadmapItemStatus
RESOLVED = (S.COMPLETED, S.SKIPPED)
_ALLOWED: dict[S, set[S]] = {
    S.NOT_STARTED: {S.IN_PROGRESS, S.COMPLETED, S.BLOCKED, S.SKIPPED},
    S.IN_PROGRESS: {S.IN_PROGRESS, S.COMPLETED, S.NOT_STARTED, S.BLOCKED, S.SKIPPED},
    S.BLOCKED: {S.IN_PROGRESS, S.NOT_STARTED, S.SKIPPED},
    S.SKIPPED: {S.NOT_STARTED, S.IN_PROGRESS},
    S.COMPLETED: {S.IN_PROGRESS},  # reopen
}
_RECENT_EVENTS = 50


def _fmt(status: S, pct: float) -> str:
    return f"{status.value}:{pct:g}"


def skill_items(roadmap: Roadmap) -> list[RoadmapItem]:
    return [i for i in roadmap.items if i.item_type == RoadmapItemType.SKILL]


def summarize(roadmap: Roadmap) -> ProgressSummary:
    items = skill_items(roadmap)
    counts = {status: sum(1 for i in items if i.status == status) for status in S}
    countable = [i for i in items if i.status != S.SKIPPED]
    percent_items = 100.0 * counts[S.COMPLETED] / len(countable) if countable else 0.0
    total_effort = sum(i.estimated_minutes or MIN_ITEM_MINUTES for i in countable)
    done_effort = sum(
        (i.estimated_minutes or MIN_ITEM_MINUTES) * (1.0 if i.status == S.COMPLETED else i.completion_percentage / 100)
        for i in countable
    )
    return ProgressSummary(
        total_skills=len(items),
        not_started=counts[S.NOT_STARTED],
        in_progress=counts[S.IN_PROGRESS],
        blocked=counts[S.BLOCKED],
        completed=counts[S.COMPLETED],
        skipped=counts[S.SKIPPED],
        percent_by_items=round(percent_items, 1),
        percent_by_effort=round(100.0 * done_effort / total_effort, 1) if total_effort else 0.0,
    )


class ProgressService:
    def __init__(self, db: Session):
        self._db = db

    def update_item(self, roadmap_id: str, item_id: str, request: ProgressUpdateRequest) -> ProgressUpdateResponse:
        roadmap = load_owned_roadmap(self._db, roadmap_id, request.user_id)
        if roadmap.status == RoadmapStatus.ARCHIVED:
            raise RoadmapArchivedError()
        item = next((i for i in roadmap.items if i.id == item_id), None)
        if item is None:
            raise RoadmapItemNotFoundError()

        old_status, old_pct = item.status, item.completion_percentage
        new_status = request.status
        pct = self._resolve_percentage(item, request)
        self._check_transition(old_status, new_status, request)

        warnings = self._prerequisite_warnings(roadmap, item) if new_status in (S.IN_PROGRESS, S.COMPLETED) else []

        item.status, item.completion_percentage = new_status, pct
        self._db.add(
            ProgressEvent(
                user_id=request.user_id,
                roadmap_item_id=item.id,
                event_type=self._event_type(old_status, new_status),
                previous_value=_fmt(old_status, old_pct),
                new_value=_fmt(new_status, pct),
                event_metadata={"roadmap_id": roadmap.id},
            )
        )
        self._sync_roadmap_status(roadmap)
        self._db.commit()
        logger.info("Progress updated: %s -> %s", old_status.value, new_status.value)

        return ProgressUpdateResponse(
            item=self._item_progress(item, *self._timestamps(roadmap).get(item.id, (None, None))),
            roadmap_status=roadmap.status,
            summary=summarize(roadmap),
            warnings=warnings,
        )

    def get_progress(self, roadmap_id: str, user_id: str) -> RoadmapProgressResponse:
        roadmap = load_owned_roadmap(self._db, roadmap_id, user_id)
        stamps = self._timestamps(roadmap)
        events = self._events(roadmap)
        replans = [e for e in events if e.event_type == ProgressEventType.ROADMAP_REPLANNED]
        return RoadmapProgressResponse(
            roadmap_id=roadmap.id,
            status=roadmap.status,
            summary=summarize(roadmap),
            replan_count=len(replans),
            items=[self._item_progress(i, *stamps.get(i.id, (None, None))) for i in skill_items(roadmap)],
            recent_events=[
                ProgressEventOut(
                    id=e.id,
                    event_type=e.event_type.value,
                    roadmap_item_id=e.roadmap_item_id,
                    previous_value=e.previous_value,
                    new_value=e.new_value,
                    created_at=e.created_at,
                    metadata=e.event_metadata,
                )
                for e in reversed(events[-_RECENT_EVENTS:])
            ],
        )

    # --- helpers --------------------------------------------------------------------------------

    @staticmethod
    def _resolve_percentage(item: RoadmapItem, request: ProgressUpdateRequest) -> float:
        status, given = request.status, request.completion_percentage
        if given is not None and status != S.IN_PROGRESS:
            raise InvalidProgressInputError("completion_percentage is only accepted together with status 'in_progress'")
        if status == S.COMPLETED:
            return 100.0
        if status == S.NOT_STARTED:
            return 0.0
        if status == S.IN_PROGRESS:
            if given is not None:
                if given >= 100:
                    raise InvalidProgressInputError("An in-progress item must be below 100%; use status 'completed'")
                return float(given)
            return 0.0 if item.status == S.COMPLETED else item.completion_percentage  # reopen restarts at 0
        return item.completion_percentage  # blocked / skipped keep partial progress

    @staticmethod
    def _check_transition(old: S, new: S, request: ProgressUpdateRequest) -> None:
        if new not in _ALLOWED[old]:
            raise InvalidTransitionError(f"Cannot move an item from '{old.value}' to '{new.value}'")
        if old == new and request.completion_percentage is None:
            raise InvalidTransitionError("Item is already in progress; provide completion_percentage to update it")

    @staticmethod
    def _event_type(old: S, new: S) -> ProgressEventType:
        return {
            S.COMPLETED: ProgressEventType.ITEM_COMPLETED,
            S.SKIPPED: ProgressEventType.ITEM_SKIPPED,
            S.BLOCKED: ProgressEventType.ITEM_BLOCKED,
            S.NOT_STARTED: ProgressEventType.ITEM_PROGRESS_UPDATED,
            S.IN_PROGRESS: (
                ProgressEventType.ITEM_PROGRESS_UPDATED if old == S.IN_PROGRESS else ProgressEventType.ITEM_STARTED
            ),
        }[new]

    @staticmethod
    def _prerequisite_warnings(roadmap: Roadmap, item: RoadmapItem) -> list[str]:
        by_id = {i.id: i for i in roadmap.items}
        return [
            f"Prerequisite '{by_id[pid].title}' is not completed yet."
            for pid in (item.prerequisite_item_ids or [])
            if pid in by_id and by_id[pid].status not in RESOLVED
        ]

    @staticmethod
    def _sync_roadmap_status(roadmap: Roadmap) -> None:
        skills = skill_items(roadmap)
        if not skills:
            return
        if all(i.status in RESOLVED for i in skills):
            roadmap.status = RoadmapStatus.COMPLETED
        elif roadmap.status == RoadmapStatus.COMPLETED:
            roadmap.status = RoadmapStatus.ACTIVE

    def _events(self, roadmap: Roadmap) -> list[ProgressEvent]:
        item_ids = [i.id for i in roadmap.items]
        rows = (
            self._db.query(ProgressEvent)
            .filter(ProgressEvent.user_id == roadmap.user_id)
            .order_by(ProgressEvent.created_at, ProgressEvent.id)
            .all()
        )
        return [
            e for e in rows if e.roadmap_item_id in item_ids or (e.event_metadata or {}).get("roadmap_id") == roadmap.id
        ]

    def _timestamps(self, roadmap: Roadmap) -> dict[str, tuple]:
        """item id -> (started_at = first start, completed_at = latest completion
        while still completed), derived from the event trail."""
        started: dict[str, object] = {}
        completed: dict[str, object] = {}
        for event in self._events(roadmap):
            if event.roadmap_item_id is None:
                continue
            if event.event_type == ProgressEventType.ITEM_STARTED:
                started.setdefault(event.roadmap_item_id, event.created_at)
            elif event.event_type == ProgressEventType.ITEM_COMPLETED:
                completed[event.roadmap_item_id] = event.created_at
        statuses = {i.id: i.status for i in roadmap.items}
        return {
            item_id: (started.get(item_id), completed.get(item_id) if statuses[item_id] == S.COMPLETED else None)
            for item_id in statuses
        }

    @staticmethod
    def _item_progress(item: RoadmapItem, started_at, completed_at) -> ItemProgress:
        return ItemProgress(
            item_id=item.id,
            item_type=item.item_type,
            skill_slug=item.skill.slug if item.skill else None,
            title=item.title,
            status=item.status,
            completion_percentage=item.completion_percentage,
            order_index=item.order_index,
            week_number=item.week_number,
            started_at=started_at,
            completed_at=completed_at,
        )
