"""Tests for the standalone oracle reference CLI and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.offline.offline_oracle_reference import build_config, parse_args
from src.experiments.offline_harness import ExperimentConfig, run_grid_experiment
from src.experiments.offline_oracle_reference import (
    build_oracle_reference_output_path,
    build_oracle_task_key,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_oracle_reference_cli_accepts_reference_dir() -> None:
    """Parse oracle reference CLI flags without baseline-only arguments."""

    args = parse_args(
        [
            "--task-folder-name",
            "sampled_10_instruction_set_for_final_experiment_251203",
            "--case",
            "tasks_3_constraints_2",
            "--scene",
            "FloorPlan13",
            "--instruction",
            "task_a.json",
            "--oracle-reference-dir",
            "assets/results/offline_oracle_reference",
            "--oracle-time-limit-seconds",
            "300",
        ]
    )

    assert args.oracle_reference_dir == "assets/results/offline_oracle_reference"
    assert args.oracle_time_limit_seconds == 300.0
    assert args.instructions == ["task_a.json"]


def test_build_oracle_reference_config_uses_new_fields(tmp_path: Path) -> None:
    """Build the oracle reference config from file defaults and CLI overrides."""

    config_path = tmp_path / "oracle.yaml"
    config_path.write_text(
        "\n".join(
            [
                "scene: FloorPlan13",
                "oracle_reference_dir: assets/results/offline_oracle_reference",
                "oracle_time_limit_seconds: 120",
            ]
        ),
        encoding="utf-8",
    )

    args = parse_args(
        [
            "--config",
            str(config_path),
            "--case",
            "tasks_3_constraints_2",
            "--instruction",
            "task_a.json",
            "--oracle-time-limit-seconds",
            "300",
        ]
    )

    config = build_config(args)

    assert config.case == "tasks_3_constraints_2"
    assert config.instructions == ["task_a.json"]
    assert config.oracle_time_limit_seconds == 300
    assert config.oracle_reference_dir == "assets/results/offline_oracle_reference"


def test_run_grid_experiment_embeds_oracle_reference_comparison(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Embed loaded oracle references into the baseline report."""

    reference_dir = tmp_path / "oracle_refs"
    reference_path = build_oracle_reference_output_path(
        reference_dir,
        task_folder_name="sampled_10_instruction_set_for_final_experiment_251203",
        scene_name="FloorPlan13",
        case_name="tasks_3_constraints_2",
        instruction_name="task_a.json",
    )
    assert reference_path.parts[-4:] == (
        "sampled_10_instruction_set_for_final_experiment_251203",
        "FloorPlan13",
        "tasks_3_constraints_2",
        "task_a.json",
    )
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(
        "\n".join(
            [
                "{",
                '  "case": "tasks_3_constraints_2",',
                '  "instruction": "task_a.json",',
                '  "optimal_schedule_time": 8.0,',
                '  "optimal_sequence": ["A"],',
                '  "solve_time": 0.2,',
                '  "search_nodes": 5,',
                '  "pruned_nodes": 2,',
                '  "idle_advances": 0,',
                '  "exact": true,',
                '  "timeout_hit": false',
                "}",
            ]
        ),
        encoding="utf-8",
    )

    config = ExperimentConfig(
        instructions=["task_a.json"],
        beam_bound=[(1, 1)],
        oracle_reference_dir=str(reference_dir),
    )

    monkeypatch.setattr(
        "src.experiments.offline_harness.load_scene_positions",
        lambda _name: {"agent": (0.0, 0.9, 0.0), "obj": (0.25, 0.9, 0.25)},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.run_single_rollout",
        lambda cfg, task, **_: {
            "case": task.case or cfg.case,
            "instruction": task.instruction,
            "beam_width": task.beam_width,
            "beam_depth": task.beam_depth,
            "completed": True,
            "abort_reason": "",
            "total_compute_time": 1.0,
            "final_schedule_time": 10.0,
            "schedule_tcsr": 1.0,
            "action_count": 1,
            "wait_count": 0,
            "monitor_count": 0,
            "replanning_count": 1,
            "avg_committed_steps_per_replan": 1.0,
            "steps": [],
            "timing_detail": {},
            "ground_truth_intervals": {"Microwave": 100.0},
        },
    )

    report = run_grid_experiment(config)

    task_key = build_oracle_task_key("tasks_3_constraints_2", "task_a.json")
    assert report["oracle_comparison"]["coverage"]["matched_instructions"] == 1
    assert report["oracle_comparison"]["best_by_task"][task_key]["absolute_gap"] == 2.0
