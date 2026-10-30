from app.models.enums import Difficulty, SkillLevel
from app.roadmap.planner import (
    PlanNode,
    days_needed,
    difficulty_for,
    effective_priorities,
    estimate_minutes,
    has_shortfall,
    order_nodes,
    schedule,
)

L = SkillLevel


def _node(sid, priority=0.0, prereqs=(), current=L.NONE, target=L.INTERMEDIATE, foundation=False):
    return PlanNode(
        skill_id=sid,
        slug=sid,
        name=sid.title(),
        current_level=current,
        target_level=target,
        priority_score=priority,
        prerequisite_ids=set(prereqs),
        is_foundation=foundation,
    )


def _order(*nodes):
    ordered, cycle = order_nodes({n.skill_id: n for n in nodes})
    return [n.skill_id for n in ordered], cycle


def test_estimate_minutes_sums_each_level_step():
    assert estimate_minutes(L.NONE, L.BEGINNER) == 480
    assert estimate_minutes(L.BEGINNER, L.ADVANCED) == 900 + 1500
    assert estimate_minutes(L.NONE, L.EXPERT) == 480 + 900 + 1500 + 2400


def test_no_shortfall_gets_evidence_floor():
    assert estimate_minutes(L.ADVANCED, L.ADVANCED) == 120
    assert not has_shortfall(L.ADVANCED, L.ADVANCED)
    assert has_shortfall(L.BEGINNER, L.ADVANCED)


def test_difficulty_mapping():
    assert difficulty_for(L.BEGINNER) == Difficulty.BEGINNER
    assert difficulty_for(L.INTERMEDIATE) == Difficulty.INTERMEDIATE
    assert difficulty_for(L.EXPERT) == Difficulty.ADVANCED


def test_prerequisites_precede_dependents_even_if_dependent_has_higher_priority():
    order, cycle = _order(
        _node("dl", 90, prereqs={"ml"}), _node("ml", 10, prereqs={"py"}), _node("py", 0, foundation=True)
    )
    assert order == ["py", "ml", "dl"] and not cycle


def test_independent_skills_ordered_by_priority_then_slug():
    order, _ = _order(_node("b", 50), _node("a", 50), _node("c", 80), _node("d", 10))
    assert order == ["c", "a", "b", "d"]


def test_foundation_inherits_priority_of_urgent_dependent():
    # py is a foundation (0) of urgent "rag"; unrelated "docker" is medium. py must not be starved.
    nodes = {
        "rag": _node("rag", 90, prereqs={"py"}),
        "py": _node("py", 0, foundation=True),
        "docker": _node("docker", 40),
    }
    assert effective_priorities(nodes)["py"] == 90
    assert [n.skill_id for n in order_nodes(nodes)[0]] == ["py", "rag", "docker"]


def test_ordering_is_deterministic_regardless_of_input_order():
    nodes = [_node("x", 30), _node("y", 30, prereqs={"x"}), _node("z", 70), _node("w", 30)]
    first = _order(*nodes)
    second = _order(*reversed(nodes))
    assert first == second


def test_cycle_is_reported_and_nothing_dropped():
    order, cycle = _order(_node("a", 5, prereqs={"b"}), _node("b", 9, prereqs={"a"}), _node("c", 1))
    assert cycle and sorted(order) == ["a", "b", "c"]


def test_schedule_assigns_start_weeks_from_weekly_capacity():
    ordered = [_node("a", target=L.BEGINNER), _node("b", target=L.INTERMEDIATE), _node("c", target=L.BEGINNER)]
    items = schedule(ordered, weekly_minutes=600)  # a=480, b=1380, c=480
    assert [i.order for i in items] == [1, 2, 3]
    assert [i.minutes for i in items] == [480, 1380, 480]
    assert [i.start_week for i in items] == [1, 1, 4]  # offsets 0, 480, 1860 -> weeks 1, 1, 4


def test_schedule_week_arithmetic_exact():
    ordered = [_node("a", target=L.BEGINNER), _node("b", target=L.BEGINNER)]
    items = schedule(ordered, weekly_minutes=480)
    assert [i.start_week for i in items] == [1, 2]


def test_schedule_records_prerequisite_skill_ids_sorted():
    items = schedule([_node("c", prereqs={"b", "a"})], 600)
    assert items[0].prerequisite_skill_ids == ["a", "b"]


def test_days_needed_counts_only_study_days():
    # 10 study days at 1h/day (600 min), 5 days/week -> 2 full weeks = 14 calendar days
    assert days_needed(600, 1.0, 5) == 14
    # 7 study days -> 1 week + 2 days
    assert days_needed(420, 1.0, 5) == 9
    assert days_needed(30, 1.0, 5) == 1
