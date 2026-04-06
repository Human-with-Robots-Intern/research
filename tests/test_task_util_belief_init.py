"""Tests for TaskUtil belief initialization semantics."""

from __future__ import annotations

from src.models.task import TemporalConstraint
from src.utils.config import constants
from src.utils.task.task_util import TaskUtil


def test_zero_interval_critical_edge_keeps_object_prior_non_zero() -> None:
    """A critical zero-interval edge should not seed an object prior with zero."""

    bayesian_load: dict[str, dict[str, float]] = {}
    temporal_constraint = TemporalConstraint(
        constraint_type="After",
        rel_subtask_name="Start Microwave for Heating Potato",
        interval=0.0,
        is_critical=True,
    )

    TaskUtil._update_constraint_belief(
        "Microwave",
        temporal_constraint,
        bayesian_load,
    )

    assert bayesian_load["Microwave"]["expected_duration"] == constants.INIT_PRIOR_MEAN
    assert bayesian_load["Microwave"]["variance"] == constants.INIT_PRIOR_VARIANCE
    assert temporal_constraint.interval == 0.0


def test_non_zero_critical_edge_upgrades_existing_zero_prior() -> None:
    """A later positive critical interval should restore a zeroed object prior."""

    bayesian_load = {
        "Microwave": {
            "expected_duration": 0.0,
            "variance": constants.INIT_PRIOR_VARIANCE,
        }
    }
    temporal_constraint = TemporalConstraint(
        constraint_type="After",
        rel_subtask_name="Turn Off Microwave after Heating Potato",
        interval=100.0,
        is_critical=True,
    )

    TaskUtil._update_constraint_belief(
        "Microwave",
        temporal_constraint,
        bayesian_load,
    )

    assert bayesian_load["Microwave"]["expected_duration"] == constants.INIT_PRIOR_MEAN
    assert temporal_constraint.interval == constants.INIT_PRIOR_MEAN
