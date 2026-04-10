"""Tests for DeterministicExactOracle._is_critical_deadline_violated.

Verifies that:
- Non-critical candidates are never pruned.
- Candidates with no LIT are never pruned.
- interval > 0 candidates use TIMING_TOLERANCE_ABS.
- interval == 0 (consecutive) candidates use the stricter CONSECUTIVE_TASK_WAIT_TOLERANCE.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.experiments.exact_oracle import DeterministicExactOracle
from src.models.dataclass import CriticalContext
from src.utils.config import constants


def _oracle() -> DeterministicExactOracle:
    with patch("src.experiments.exact_oracle.Scheduler"):
        return DeterministicExactOracle(
            action_handler=MagicMock(),
            constraint_handler=MagicMock(),
            heuristic_manager=MagicMock(),
            time_limit_seconds=30.0,
        )


def _node(current_time: float):
    n = MagicMock()
    n.state.current_time = current_time
    return n


def _candidate(is_critical: bool, lit: float | None, interval: float = 100.0):
    c = MagicMock()
    c.is_critical = is_critical
    c.logical_interaction_start_time = lit
    c.critical_context = (
        CriticalContext(
            source_subtask=None,
            source_end_time=None,
            interval=interval,
            logical_start_time=lit,
        )
        if lit is not None
        else None
    )
    return c


# ---------------------------------------------------------------------------
# Edge cases — always False
# ---------------------------------------------------------------------------


def test_not_critical_never_violated() -> None:
    """Non-critical candidate is never pruned regardless of timing."""
    assert (
        _oracle()._is_critical_deadline_violated(_node(100.0), _candidate(False, 10.0))
        is False
    )


def test_lit_none_never_violated() -> None:
    """Critical candidate without LIT is never pruned."""
    assert (
        _oracle()._is_critical_deadline_violated(_node(100.0), _candidate(True, None))
        is False
    )


# ---------------------------------------------------------------------------
# interval > 0: uses TIMING_TOLERANCE_ABS (12.5s)
# ---------------------------------------------------------------------------


def test_nonzero_critical_within_timing_tolerance_not_violated() -> None:
    """current_time = lit + TIMING_TOLERANCE_ABS - 0.1 → not violated."""
    lit = 50.0
    oracle = _oracle()
    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + constants.TIMING_TOLERANCE_ABS - 0.1),
            _candidate(True, lit, interval=100.0),
        )
        is False
    )


def test_nonzero_critical_exceeds_timing_tolerance_violated() -> None:
    """current_time = lit + TIMING_TOLERANCE_ABS + 0.1 → violated."""
    lit = 50.0
    oracle = _oracle()
    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + constants.TIMING_TOLERANCE_ABS + 0.1),
            _candidate(True, lit, interval=100.0),
        )
        is True
    )


# ---------------------------------------------------------------------------
# interval == 0 (consecutive): uses CONSECUTIVE_TASK_WAIT_TOLERANCE (2.0s)
# ---------------------------------------------------------------------------


def test_zero_interval_critical_wait_within_consecutive_tolerance_not_violated() -> None:
    """(0,True): wait=1.5s ≤ CONSECUTIVE_TASK_WAIT_TOLERANCE(2.0s) → not violated."""
    lit = 20.0
    oracle = _oracle()
    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + 1.5),
            _candidate(True, lit, interval=0.0),
        )
        is False
    )


def test_zero_interval_critical_exceeds_consecutive_tolerance_violated() -> None:
    """(0,True): wait > 2.0s but < 12.5s → VIOLATED (stricter threshold).

    Currently FAILS: uses TIMING_TOLERANCE_ABS=12.5 → not violated (returns False).
    After Task 1 fix: uses CONSECUTIVE_TASK_WAIT_TOLERANCE=2.0 → violated (returns True).
    """
    lit = 20.0
    oracle = _oracle()
    # wait = CONSECUTIVE_TASK_WAIT_TOLERANCE + 0.1 = 2.1s
    # 2.1 > 2.0 (CONSECUTIVE_TASK_WAIT_TOLERANCE) → violated
    # 2.1 < 12.5 (TIMING_TOLERANCE_ABS) → would NOT be violated without fix
    assert (
        oracle._is_critical_deadline_violated(
            _node(lit + constants.CONSECUTIVE_TASK_WAIT_TOLERANCE + 0.1),
            _candidate(True, lit, interval=0.0),
        )
        is True
    )
