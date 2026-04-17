"""Tests for offline comparison loading under the new prior-aware layout."""

from __future__ import annotations

import json
from pathlib import Path

from assets.result_analysis.offline_comparison import (
    aggregate,
    build_approach_key,
    build_raw,
    build_tol_sweep,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_approach_key_uses_init_prior_and_baseline_name() -> None:
    """Canonical analysis keys should keep init_prior as a top-level axis."""

    bayesian_meta = {
        "baseline_name": "bayesian",
        "ablation_config": "DEFAULT",
        "init_prior_config": "UNDER_ESTIMATE",
        "beam_width": 10,
        "beam_depth": 10,
        "eta": 0.1,
        "gt_distribution": "lognormal",
        "monitoring_budget_per_critical": "2",
    }
    assert build_approach_key("ignored", bayesian_meta) == (
        "UNDER_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtlognormal__mb2"
    )

    pf_meta = {
        "baseline_name": "particle_filter",
        "ablation_config": "DEFAULT",
        "init_prior_config": "OVER_ESTIMATE",
        "beam_width": 10,
        "beam_depth": 10,
        "eta": 0.1,
        "gt_distribution": "mixture",
        "particle_distribution": "gaussian",
    }
    assert build_approach_key("ignored", pf_meta) == (
        "OVER_ESTIMATE__particle_filter__DEFAULT__w10_d10"
        "__eta0.1__gtmixture__pdistgaussian"
    )

    assert build_approach_key(
        "ignored",
        {
            "baseline_name": "edf",
            "init_prior_config": "CORRECT_ESTIMATE",
        },
    ) == "CORRECT_ESTIMATE__edf"


def test_build_raw_reads_prior_and_baseline_directories(tmp_path: Path) -> None:
    """Result discovery should traverse init_prior/baseline subdirectories."""

    task_folder = "sampled_10_instruction_set_for_final_experiment_251203"
    scene = "FloorPlan27"
    case = "tasks_3_constraints_2"
    instruction = "10_make_a_coffee_and_cook_egg_and_wash_a_tomato"

    oracle_path = (
        tmp_path
        / "offline_oracle_reference"
        / task_folder
        / scene
        / case
        / f"{instruction}.json"
    )
    _write_json(
        oracle_path,
        {
            "optimal_schedule_time": 100.0,
            "computation_time": 2.5,
            "exact": True,
            "steps": [],
        },
    )

    bayesian_path = (
        tmp_path
        / "offline_batch_pf_vs_bayesian"
        / task_folder
        / "CORRECT_ESTIMATE"
        / scene
        / case
        / instruction
        / "bayesian"
        / "DEFAULT__w10_d10__eta0.1__gtlognormal.json"
    )
    _write_json(
        bayesian_path,
        {
            "scene_name": scene,
            "case": case,
            "instruction": f"{instruction}.json",
            "completed": True,
            "timing_success_rate_sched": 0.75,
            "scheduler_makespan": 110.0,
            "computation_time": 3.2,
            "detail_log": {},
            "meta_data": {
                "baseline_name": "bayesian",
                "ablation_config": "DEFAULT",
                "init_prior_config": "CORRECT_ESTIMATE",
                "beam_width": 10,
                "beam_depth": 10,
                "eta": 0.1,
                "gt_distribution": "lognormal",
                "belief_update_method": "bayesian",
            },
        },
    )

    pf_path = (
        tmp_path
        / "offline_batch_pf_vs_bayesian"
        / task_folder
        / "UNDER_ESTIMATE"
        / scene
        / case
        / instruction
        / "particle_filter"
        / "DEFAULT__w10_d10__eta0.1__gtlognormal__pdistgaussian.json"
    )
    _write_json(
        pf_path,
        {
            "scene_name": scene,
            "case": case,
            "instruction": f"{instruction}.json",
            "completed": False,
            "timing_success_rate_sched": 0.5,
            "scheduler_makespan": 125.0,
            "computation_time": 4.8,
            "detail_log": {},
            "meta_data": {
                "baseline_name": "particle_filter",
                "ablation_config": "DEFAULT",
                "init_prior_config": "UNDER_ESTIMATE",
                "beam_width": 10,
                "beam_depth": 10,
                "eta": 0.1,
                "gt_distribution": "lognormal",
                "particle_distribution": "gaussian",
                "belief_update_method": "particle_filter",
            },
        },
    )

    raw = build_raw(
        tmp_path,
        task_folder,
        batch_dirname="offline_batch_pf_vs_bayesian",
        oracle_dirname="offline_oracle_reference",
    )

    entry = raw[scene][case][instruction]
    assert entry["oracle"]["optimal_schedule_time"] == 100.0
    assert (
        entry["CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtlognormal"][
            "makespan_gap"
        ]
        == 10.0
    )
    assert (
        entry[
            "UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1"
            "__gtlognormal__pdistgaussian"
        ]["completed"]
        is False
    )


def test_build_tol_sweep_reads_new_layout(tmp_path: Path) -> None:
    """Tolerance sweep should aggregate results found under prior/baseline folders."""

    task_folder = "sampled_10_instruction_set_for_final_experiment_251203"
    scene = "FloorPlan27"
    case = "tasks_3_constraints_2"
    instruction = "10_make_a_coffee_and_cook_egg_and_wash_a_tomato"

    batch_path = (
        tmp_path
        / "offline_batch_pf_vs_bayesian"
        / task_folder
        / "OVER_ESTIMATE"
        / scene
        / case
        / instruction
        / "particle_filter"
        / "DEFAULT__w10_d10__eta0.1__gtmixture.json"
    )
    _write_json(
        batch_path,
        {
            "scene_name": scene,
            "case": case,
            "instruction": f"{instruction}.json",
            "completed": True,
            "timing_success_rate_sched": 1.0,
            "scheduler_makespan": 123.0,
            "computation_time": 5.0,
            "detail_log": {
                "a -> b": {
                    "Original Timing Constraint": "(100.0, True)",
                    "Schedule Result": "[True] : (0.00) -> (100.00s)",
                }
            },
            "meta_data": {
                "baseline_name": "particle_filter",
                "ablation_config": "DEFAULT",
                "init_prior_config": "OVER_ESTIMATE",
                "beam_width": 10,
                "beam_depth": 10,
                "eta": 0.1,
                "gt_distribution": "mixture",
                "belief_update_method": "particle_filter",
            },
        },
    )

    tol_sweep = build_tol_sweep(
        tmp_path,
        task_folder,
        [30.0],
        batch_dirname="offline_batch_pf_vs_bayesian",
    )

    assert tol_sweep["30.0"] == {
        "OVER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtmixture": {
            case: {
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 123.0,
            }
        }
    }


def test_aggregate_includes_instruction_counts_for_summary_schema() -> None:
    """Aggregated summaries should expose n_instructions for downstream tables."""

    raw = {
        "FloorPlan1": {
            "tasks_2_constraints_1": {
                "inst_a": {
                    "oracle": {"optimal_schedule_time": 10.0},
                    "oracle_valid": True,
                    "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1": {
                        "completed": True,
                        "tsr": 1.0,
                        "makespan": 12.0,
                        "makespan_gap": 2.0,
                        "computation_time": 0.5,
                        "computation_time_gap": 0.1,
                    },
                },
                "inst_b": {
                    "oracle": {"optimal_schedule_time": 10.0},
                    "oracle_valid": True,
                    "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1": {
                        "completed": False,
                        "tsr": 0.5,
                        "makespan": 14.0,
                        "makespan_gap": 4.0,
                        "computation_time": 0.7,
                        "computation_time_gap": 0.2,
                    },
                },
            }
        }
    }

    summary = aggregate(raw)

    assert summary["CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1"][
        "tasks_2_constraints_1"
    ]["n_instructions"] == 2
