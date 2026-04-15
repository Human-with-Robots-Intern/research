"""Tests for strict oracle timing validation and deadline pruning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import networkx as nx

from src.experiments.exact_oracle import DeterministicExactOracle
from src.models.dataclass import Candidate, CompletedEntry, CriticalContext, SchedulerState
from src.models.task import Duration, Execution, Subtask


def _oracle() -> DeterministicExactOracle:
    with patch("src.experiments.exact_oracle.Scheduler"):
        return DeterministicExactOracle(
            action_handler=MagicMock(),
            constraint_handler=MagicMock(),
            heuristic_manager=MagicMock(),
            time_limit_seconds=30.0,
        )


def _node(current_time: float):
    node = MagicMock()
    node.state.current_time = current_time
    return node


def _subtask(name: str) -> Subtask:
    return Subtask(
        task_name="task",
        name=name,
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["WAIT 0.0"]),
        duration=Duration(type="Interaction", interval=1.0),
    )


def _entry(
    name: str,
    schedule_start: float,
    schedule_end: float,
    *,
    nav_time: float = 0.0,
) -> CompletedEntry:
    return CompletedEntry(
        subtask=_subtask(name),
        schedule_start_time=schedule_start,
        schedule_end_time=schedule_end,
        sim_start_time=schedule_start,
        sim_end_time=schedule_end,
        schedule_nav_time=nav_time,
        execution_status=True,
    )


def _terminal_state(
    completed_entries: list[CompletedEntry],
    constraints: nx.DiGraph | None,
) -> SchedulerState:
    current_subtask = completed_entries[-1].subtask if completed_entries else _subtask("Idle")
    current_time = (
        float(completed_entries[-1].schedule_end_time) if completed_entries else 0.0
    )
    return SchedulerState(
        subtask=current_subtask,
        completed_entries=completed_entries,
        remaining_subtasks=[],
        constraints=constraints,
        current_time=current_time,
        scene_positions={},
        held_object=None,
    )


def _candidate(
    is_critical: bool,
    lit: float | None,
    *,
    interval: float = 100.0,
    nav_duration: float = 0.0,
) -> Candidate:
    return Candidate(
        subtask=_subtask("Candidate"),
        is_critical=is_critical,
        logical_interaction_start_time=lit,
        estimated_first_nav_duration=nav_duration,
        critical_context=(
            CriticalContext(
                source_subtask="Pred",
                source_end_time=10.0,
                interval=interval,
                logical_start_time=lit,
            )
            if lit is not None
            else None
        ),
    )


def test_not_critical_never_violated() -> None:
    """Non-critical candidates are never pruned by strict deadline checks."""

    assert (
        _oracle()._is_critical_deadline_violated(
            _node(100.0),
            _candidate(False, 10.0, nav_duration=2.0),
        )
        is False
    )


def test_lit_none_never_violated() -> None:
    """Critical candidates without a logical interaction time stay unpruned."""

    assert (
        _oracle()._is_critical_deadline_violated(_node(100.0), _candidate(True, None))
        is False
    )


def test_positive_interval_critical_uses_nav_reach_time_strictly() -> None:
    """Positive critical intervals prune once nav makes the interaction start late."""

    oracle = _oracle()
    lit = 50.0

    assert (
        oracle._is_critical_deadline_violated(
            _node(lit - 2.0),
            _candidate(True, lit, interval=100.0, nav_duration=2.0),
        )
        is False
    )
    assert (
        oracle._is_critical_deadline_violated(
            _node(lit - 2.0 + 0.1),
            _candidate(True, lit, interval=100.0, nav_duration=2.0),
        )
        is True
    )


def test_zero_interval_critical_wait_within_numeric_epsilon_not_violated() -> None:
    """A consecutive edge tolerates only tiny numeric noise, not semantic wait."""

    oracle = _oracle()
    lit = 20.0

    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + (oracle._strict_timing_epsilon / 2.0)),
            _candidate(True, lit, interval=0.0),
        )
        is False
    )


def test_zero_interval_critical_wait_beyond_numeric_epsilon_violated() -> None:
    """Any positive wait beyond numeric epsilon breaks a consecutive edge."""

    oracle = _oracle()
    lit = 20.0

    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + (oracle._strict_timing_epsilon * 2.0)),
            _candidate(True, lit, interval=0.0),
        )
        is True
    )


def test_late_by_less_than_twelve_point_five_seconds_is_rejected_by_oracle() -> None:
    """Terminal schedules no longer inherit evaluator tolerance for critical edges."""

    oracle = _oracle()
    constraints = nx.DiGraph()
    constraints.add_edge(
        "Start Microwave",
        "Turn Off Microwave",
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = _terminal_state(
        [
            _entry("Start Microwave", 0.0, 20.0),
            _entry("Turn Off Microwave", 115.5, 130.5, nav_time=5.0),
        ],
        constraints,
    )

    assert oracle._is_terminal_schedule_valid(state) is False

    solution = oracle.solve(
        state,
        instruction="demo.json",
        case="tasks_2_constraints_1",
        incumbent_upper_bound=None,
    )

    assert solution.optimal_schedule_time is None
    assert solution.exact is False


def test_zero_interval_terminal_wait_beyond_numeric_epsilon_is_rejected() -> None:
    """Strict terminal validation rejects any scheduled wait on a consecutive edge."""

    oracle = _oracle()
    constraints = nx.DiGraph()
    constraints.add_edge(
        "Predecessor",
        "Successor",
        info={"Interval": 0.0, "IsCritical": True},
    )
    state = _terminal_state(
        [
            _entry("Predecessor", 0.0, 20.0),
            _entry("Successor", 20.01, 25.01, nav_time=3.0),
        ],
        constraints,
    )

    assert oracle._is_terminal_schedule_valid(state) is False


def test_strictly_on_time_terminal_schedule_is_committed() -> None:
    """A schedule that exactly matches planner timing semantics remains valid."""

    oracle = _oracle()
    constraints = nx.DiGraph()
    constraints.add_edge(
        "Start Microwave",
        "Turn Off Microwave",
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = _terminal_state(
        [
            _entry("Start Microwave", 0.0, 20.0),
            _entry("Turn Off Microwave", 115.0, 130.0, nav_time=5.0),
        ],
        constraints,
    )

    assert oracle._is_terminal_schedule_valid(state) is True

    solution = oracle.solve(
        state,
        instruction="demo.json",
        case="tasks_2_constraints_1",
        incumbent_upper_bound=None,
    )

    assert solution.optimal_schedule_time == 130.0
    assert solution.exact is True


def test_external_upper_bound_is_not_treated_as_solution() -> None:
    """An incumbent upper bound should remain a bound until a valid leaf is committed."""

    oracle = _oracle()
    state = _terminal_state([], None)

    solution = oracle.solve(
        state,
        instruction="demo.json",
        case="tasks_2_constraints_1",
        incumbent_upper_bound=123.0,
    )

    assert solution.optimal_schedule_time == 0.0
    assert solution.exact is True
    assert solution.optimal_sequence == []
