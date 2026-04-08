"""Tests for the offline in-process experiment harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.monitoring import BeliefUpdateContext, create_observation_model
from src.experiments.exact_oracle import DeterministicExactOracle
from src.experiments.offline_compare import compare_result_files
from src.experiments.offline_harness import (
    ExperimentConfig,
    ExperimentTask,
    apply_cli_overrides,
    build_experiment_tasks,
    load_experiment_config,
    run_oracle_comparison_experiment,
    run_grid_experiment,
    run_single_rollout,
    save_experiment_report,
    summarize_results,
)
from src.models.dataclass import Candidate, CompletedEntry, SchedulerState, SimulationNode
from src.models.task import Duration, Execution, Subtask
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager

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
                "planner_type: bayesian",
                "beam_width_values: [1, 3]",
                "disable_monitoring: false",
                "nav_graph_source: synthetic_grid",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_experiment_config(config_path)
    merged = apply_cli_overrides(
        loaded,
        {
            "scene": "FloorPlan2",
            "planner_type": "edf",
            "disable_monitoring": True,
            "beam_depth_values": [2, 4],
            "nav_graph_source": "ai2thor_controller",
        },
    )

    assert loaded.experiment_name == "baseline"
    assert merged.scene == "FloorPlan2"
    assert merged.planner_type == "edf"
    assert merged.disable_monitoring is True
    assert merged.beam_width_values == [1, 3]
    assert merged.beam_depth_values == [2, 4]
    assert merged.nav_graph_source == "ai2thor_controller"


def test_build_experiment_tasks_expands_instruction_and_beam_grid() -> None:
    """Task builder should emit the cartesian product over instructions and beams."""

    config = ExperimentConfig(
        instructions=["a.json", "b.json"],
        beam_width_values=[1, 5],
        beam_depth_values=[1, 3],
    )

    tasks = build_experiment_tasks(config)

    assert len(tasks) == 8
    assert tasks[0] == ExperimentTask("a.json", 1, 1, 0, "tasks_3_constraints_2")
    assert tasks[-1] == ExperimentTask("b.json", 5, 3, 1, "tasks_3_constraints_2")


def test_build_experiment_tasks_supports_multiple_cases() -> None:
    """Task builder should expand instructions across all requested cases."""

    config = ExperimentConfig(
        cases=["tasks_2_constraints_1", "tasks_3_constraints_1"],
        instructions=["a.json"],
        beam_width_values=[1],
        beam_depth_values=[1],
    )

    tasks = build_experiment_tasks(config)

    assert tasks == [
        ExperimentTask("a.json", 1, 1, 0, "tasks_2_constraints_1"),
        ExperimentTask("a.json", 1, 1, 0, "tasks_3_constraints_1"),
    ]


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
            "replanning_count": 4,
            "avg_committed_steps_per_replan": 1.0,
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
            "replanning_count": 2,
            "avg_committed_steps_per_replan": 1.5,
        },
    ]

    summary = summarize_results(results)

    assert summary["w1_d1"]["completed_runs"] == 2
    assert summary["w1_d1"]["avg_schedule_time"] == 12.0
    assert summary["w1_d1"]["avg_compute_time"] == 3.0
    assert summary["w1_d1"]["avg_schedule_tcsr"] == 0.75
    assert summary["w1_d1"]["avg_wait_count"] == 2
    assert summary["w1_d1"]["avg_monitor_count"] == 0.5
    assert summary["w1_d1"]["avg_replanning_count"] == 3
    assert summary["w1_d1"]["avg_committed_steps_per_replan"] == 1.25


def test_create_observation_model_uses_seed_for_synthetic_mode() -> None:
    """Synthetic observation backend should be reproducible with a fixed seed."""

    context = BeliefUpdateContext(
        object_name="Microwave",
        gt_interval=100.0,
        prior_mean=140.0,
        prior_variance=900.0,
        elapsed_interval=80.0,
    )
    model_a = create_observation_model("synthetic_gaussian", random_seed=7)
    model_b = create_observation_model("synthetic_gaussian", random_seed=7)

    observation_a = model_a.observe(context)
    observation_b = model_b.observe(context)

    assert observation_a.observation == observation_b.observation
    assert observation_a.variance == observation_b.variance


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
            "case": task.case or cfg.case,
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
            "replanning_count": 1,
            "avg_committed_steps_per_replan": 1.0,
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
    assert "tasks_3_constraints_2:w1_d1" in report["summary_by_case_setting"]
    assert "best_by_task" in report["comparison"]
    assert saved_report["config"]["experiment_name"] == "test-grid"


def test_run_grid_experiment_uses_ai2thor_nav_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """Grid runner should resolve the nav graph from AI2-THOR when requested."""

    config = ExperimentConfig(
        instructions=["task_a.json"],
        beam_width_values=[1],
        beam_depth_values=[1],
        nav_graph_source="ai2thor_controller",
    )

    monkeypatch.setattr(
        "src.experiments.offline_harness.load_scene_positions",
        lambda _: {"agent": (0.0, 0.9, 0.0), "obj": (0.25, 0.9, 0.25)},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.load_ai2thor_nav_graph",
        lambda _scene: {(0.0, 0.9, 0.0): [(0.25, 0.9, 0.25)]},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.build_grid_nav_graph",
        lambda _scene_positions: (_ for _ in ()).throw(
            AssertionError("Synthetic nav graph builder should not be used.")
        ),
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.run_single_rollout",
        lambda cfg, task, **kwargs: {
            "case": task.case or cfg.case,
            "instruction": task.instruction,
            "beam_width": task.beam_width,
            "beam_depth": task.beam_depth,
            "completed": True,
            "abort_reason": "",
            "total_compute_time": 0.1,
            "final_schedule_time": 1.0,
            "schedule_tcsr": 1.0,
            "action_count": 1,
            "wait_count": 0,
            "monitor_count": 0,
            "replanning_count": 1,
            "avg_committed_steps_per_replan": 1.0,
            "steps": [],
            "timing_detail": {},
            "ground_truth_intervals": {"Microwave": 100.0},
            "nav_graph_nodes": len(kwargs["nav_graph"]),
        },
    )

    report = run_grid_experiment(config)

    assert report["config"]["nav_graph_source"] == "ai2thor_controller"
    assert report["results"][0]["nav_graph_nodes"] == 1


def test_run_single_rollout_dispatches_to_edf_adapter(
    monkeypatch: MonkeyPatch,
) -> None:
    """EDF planner type should delegate to the EDF rollout adapter."""

    config = ExperimentConfig(
        planner_type="edf",
        instructions=["task_a.json"],
        beam_width_values=[1],
        beam_depth_values=[1],
    )
    task = ExperimentTask("task_a.json", 1, 1, 0, config.case)

    monkeypatch.setattr(
        "src.experiments.offline_harness.run_single_rollout_edf",
        lambda cfg, task, **_: {
            "case": task.case or cfg.case,
            "instruction": task.instruction,
            "beam_width": task.beam_width,
            "beam_depth": task.beam_depth,
            "completed": True,
            "abort_reason": "",
            "total_compute_time": 0.0,
            "final_schedule_time": 1.0,
            "schedule_tcsr": 1.0,
            "action_count": 1,
            "wait_count": 0,
            "monitor_count": 0,
            "replanning_count": 1,
            "avg_committed_steps_per_replan": 1.0,
            "steps": [],
            "timing_detail": {},
            "ground_truth_intervals": {},
        },
    )

    result = run_single_rollout(
        config,
        task,
        nav_graph={(0.0, 0.0, 0.0): []},
        scene_positions={"agent": (0.0, 0.0, 0.0)},
    )

    assert result["completed"] is True
    assert result["final_schedule_time"] == 1.0


def test_run_single_rollout_dispatches_to_cpm_adapter(
    monkeypatch: MonkeyPatch,
) -> None:
    """CPM planner type should delegate to the CPM rollout adapter."""

    config = ExperimentConfig(
        planner_type="cpm",
        instructions=["task_a.json"],
        beam_width_values=[1],
        beam_depth_values=[1],
    )
    task = ExperimentTask("task_a.json", 1, 1, 0, config.case)

    monkeypatch.setattr(
        "src.experiments.offline_harness.run_single_rollout_cpm",
        lambda cfg, task, **_: {
            "case": task.case or cfg.case,
            "instruction": task.instruction,
            "beam_width": task.beam_width,
            "beam_depth": task.beam_depth,
            "completed": True,
            "abort_reason": "",
            "total_compute_time": 0.0,
            "final_schedule_time": 2.0,
            "schedule_tcsr": 1.0,
            "action_count": 1,
            "wait_count": 0,
            "monitor_count": 0,
            "replanning_count": 1,
            "avg_committed_steps_per_replan": 1.0,
            "steps": [],
            "timing_detail": {},
            "ground_truth_intervals": {},
        },
    )

    result = run_single_rollout(
        config,
        task,
        nav_graph={(0.0, 0.0, 0.0): []},
        scene_positions={"agent": (0.0, 0.0, 0.0)},
    )

    assert result["completed"] is True
    assert result["final_schedule_time"] == 2.0


def test_run_oracle_comparison_experiment_combines_scheduler_and_oracle(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle comparison runner should join deterministic and oracle results."""

    config = ExperimentConfig(
        experiment_name="oracle-grid",
        cases=["tasks_2_constraints_1"],
        instructions=["task_a.json"],
        beam_width_values=[1],
        beam_depth_values=[1],
        oracle_time_limit_seconds=5.0,
    )

    monkeypatch.setattr(
        "src.experiments.offline_harness.run_grid_experiment",
        lambda cfg: {
            "schema_version": cfg.schema_version,
            "saved_time": "2026-04-08T00:00:00",
            "experiment": {"name": cfg.experiment_name, "tags": []},
            "config": {"disable_monitoring": True},
            "selected_instructions": {"tasks_2_constraints_1": ["task_a.json"]},
            "summary_by_setting": {},
            "summary_by_case_setting": {},
            "comparison": {
                "best_by_task": {
                    "tasks_2_constraints_1::task_a.json": {
                        "case": "tasks_2_constraints_1",
                        "instruction": "task_a.json",
                        "beam_width": 1,
                        "beam_depth": 1,
                        "final_schedule_time": 120.0,
                        "total_compute_time": 1.0,
                    }
                }
            },
            "results": [
                {
                    "case": "tasks_2_constraints_1",
                    "instruction": "task_a.json",
                    "beam_width": 1,
                    "beam_depth": 1,
                    "completed": True,
                    "final_schedule_time": 120.0,
                    "total_compute_time": 1.0,
                    "schedule_tcsr": 1.0,
                    "wait_count": 0,
                    "monitor_count": 0,
                    "replanning_count": 1,
                    "avg_committed_steps_per_replan": 1.0,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness._apply_runtime_overrides",
        lambda _cfg: {},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness._restore_runtime_overrides",
        lambda _values: None,
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness.load_scene_positions",
        lambda _name: {"agent": (0.0, 0.9, 0.0), "obj": (0.25, 0.9, 0.25)},
    )
    monkeypatch.setattr(
        "src.experiments.offline_harness._run_exact_oracle_rollout",
        lambda *_args, **_kwargs: {
            "case": "tasks_2_constraints_1",
            "instruction": "task_a.json",
            "optimal_schedule_time": 100.0,
            "optimal_sequence": ["A", "B"],
            "solve_time": 0.2,
            "search_nodes": 10,
            "pruned_nodes": 3,
            "idle_advances": 1,
            "exact": True,
            "timeout_hit": False,
        },
    )

    report = run_oracle_comparison_experiment(config)

    assert report["schema_version"] == "offline_oracle_comparison.v1"
    assert report["oracle_summary"]["exact_instructions"] == 1
    assert report["gap_by_setting"]["w1_d1"]["avg_absolute_gap"] == 20.0


def test_exact_oracle_orders_candidates_by_name() -> None:
    """Oracle should sort feasible candidates lexicographically, not by heuristic."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    heuristic_manager = HeuristicManager(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
        time_limit_seconds=5.0,
    )

    def _make_candidate(name: str) -> Candidate:
        subtask = Subtask(
            task_name="task",
            name=name,
            repetition=1,
            subtask_type="Interaction",
            execution=Execution(
                objects={},
                primitive_actions=["NAVIGATE_TO Obj|1"],
            ),
            duration=Duration(type="Interaction", interval=5),
        )
        return Candidate(
            subtask=subtask,
            is_critical=False,
            actual_interaction_start_time=0.0,
            logical_interaction_start_time=0.0,
        )

    state = SchedulerState(
        subtask=_make_candidate("Z Task").subtask,
        completed_entries=[],
        remaining_subtasks=[],
        constraints=None,
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidates = [
        _make_candidate("Z Task"),
        _make_candidate("A Task"),
        _make_candidate("M Task"),
    ]

    ordered = oracle._order_candidates(node, candidates)

    assert [c.subtask.name for c in ordered] == ["A Task", "M Task", "Z Task"]


def test_exact_oracle_prunes_high_risk_nodes() -> None:
    """Strict oracle should reject branches whose scheduler risk reaches 2."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    heuristic_manager = HeuristicManager(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
        time_limit_seconds=5.0,
    )
    subtask = Subtask(
        task_name="task",
        name="Risky Task",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(
            objects={"Obj|1": 1},
            primitive_actions=["NAVIGATE_TO Obj|1", "TOGGLE_ON Obj|1"],
        ),
        duration=Duration(type="Interaction", interval=5),
    )
    state = SchedulerState(
        subtask=subtask,
        completed_entries=[CompletedEntry(subtask=subtask, schedule_end_time=10.0)],
        remaining_subtasks=[],
        constraints=None,
        current_time=10.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    risky_node = SimulationNode(
        heuristic_cost=10.0,
        depth=1,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=2,
    )

    oracle._started_at = time.perf_counter()
    oracle._timeout_hit = False
    oracle._search_nodes = 0
    oracle._pruned_nodes = 0

    oracle._search(risky_node, ("Risky Task",))

    assert oracle._search_nodes == 0
    assert oracle._pruned_nodes == 1


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
