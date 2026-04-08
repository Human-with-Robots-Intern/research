"""Tests for the offline in-process experiment harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.experiments.offline_compare import compare_result_files
from src.experiments.offline_harness import (
    ExperimentConfig,
    ExperimentTask,
    apply_cli_overrides,
    build_experiment_tasks,
    load_experiment_config,
    run_grid_experiment,
    save_experiment_report,
    summarize_results,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_load_experiment_config_and_cli_override(tmp_path: Path) -> None:
    """Config loader should merge YAML defaults with CLI overrides."""

    config_path = tmp_path / "offline.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: baseline",
                "scene: FloorPlan1",
                "beam_width_values: [1, 3]",
                "disable_monitoring: false",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_experiment_config(config_path)
    merged = apply_cli_overrides(
        loaded,
        {
            "scene": "FloorPlan2",
            "disable_monitoring": True,
            "beam_depth_values": [2, 4],
        },
    )

    assert loaded.experiment_name == "baseline"
    assert merged.scene == "FloorPlan2"
    assert merged.disable_monitoring is True
    assert merged.beam_width_values == [1, 3]
    assert merged.beam_depth_values == [2, 4]


def test_build_experiment_tasks_expands_instruction_and_beam_grid() -> None:
    """Task builder should emit the cartesian product over instructions and beams."""

    config = ExperimentConfig(
        instructions=["a.json", "b.json"],
        beam_width_values=[1, 5],
        beam_depth_values=[1, 3],
    )

    tasks = build_experiment_tasks(config)

    assert len(tasks) == 8
    assert tasks[0] == ExperimentTask("a.json", 1, 1, 0)
    assert tasks[-1] == ExperimentTask("b.json", 5, 3, 1)


def test_summarize_results_outputs_setting_metrics() -> None:
    """Summary aggregation should compute per-setting averages."""

    results = [
        {
            "instruction": "a.json",
            "beam_width": 1,
            "beam_depth": 1,
            "completed": True,
            "total_compute_time": 2.0,
            "final_schedule_time": 10.0,
            "schedule_tcsr": 0.5,
            "wait_count": 1,
            "monitor_count": 0,
        },
        {
            "instruction": "b.json",
            "beam_width": 1,
            "beam_depth": 1,
            "completed": True,
            "total_compute_time": 4.0,
            "final_schedule_time": 14.0,
            "schedule_tcsr": 1.0,
            "wait_count": 3,
            "monitor_count": 1,
        },
    ]

    summary = summarize_results(results)

    assert summary["w1_d1"]["completed_runs"] == 2
    assert summary["w1_d1"]["avg_schedule_time"] == 12.0
    assert summary["w1_d1"]["avg_compute_time"] == 3.0
    assert summary["w1_d1"]["avg_schedule_tcsr"] == 0.75
    assert summary["w1_d1"]["avg_wait_count"] == 2
    assert summary["w1_d1"]["avg_monitor_count"] == 0.5


def test_run_grid_experiment_returns_schema_and_writes_report(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Grid runner should assemble the standardized report schema."""

    config = ExperimentConfig(
        experiment_name="test-grid",
        instructions=["task_a.json", "task_b.json"],
        beam_width_values=[1],
        beam_depth_values=[1, 2],
        output_path=str(tmp_path / "report.json"),
    )

    monkeypatch.setattr(
        "src.experiments.offline_harness.load_scene_positions",
        lambda _: {"agent": (0.0, 0.9, 0.0), "obj": (0.25, 0.9, 0.25)},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.run_single_rollout",
        lambda cfg, task, **_: {
            "instruction": task.instruction,
            "beam_width": task.beam_width,
            "beam_depth": task.beam_depth,
            "completed": True,
            "abort_reason": "",
            "total_compute_time": float(task.beam_depth),
            "final_schedule_time": float(task.beam_width + task.beam_depth),
            "schedule_tcsr": 1.0,
            "action_count": 1,
            "wait_count": 0,
            "monitor_count": 0,
            "steps": [],
            "timing_detail": {},
            "ground_truth_intervals": {"Microwave": 100.0},
        },
    )

    report = run_grid_experiment(config)
    save_experiment_report(report, Path(config.output_path))
    saved_report = json.loads(Path(config.output_path).read_text(encoding="utf-8"))

    assert report["schema_version"] == config.schema_version
    assert report["experiment"]["name"] == "test-grid"
    assert len(report["results"]) == 4
    assert "w1_d1" in report["summary_by_setting"]
    assert "best_by_task" in report["comparison"]
    assert saved_report["config"]["experiment_name"] == "test-grid"


def test_compare_result_files_calculates_setting_and_task_deltas(
    tmp_path: Path,
) -> None:
    """Comparison report should expose setting and task deltas."""

    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_payload: dict[str, Any] = {
        "summary_by_setting": {
            "w1_d1": {"avg_schedule_time": 10.0, "avg_compute_time": 2.0},
            "w5_d5": {"avg_schedule_time": 20.0, "avg_compute_time": 5.0},
        },
        "comparison": {
            "best_by_task": {
                "a.json": {"final_schedule_time": 10.0},
                "b.json": {"final_schedule_time": 20.0},
            }
        },
    }
    after_payload: dict[str, Any] = {
        "summary_by_setting": {
            "w1_d1": {"avg_schedule_time": 8.0, "avg_compute_time": 3.0},
            "w5_d5": {"avg_schedule_time": 22.0, "avg_compute_time": 4.0},
        },
        "comparison": {
            "best_by_task": {
                "a.json": {"final_schedule_time": 8.0},
                "b.json": {"final_schedule_time": 21.0},
            }
        },
    }
    before_path.write_text(json.dumps(before_payload), encoding="utf-8")
    after_path.write_text(json.dumps(after_payload), encoding="utf-8")

    comparison = compare_result_files(before_path, after_path)

    assert comparison["setting_deltas"]["w1_d1"]["schedule_time_delta"] == -2.0
    assert comparison["setting_deltas"]["w5_d5"]["compute_time_delta"] == -1.0
    assert comparison["task_best_deltas"]["a.json"]["best_schedule_delta"] == -2.0
    assert comparison["improved_settings"] == ["w1_d1"]
    assert comparison["regressed_settings"] == ["w5_d5"]
