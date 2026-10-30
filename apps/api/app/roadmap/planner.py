"""Pure, deterministic roadmap planning (no DB, no LLM): ordering,
effort estimation and week scheduling. The service layer feeds it plain
dataclasses and persists the result."""

import heapq
import math
from dataclasses import dataclass, field, replace

from app.models.enums import Difficulty, SkillLevel

_LEVEL_RANK = {
    SkillLevel.NONE: 0,
    SkillLevel.BEGINNER: 1,
    SkillLevel.INTERMEDIATE: 2,
    SkillLevel.ADVANCED: 3,
    SkillLevel.EXPERT: 4,
}
_RANK_LEVEL = {rank: level for level, rank in _LEVEL_RANK.items()}
# Minutes needed to climb INTO each level from the one below it.
MINUTES_TO_REACH = {1: 480, 2: 900, 3: 1500, 4: 2400}
MIN_ITEM_MINUTES = 120  # evidence-building floor when there is no level shortfall


@dataclass
class PlanNode:
    skill_id: str
    slug: str
    name: str
    current_level: SkillLevel
    target_level: SkillLevel
    priority_score: float  # 0 for foundations
    prerequisite_ids: set[str] = field(default_factory=set)  # skill ids, restricted to the plan
    is_foundation: bool = False


@dataclass
class PlannedItem:
    node: PlanNode
    order: int
    minutes: int
    difficulty: Difficulty
    start_week: int
    prerequisite_skill_ids: list[str]


def estimate_minutes(current: SkillLevel, target: SkillLevel) -> int:
    start, end = _LEVEL_RANK[current], _LEVEL_RANK[target]
    if end <= start:
        return MIN_ITEM_MINUTES
    return sum(MINUTES_TO_REACH[rank] for rank in range(start + 1, end + 1))


def has_shortfall(current: SkillLevel, target: SkillLevel) -> bool:
    return _LEVEL_RANK[target] > _LEVEL_RANK[current]


def difficulty_for(target: SkillLevel) -> Difficulty:
    if target in (SkillLevel.NONE, SkillLevel.BEGINNER):
        return Difficulty.BEGINNER
    if target == SkillLevel.INTERMEDIATE:
        return Difficulty.INTERMEDIATE
    return Difficulty.ADVANCED


def effective_priorities(nodes: dict[str, PlanNode]) -> dict[str, float]:
    """A node's effective priority is the max of its own and that of every
    (transitive) dependent, so the foundations of an urgent gap are not
    starved by unrelated medium-priority gaps."""
    dependents: dict[str, set[str]] = {sid: set() for sid in nodes}
    for node in nodes.values():
        for prereq in node.prerequisite_ids:
            dependents[prereq].add(node.skill_id)

    effective: dict[str, float] = {}

    def resolve(skill_id: str, trail: frozenset[str]) -> float:
        if skill_id in effective:
            return effective[skill_id]
        best = nodes[skill_id].priority_score
        for dep in dependents[skill_id]:
            if dep not in trail:  # cycle guard
                best = max(best, resolve(dep, trail | {skill_id}))
        effective[skill_id] = best
        return best

    for sid in sorted(nodes):
        resolve(sid, frozenset())
    return effective


def order_nodes(nodes: dict[str, PlanNode], first_ids: frozenset[str] = frozenset()) -> tuple[list[PlanNode], bool]:
    """Kahn topological sort; ready nodes are taken by highest effective
    priority then slug (nodes in `first_ids` jump ahead of other ready
    nodes, never ahead of their own prerequisites). Returns (ordered nodes,
    had_cycle)."""
    effective = effective_priorities(nodes)
    remaining_prereqs = {sid: set(n.prerequisite_ids) for sid, n in nodes.items()}
    dependents: dict[str, list[str]] = {sid: [] for sid in nodes}
    for sid, node in nodes.items():
        for prereq in node.prerequisite_ids:
            dependents[prereq].append(sid)

    def key(sid: str) -> tuple[int, float, str]:
        return (0 if sid in first_ids else 1, -effective[sid], nodes[sid].slug)

    heap = [(key(sid), sid) for sid, deps in remaining_prereqs.items() if not deps]
    heapq.heapify(heap)
    ordered: list[PlanNode] = []
    while heap:
        _, sid = heapq.heappop(heap)
        ordered.append(nodes[sid])
        for dependent in dependents[sid]:
            remaining_prereqs[dependent].discard(sid)
            if not remaining_prereqs[dependent]:
                heapq.heappush(heap, (key(dependent), dependent))

    had_cycle = len(ordered) < len(nodes)
    if had_cycle:
        placed = {n.skill_id for n in ordered}
        ordered += sorted((n for sid, n in nodes.items() if sid not in placed), key=lambda n: key(n.skill_id))
    return ordered, had_cycle


def schedule(
    ordered: list[PlanNode], weekly_minutes: int, minutes_by_id: dict[str, int] | None = None
) -> list[PlannedItem]:
    """`minutes_by_id` overrides the level-based estimate (used by re-planning,
    where the remaining effort is already known)."""
    items: list[PlannedItem] = []
    cumulative = 0
    for index, node in enumerate(ordered, start=1):
        minutes = (minutes_by_id or {}).get(node.skill_id)
        if minutes is None:
            minutes = estimate_minutes(node.current_level, node.target_level)
        items.append(
            PlannedItem(
                node=node,
                order=index,
                minutes=minutes,
                difficulty=difficulty_for(node.target_level),
                start_week=cumulative // weekly_minutes + 1,
                prerequisite_skill_ids=sorted(node.prerequisite_ids),
            )
        )
        cumulative += minutes
    return items


def days_needed(total_minutes: int, hours_per_day: float, study_days_per_week: int) -> int:
    """Calendar days to finish, counting only study days."""
    daily = hours_per_day * 60
    study_days = math.ceil(total_minutes / daily)
    full_weeks, extra_days = divmod(study_days, study_days_per_week)
    return full_weeks * 7 + extra_days


def stalled_ids(nodes: dict[str, PlanNode], blocked_ids: set[str]) -> set[str]:
    """Blocked nodes plus everything that transitively depends on them."""
    dependents: dict[str, list[str]] = {sid: [] for sid in nodes}
    for node in nodes.values():
        for prereq in node.prerequisite_ids:
            dependents[prereq].append(node.skill_id)
    stalled: set[str] = set()
    stack = [sid for sid in blocked_ids if sid in nodes]
    while stack:
        sid = stack.pop()
        if sid in stalled:
            continue
        stalled.add(sid)
        stack.extend(dependents[sid])
    return stalled


def order_for_replan(
    nodes: dict[str, PlanNode], blocked_ids: set[str], in_progress_ids: set[str]
) -> tuple[list[PlanNode], bool, set[str]]:
    """Unblocked work first (in-progress items ahead of other ready ones),
    then stalled work (blocked items and their dependents) — both
    prerequisite-ordered. An unblocked node can never depend on a stalled
    one (it would be stalled itself), so prerequisites always precede
    dependents. Returns (ordered nodes, had_cycle, stalled ids)."""
    stalled = stalled_ids(nodes, blocked_ids)

    def subset(ids: set[str]) -> dict[str, PlanNode]:
        return {sid: replace(nodes[sid], prerequisite_ids=nodes[sid].prerequisite_ids & ids) for sid in ids}

    free_ids = set(nodes) - stalled
    free_order, free_cycle = order_nodes(subset(free_ids), frozenset(in_progress_ids))
    stalled_order, stalled_cycle = order_nodes(subset(stalled), frozenset(in_progress_ids))
    return free_order + stalled_order, free_cycle or stalled_cycle, stalled
