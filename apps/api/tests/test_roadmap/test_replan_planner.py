from app.models.enums import SkillLevel
from app.roadmap.planner import PlanNode, order_for_replan, order_nodes, schedule, stalled_ids

L = SkillLevel


def _node(sid, priority=0.0, prereqs=()):
    return PlanNode(
        skill_id=sid,
        slug=sid,
        name=sid,
        current_level=L.NONE,
        target_level=L.BEGINNER,
        priority_score=priority,
        prerequisite_ids=set(prereqs),
    )


def _nodes(*nodes):
    return {n.skill_id: n for n in nodes}


def test_stalled_includes_blocked_and_transitive_dependents_only():
    nodes = _nodes(_node("a"), _node("b", prereqs={"a"}), _node("c", prereqs={"b"}), _node("d"))
    assert stalled_ids(nodes, {"b"}) == {"b", "c"}
    assert stalled_ids(nodes, set()) == set()
    assert stalled_ids(nodes, {"unknown"}) == set()


def test_unblocked_work_goes_first_and_stalled_last_but_nothing_dropped():
    nodes = _nodes(_node("py", 10), _node("ml", 99, prereqs={"py"}), _node("docker", 5))
    ordered, cycle, stalled = order_for_replan(nodes, blocked_ids={"py"}, in_progress_ids=set())
    assert [n.skill_id for n in ordered] == ["docker", "py", "ml"]
    assert stalled == {"py", "ml"} and not cycle


def test_prerequisites_still_precede_dependents_inside_stalled_group():
    nodes = _nodes(_node("a", 1), _node("b", 9, prereqs={"a"}), _node("c", 5, prereqs={"b"}))
    ordered, _, _ = order_for_replan(nodes, {"a"}, set())
    assert [n.skill_id for n in ordered] == ["a", "b", "c"]


def test_in_progress_item_jumps_ahead_of_higher_priority_ready_items():
    nodes = _nodes(_node("hi", 90), _node("mid", 50), _node("lo", 10))
    ordered, _, _ = order_for_replan(nodes, set(), in_progress_ids={"lo"})
    assert [n.skill_id for n in ordered] == ["lo", "hi", "mid"]


def test_in_progress_never_jumps_ahead_of_its_own_prerequisite():
    nodes = _nodes(_node("pre", 1), _node("dep", 1, prereqs={"pre"}), _node("other", 50))
    ordered, _, _ = order_for_replan(nodes, set(), in_progress_ids={"dep"})
    ids = [n.skill_id for n in ordered]
    assert ids.index("pre") < ids.index("dep")


def test_first_ids_default_leaves_phase8_ordering_unchanged():
    nodes = _nodes(_node("b", 50), _node("a", 50), _node("c", 80))
    assert [n.skill_id for n in order_nodes(nodes)[0]] == ["c", "a", "b"]


def test_schedule_minutes_override():
    items = schedule([_node("a"), _node("b"), _node("c")], 100, {"a": 60, "b": 70, "c": 10})
    assert [i.minutes for i in items] == [60, 70, 10]
    assert [i.start_week for i in items] == [1, 1, 2]  # offsets 0, 60, 130
