"""Tests verifying held_object tracking across schedulers.

Issue #1: EDF/CPM update_state() passes held_object=current_state.held_object
(the *old* state) instead of exec_info.held_object (the *new* state after
execution). This means that after a GRASP subtask, EDF/CPM enter the next
subtask still "empty-handed", causing a subsequent PLACE to fail.

Test design note
----------------
The action handler has an independent bug: `new_held_object = None` is
initialized once *before* the simulation loop, and NAVIGATE_TO does not
reassign it — so after any NAVIGATE_TO step the outer `current_held_object`
is overwritten with None, losing the initial sim_state.held_object.

To isolate the EDF/CPM held_object bug we therefore avoid NAVIGATE_TO in the
primitive actions by placing the agent and objects within reachable distance
(< 50 units) *from the start*, so GRASP/PLACE can run without a preceding
NAVIGATE_TO step.
"""

from __future__ import annotations

import networkx as nx

from src.models.dataclass import SchedulerState, SimulationNode
from src.models.task import Duration, Execution, Subtask
from src.scheduler.action_handler import ActionHandler

# ---------------------------------------------------------------------------
# Minimal scene fixtures
# ---------------------------------------------------------------------------

NAV_GRAPH: dict = {
    (0.0, 0.0, 0.0): [(0.0, 0.0, 1.0)],
    (0.0, 0.0, 1.0): [(0.0, 0.0, 0.0), (0.0, 0.0, 2.0)],
    (0.0, 0.0, 2.0): [(0.0, 0.0, 1.0)],
}

SCENE_POSITIONS: dict = {
    "agent": (0.0, 0.0, 0.0),
    "ObjectX|1": (0.0, 0.0, 1.0),   # distance 1 — reachable without nav
    "ReceptacleY|1": (0.0, 0.0, 2.0),  # distance 2 — also reachable without nav
}


def _make_subtask(name: str, actions: list[str]) -> Subtask:
    return Subtask(
        task_name="test_task",
        name=name,
        repetition=1,
        subtask_type="interaction",
        execution=Execution(objects={}, primitive_actions=actions),
        duration=Duration(type="fixed", interval=10),
    )


def _make_node(state: SchedulerState) -> SimulationNode:
    return SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
    )


def _make_initial_state(held_object: str | None) -> SchedulerState:
    return SchedulerState(
        subtask=None,
        completed_entries=[],
        remaining_subtasks=[],
        constraints=nx.DiGraph(),
        current_time=0.0,
        scene_positions=dict(SCENE_POSITIONS),
        held_object=held_object,
        agent_location=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scheduler_updates_held_object_after_grasp():
    """After simulating GRASP, the Scheduler propagates exec_info.held_object
    to the next state. A subsequent PLACE in that new state should succeed."""
    handler = ActionHandler(nav_graph=NAV_GRAPH)

    # --- Subtask A: GRASP ObjectX|1 (no nav — agent already adjacent) ---
    state_a = _make_initial_state(held_object=None)
    node_a = _make_node(state_a)
    subtask_a = _make_subtask("grasp_a", ["GRASP ObjectX|1"])

    exec_info_a = handler.get_actions_info(node_a, subtask_a.execution.primitive_actions)

    assert exec_info_a is not None, "GRASP simulation returned None"
    assert exec_info_a.success, "GRASP should succeed when agent is empty-handed"
    assert exec_info_a.held_object == "ObjectX|1", (
        f"exec_info.held_object should be 'ObjectX|1' after GRASP, got {exec_info_a.held_object!r}"
    )

    # --- Scheduler-style state update: use exec_info.held_object ---
    state_b_scheduler = SchedulerState(
        subtask=subtask_a,
        completed_entries=[],
        remaining_subtasks=[],
        constraints=nx.DiGraph(),
        current_time=exec_info_a.cumulative_time,
        scene_positions=exec_info_a.scene_positions,
        held_object=exec_info_a.held_object,  # ← correct: from exec result
        agent_location=None,
    )

    # --- Subtask B: PLACE_INSIDE ObjectX|1 ReceptacleY|1 ---
    node_b_scheduler = _make_node(state_b_scheduler)
    subtask_b = _make_subtask("place_b", ["PLACE_INSIDE ObjectX|1 ReceptacleY|1"])

    exec_info_b = handler.get_actions_info(node_b_scheduler, subtask_b.execution.primitive_actions)

    assert exec_info_b is not None, "PLACE simulation returned None (Scheduler)"
    assert exec_info_b.success, (
        "PLACE should succeed when Scheduler correctly tracks held_object='ObjectX|1'"
    )


def test_edf_stale_held_object_causes_place_failure():
    """EDF update_state passes held_object=current_state.held_object (stale).
    After a GRASP, the next state has held_object=None, causing PLACE to fail."""
    handler = ActionHandler(nav_graph=NAV_GRAPH)

    # --- Same GRASP simulation as above ---
    state_a = _make_initial_state(held_object=None)
    node_a = _make_node(state_a)
    subtask_a = _make_subtask("grasp_a", ["GRASP ObjectX|1"])

    exec_info_a = handler.get_actions_info(node_a, subtask_a.execution.primitive_actions)

    assert exec_info_a is not None
    assert exec_info_a.held_object == "ObjectX|1", (
        "Precondition: GRASP must succeed for this test to be meaningful"
    )

    # --- EDF-style state update: held_object = current_state.held_object (NOT exec_info) ---
    state_b_edf = SchedulerState(
        subtask=subtask_a,
        completed_entries=[],
        remaining_subtasks=[],
        constraints=nx.DiGraph(),
        current_time=exec_info_a.cumulative_time,
        scene_positions=exec_info_a.scene_positions,
        held_object=state_a.held_object,  # ← EDF bug: stale value (None)
        agent_location=None,
    )

    assert state_b_edf.held_object is None, (
        "Precondition: EDF state must have stale held_object=None after GRASP"
    )

    # --- Subtask B: PLACE_INSIDE with stale state ---
    node_b_edf = _make_node(state_b_edf)
    subtask_b = _make_subtask("place_b", ["PLACE_INSIDE ObjectX|1 ReceptacleY|1"])

    exec_info_b_edf = handler.get_actions_info(node_b_edf, subtask_b.execution.primitive_actions)

    assert exec_info_b_edf is not None, "PLACE simulation returned None (EDF)"
    assert not exec_info_b_edf.success, (
        "PLACE should FAIL when EDF's stale held_object=None is passed to the next state "
        "(agent is not holding anything, so PLACE_INSIDE has nothing to place)"
    )
