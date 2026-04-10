"""Tests for (0, True) consecutive constraint evaluation in calculate_timing_success_rate."""
from __future__ import annotations

import networkx as nx

from src.models.dataclass import CompletedEntry
from src.models.task import Duration, Execution, Subtask
from src.utils.config import constants
from src.utils.io_utils.result_saver import calculate_timing_success_rate


def _subtask(name: str) -> Subtask:
    return Subtask(
        task_name="test_task",
        name=name,
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Stove|1"]),
        duration=Duration(type="Interaction", interval=5.0),
    )


def _make_schedule(
    interval: float,
    is_critical: bool,
    pred_end: float,
    succ_start: float,
    succ_nav: float = 2.0,
):
    """Return (constraints, entries) for a single-edge predecessor→successor schedule."""
    pred = _subtask("PredTask")
    succ = _subtask("SuccTask")
    g = nx.DiGraph()
    g.add_edge(pred.name, succ.name, info={"Interval": interval, "IsCritical": is_critical})
    pred_e = CompletedEntry(
        subtask=pred,
        schedule_start_time=pred_end - 5.0,
        schedule_end_time=pred_end,
        sim_start_time=pred_end - 5.0,
        sim_end_time=pred_end,
    )
    succ_e = CompletedEntry(
        subtask=succ,
        schedule_start_time=succ_start,
        schedule_end_time=succ_start + succ_nav + 5.0,
        schedule_nav_time=succ_nav,
        sim_start_time=succ_start,
        sim_end_time=succ_start + succ_nav + 5.0,
        sim_nav_time=succ_nav,
    )
    return g, [pred_e, succ_e]


# ---------------------------------------------------------------------------
# 상수 존재 확인 (Task 2 검증)
# ---------------------------------------------------------------------------


def test_consecutive_task_wait_tolerance_constant_exists() -> None:
    """CONSECUTIVE_TASK_WAIT_TOLERANCE must be defined in constants."""
    assert hasattr(constants, "CONSECUTIVE_TASK_WAIT_TOLERANCE")


def test_consecutive_task_wait_tolerance_value() -> None:
    """CONSECUTIVE_TASK_WAIT_TOLERANCE must equal 2.0 seconds."""
    assert constants.CONSECUTIVE_TASK_WAIT_TOLERANCE == 2.0


def test_constraint_merge_threshold_constant_exists() -> None:
    """CONSTRAINT_MERGE_THRESHOLD must be defined and equal 6.25."""
    assert hasattr(constants, "CONSTRAINT_MERGE_THRESHOLD")
    assert constants.CONSTRAINT_MERGE_THRESHOLD == 6.25


def test_action_split_precision_constant_exists() -> None:
    """ACTION_SPLIT_PRECISION must be defined and equal 12.5."""
    assert hasattr(constants, "ACTION_SPLIT_PRECISION")
    assert constants.ACTION_SPLIT_PRECISION == 12.5


# ---------------------------------------------------------------------------
# (0, True) constraint — 핵심 실패 테스트 (구현 전 실패, 구현 후 통과)
# ---------------------------------------------------------------------------


def test_zero_critical_wait_exceeds_consecutive_tolerance_fails() -> None:
    """(0,True): wait=3.0s > CONSECUTIVE_TASK_WAIT_TOLERANCE(2.0s) → TSR=0.0.

    Currently FAILS: hardcoded max(5,...) allows 3.0s wait → TSR=1.0.
    After Task 1 fix: uses CONSECUTIVE_TASK_WAIT_TOLERANCE=2.0s → TSR=0.0.
    """
    g, entries = _make_schedule(
        interval=0.0, is_critical=True,
        pred_end=20.0, succ_start=23.0,  # wait_time = succ_start - pred_end = 3.0s
    )
    _, sched_tsr, _ = calculate_timing_success_rate(g, entries)
    assert sched_tsr == 0.0


# ---------------------------------------------------------------------------
# (0, True) constraint — 기준선 테스트 (현재도 통과해야 함)
# ---------------------------------------------------------------------------


def test_zero_critical_immediate_nav_succeeds() -> None:
    """(0,True): wait=0.5s < 2.0s tolerance → TSR=1.0."""
    g, entries = _make_schedule(
        interval=0.0, is_critical=True,
        pred_end=20.0, succ_start=20.5,  # wait_time = 0.5s
    )
    _, sched_tsr, _ = calculate_timing_success_rate(g, entries)
    assert sched_tsr == 1.0


def test_zero_critical_exactly_at_boundary_succeeds() -> None:
    """(0,True): wait == CONSECUTIVE_TASK_WAIT_TOLERANCE exactly → TSR=1.0 (boundary)."""
    g, entries = _make_schedule(
        interval=0.0, is_critical=True,
        pred_end=20.0, succ_start=22.0,  # wait_time = 2.0s == tolerance
    )
    _, sched_tsr, _ = calculate_timing_success_rate(g, entries)
    assert sched_tsr == 1.0


# ---------------------------------------------------------------------------
# (100, True) / (100, False) — 기존 로직 영향 없음 확인
# ---------------------------------------------------------------------------


def test_nonzero_critical_within_tolerance_succeeds() -> None:
    """(100,True): interaction diff == 100s, within TIMING_TOLERANCE_ABS → TSR=1.0."""
    g, entries = _make_schedule(
        interval=100.0, is_critical=True,
        pred_end=20.0, succ_start=115.0, succ_nav=5.0,
        # succ_interaction_start = 115.0 + 5.0 = 120.0, diff = 120.0 - 20.0 = 100.0 ✓
    )
    _, sched_tsr, _ = calculate_timing_success_rate(g, entries)
    assert sched_tsr == 1.0


def test_noncritical_on_time_succeeds() -> None:
    """(100,False): non-critical interval is replaced by INIT_PRIOR_MEAN=140s.
    actual_diff = 130s, (140 - 130) = 10 ≤ TIMING_TOLERANCE_ABS(12.5) → TSR=1.0.
    """
    g, entries = _make_schedule(
        interval=100.0, is_critical=False,
        pred_end=20.0, succ_start=145.0, succ_nav=5.0,
        # succ_interaction = 150.0, actual_diff = 150 - 20 = 130, (140 - 130) = 10 ≤ 12.5 ✓
    )
    _, sched_tsr, _ = calculate_timing_success_rate(g, entries)
    assert sched_tsr == 1.0
