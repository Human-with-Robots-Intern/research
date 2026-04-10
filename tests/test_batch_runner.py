"""Tests for offline batch runner key normalization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.experiments.batch_runner import (
    _build_offline_options,
    build_offline_batch_summary_path,
    build_offline_tasks,
    build_oracle_reference_tasks,
    write_batch_summary,
)
from src.experiments.offline_oracle_reference import build_oracle_reference_output_path

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_build_offline_options_reads_run_all_style_keys() -> None:
    """Normalize the offline batch config from the new top-level key schema."""

    config: dict[str, Any] = {
        "approaches": ["bayesian", "oracle"],
        "scene_type": ["kitchen"],
        "scene_lists": {
            "kitchen": ["FloorPlan13", "FloorPlan18"],
            "bathroom": [],
            "real_world": [],
        },
        "ablation_configs": ["DEFAULT", "NONE_MONITORING"],
        "init_prior_configs": ["OVER_ESTIMATE_110"],
        "task_folder_name": ["sampled_10_instruction_set_for_final_experiment_251203"],
        "cases": ["tasks_3_constraints_2"],
        "max_tasks": 3,
        "beam_bound": [[1, 1], [5, 5]],
        "eta": 0.25,
        "nav_graph_source": "ai2thor_controller",
        "oracle_time_limit_seconds": 300,
        "output_dir": "assets/results/offline_batch",
    }

    options = _build_offline_options(config)

    assert options.approaches == ["bayesian"]
    assert options.scenes == ["FloorPlan13", "FloorPlan18"]
    assert options.ablation_configs == ["DEFAULT", "NONE_MONITORING"]
    assert options.init_prior_configs == ["OVER_ESTIMATE_110"]
    assert options.beam_bound == [(1, 1), (5, 5)]
    assert options.etas == [0.25]
    assert options.nav_graph_source == "ai2thor_controller"
    assert options.oracle_time_limit_seconds == 300


def test_build_offline_tasks_uses_new_cli_surface(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Emit subprocess commands using only the new offline CLI flags."""

    monkeypatch.setattr(
        "src.experiments.batch_runner.resolve_instructions",
        lambda _config, _case_name: ["task_a.json"],
    )

    config: dict[str, Any] = {
        "approaches": ["bayesian"],
        "scene_type": ["kitchen"],
        "scene_lists": {
            "kitchen": ["FloorPlan13"],
            "bathroom": [],
            "real_world": [],
        },
        "ablation_configs": ["NONE_MONITORING"],
        "init_prior_configs": ["OVER_ESTIMATE_110"],
        "task_folder_name": ["sampled_10_instruction_set_for_final_experiment_251203"],
        "cases": ["tasks_3_constraints_2"],
        "beam_bound": [[1, 1], [5, 5]],
        "eta": 0.4,
        "nav_graph_source": "ai2thor_controller",
        "oracle_time_limit_seconds": 300,
        "output_dir": str(tmp_path),
        "skip_completed": False,
    }

    tasks = build_offline_tasks(
        config,
        run_timestamp="20260409_1200",
        logger=logging.getLogger("test_batch_runner"),
    )

    assert len(tasks) == 2
    command = tasks[0].command

    assert "--approach" in command
    assert "bayesian" in command
    assert "--ablation-config" in command
    assert "NONE_MONITORING" in command
    assert "--init-prior-config" in command
    assert "OVER_ESTIMATE_110" in command
    assert "--beam-bound" in command
    beam_bound_index = command.index("--beam-bound")
    assert command[beam_bound_index + 1 : beam_bound_index + 2] == ["1,1"]
    # NONE_MONITORING ablation: eta sweep does not apply, so --eta is not emitted
    assert "--eta" not in command
    assert "--nav-graph-source" in command
    assert "ai2thor_controller" in command
    assert "--oracle-time-limit-seconds" in command
    assert "300" in command

    output_path = Path(command[command.index("--output-path") + 1])
    assert output_path.parts[-5:] == (
        "sampled_10_instruction_set_for_final_experiment_251203",
        "FloorPlan13",
        "tasks_3_constraints_2",
        "task_a",
        "bayesian__NONE_MONITORING__OVER_ESTIMATE_110__w1_d1.json",
    )
    assert tasks[0].metadata["output_path"] == str(output_path)
    assert "output_path=" in tasks[0].summary()
    assert tasks[0].metadata["beam_width"] == 1
    assert tasks[0].metadata["beam_depth"] == 1

    assert "--planner-type" not in command
    assert "--beam-width-values" not in command
    assert "--beam-depth-values" not in command
    assert "--bayesian-threshold-probability" not in command
    assert "--disable-monitoring" not in command
    assert "--init-prior-mean" not in command
    assert "--init-prior-variance" not in command


def test_build_offline_tasks_collapses_baseline_beams(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Emit only one default-ablation task per baseline approach."""

    monkeypatch.setattr(
        "src.experiments.batch_runner.resolve_instructions",
        lambda _config, _case_name: ["task_a.json"],
    )

    config: dict[str, Any] = {
        "approaches": ["edf", "cpm"],
        "scene_type": ["kitchen"],
        "scene_lists": {
            "kitchen": ["FloorPlan13"],
            "bathroom": [],
            "real_world": [],
        },
        "ablation_configs": ["DEFAULT", "NONE_MONITORING"],
        "init_prior_configs": ["OVER_ESTIMATE_110"],
        "task_folder_name": ["sampled_10_instruction_set_for_final_experiment_251203"],
        "cases": ["tasks_3_constraints_2"],
        "beam_bound": [[1, 1], [5, 5]],
        "nav_graph_source": "ai2thor_controller",
        "oracle_time_limit_seconds": 300,
        "output_dir": str(tmp_path),
        "skip_completed": False,
    }

    tasks = build_offline_tasks(
        config,
        run_timestamp="20260409_1200",
        logger=logging.getLogger("test_batch_runner_baseline"),
    )

    assert len(tasks) == 2
    assert {task.metadata["approach"] for task in tasks} == {"edf", "cpm"}

    for task in tasks:
        command = task.command
        assert "NONE_MONITORING" not in command
        ablation_index = command.index("--ablation-config")
        assert command[ablation_index + 1] == "DEFAULT"
        beam_bound_index = command.index("--beam-bound")
        assert command[beam_bound_index + 1 : beam_bound_index + 2] == ["1,1"]
        output_path = Path(command[command.index("--output-path") + 1])
        assert output_path.name == (
            f"{task.metadata['approach']}__DEFAULT__OVER_ESTIMATE_110.json"
        )
        assert "__w1_d1" not in output_path.name
        assert "__w5_d5" not in output_path.name
        assert "__w1_d1" not in task.log_path.name
        assert "__w5_d5" not in task.log_path.name
        assert ":w1:d1:" not in task.name
        assert task.metadata["ablation_config"] == "DEFAULT"
        assert task.metadata["beam_width"] == 1
        assert task.metadata["beam_depth"] == 1


def test_build_oracle_reference_tasks_uses_separate_script(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Generate oracle references via the dedicated batch path."""

    monkeypatch.setattr(
        "src.experiments.batch_runner.resolve_instructions",
        lambda _config, _case_name: ["task_a.json"],
    )

    config: dict[str, Any] = {
        "scene_type": ["kitchen"],
        "scene_lists": {
            "kitchen": ["FloorPlan13"],
            "bathroom": [],
            "real_world": [],
        },
        "task_folder_name": ["sampled_10_instruction_set_for_final_experiment_251203"],
        "cases": ["tasks_3_constraints_2"],
        "nav_graph_source": "ai2thor_controller",
        "oracle_time_limit_seconds": 300,
        "oracle_reference_dir": str(tmp_path),
        "skip_completed": False,
    }

    tasks = build_oracle_reference_tasks(
        config,
        run_timestamp="20260409_1200",
        logger=logging.getLogger("test_batch_runner"),
    )

    assert len(tasks) == 1
    command = tasks[0].command

    assert command[1].endswith("offline_oracle_reference.py")
    assert "--oracle-reference-dir" in command
    assert str(tmp_path) in command
    assert "--instruction" in command
    assert "task_a.json" in command

    output_path = build_oracle_reference_output_path(
        tmp_path,
        task_folder_name="sampled_10_instruction_set_for_final_experiment_251203",
        scene_name="FloorPlan13",
        case_name="tasks_3_constraints_2",
        instruction_name="task_a.json",
    )
    assert output_path.parts[-4:] == (
        "sampled_10_instruction_set_for_final_experiment_251203",
        "FloorPlan13",
        "tasks_3_constraints_2",
        "task_a.json",
    )
    assert tasks[0].metadata["output_path"] == str(output_path)
    assert "output_path=" in tasks[0].summary()


def test_write_batch_summary_creates_separate_summary_file(tmp_path: Path) -> None:
    """Persist a lightweight batch summary separately from result variants."""

    summary_path = build_offline_batch_summary_path(
        {"output_dir": str(tmp_path / "offline_batch")},
        run_timestamp="20260409_1200",
    )
    write_batch_summary(
        [
            type("TaskLike", (), {
                "name": "offline-run:test",
                "metadata": {
                    "mode": "offline",
                    "output_path": str(tmp_path / "offline_batch" / "result.json"),
                },
            })()
        ],
        summary_path=summary_path,
        run_timestamp="20260409_1200",
        mode="offline",
    )

    assert summary_path.exists()
    payload = summary_path.read_text(encoding="utf-8")
    assert "offline_batch_summary.v1" in payload
