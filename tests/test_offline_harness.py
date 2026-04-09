"""Tests for the offline in-process experiment harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx
from src.core.monitoring import BeliefUpdateContext, create_observation_model
from src.experiments.exact_oracle import DeterministicExactOracle, OracleSolution
from src.experiments.offline_compare import compare_result_files
from src.experiments.offline_harness import (
    ExperimentConfig,
    ExperimentTask,
    _edf_compute_deadline,
    _build_deterministic_scheduler_config,
    _serialize_schedule_steps,
    apply_cli_overrides,
    build_experiment_tasks,
    load_experiment_config,
    run_oracle_reference_experiment,
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


def test_edf_deadline_uses_interaction_start_semantics() -> None:
    """EDF release targets should align with successor interaction start time."""

    predecessor = Subtask(
        task_name="task",
        name="Cook Egg in Pan",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Stove|1"]),
        duration=Duration(type="Interaction", interval=5.0),
    )
    successor = Subtask(
        task_name="task",
        name="Turn Off Stove After Cooking Egg",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(
            objects={},
            primitive_actions=["NAVIGATE_TO StoveKnob|1", "TOGGLE_OFF StoveKnob|1"],
        ),
        duration=Duration(type="Interaction", interval=5.0),
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        predecessor.name,
        successor.name,
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=predecessor,
        completed_entries=[
            CompletedEntry(
                subtask=predecessor,
                schedule_start_time=20.0,
                schedule_end_time=34.46,
            )
        ],
        remaining_subtasks=[successor],
        constraints=constraints,
        current_time=70.4,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )

    adapter_deadline = _edf_compute_deadline(
        successor,
        state,
        nav_time=3.04,
        execution_time=8.0,
    )
    assert adapter_deadline == 134.46


def test_load_experiment_config_and_cli_override(tmp_path: Path) -> None:
    """Config loader should merge YAML defaults with CLI overrides."""

    config_path = tmp_path / "offline.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: baseline",
                "scene: FloorPlan1",
                "approach: bayesian",
                "ablation_config: DEFAULT",
                "beam_bound:",
                "  - [1, 1]",
                "  - [3, 3]",
                'nav_graph_source: "ai2thor_controller"',
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_experiment_config(config_path)
    merged = apply_cli_overrides(
        loaded,
        {
            "scene": "FloorPlan2",
            "approach": "edf",
            "ablation_config": "NONE_MONITORING",
            "beam_bound": [(2, 2), (4, 4)],
            "nav_graph_source": "ai2thor_controller",
        },
    )

    assert loaded.experiment_name == "baseline"
    assert merged.scene == "FloorPlan2"
    assert merged.approach == "edf"
    assert merged.ablation_config == "NONE_MONITORING"
    assert loaded.beam_bound == [(1, 1), (3, 3)]
    assert merged.beam_bound == [(2, 2), (4, 4)]
    assert merged.nav_graph_source == "ai2thor_controller"


def test_build_experiment_tasks_expands_instruction_and_beam_grid() -> None:
    """Task builder should emit the cartesian product over instructions and beams."""

    config = ExperimentConfig(
        instructions=["a.json", "b.json"],
        beam_bound=[(1, 1), (1, 3), (5, 1), (5, 3)],
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
        beam_bound=[(1, 1)],
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


def test_serialize_schedule_steps_exposes_scheduled_start_and_end() -> None:
    """Serialized steps should expose explicit scheduled timing fields."""

    interaction = Subtask(
        task_name="task",
        name="Cook Egg",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Stove|1"]),
        duration=Duration(type="Interaction", interval=5.0),
    )
    wait = Subtask(
        task_name="task",
        name="WAIT 5 to Cook Egg",
        repetition=1,
        subtask_type="WAIT",
        execution=Execution(objects={}, primitive_actions=["WAIT 5"]),
        duration=Duration(type="WAIT", interval=5.0),
    )
    completed_entries = [
        CompletedEntry(
            subtask=interaction,
            schedule_start_time=1.0,
            schedule_end_time=4.5,
            schedule_nav_time=1.25,
            sim_start_time=1.0,
            sim_end_time=4.5,
            execution_status=True,
        ),
        CompletedEntry(
            subtask=wait,
            schedule_start_time=4.5,
            schedule_end_time=9.5,
            sim_start_time=4.5,
            sim_end_time=9.5,
            execution_status=True,
        ),
    ]

    steps = _serialize_schedule_steps(completed_entries)

    assert steps[0]["start_time_scheduled"] == 1.0
    assert steps[0]["end_time_scheduled"] == 4.5
    assert steps[0]["schedule_nav_time"] == 1.25
    assert steps[1]["start_time_scheduled"] == 4.5
    assert steps[1]["end_time_scheduled"] == 9.5


def test_run_grid_experiment_returns_schema_and_writes_report(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Grid runner should assemble the standardized report schema."""

    config = ExperimentConfig(
        experiment_name="test-grid",
        instructions=["task_a.json", "task_b.json"],
        beam_bound=[(1, 1), (1, 2)],
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
        beam_bound=[(1, 1)],
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
        approach="edf",
        instructions=["task_a.json"],
        beam_bound=[(1, 1)],
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
        approach="cpm",
        instructions=["task_a.json"],
        beam_bound=[(1, 1)],
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


def test_run_oracle_reference_experiment_writes_oracle_summary(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle reference runner should emit per-instruction oracle rows."""

    config = ExperimentConfig(
        experiment_name="oracle-grid",
        cases=["tasks_2_constraints_1"],
        instructions=["task_a.json"],
        beam_bound=[(1, 1)],
        oracle_time_limit_seconds=5.0,
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
            "final_schedule_time": 100.0,
            "optimal_sequence": ["A", "B"],
            "solve_time": 0.2,
            "total_compute_time": 0.2,
            "search_nodes": 10,
            "pruned_nodes": 3,
            "idle_advances": 1,
            "exact": True,
            "timeout_hit": False,
            "schedule_tcsr": 1.0,
            "tcsr_is_one": True,
            "steps": [
                {
                    "subtask_name": "A",
                    "subtask_type": "Interaction",
                    "start_time_scheduled": 0.0,
                    "end_time_scheduled": 10.0,
                    "start_time_simulation": 0.0,
                    "end_time_simulation": 10.0,
                    "schedule_nav_time": None,
                    "execution_status": True,
                    "monitored_subtask": None,
                }
            ],
            "timing_detail": {},
        },
    )

    monkeypatch.setattr(
        "src.experiments.offline_harness.save_oracle_reference_rows",
        lambda *args, **kwargs: None,
    )

    report = run_oracle_reference_experiment(config)

    assert report["schema_version"] == "offline_oracle_reference.v1"
    assert report["oracle_summary"]["exact_instructions"] == 1
    assert report["oracle_results"][0]["optimal_schedule_time"] == 100.0
    assert report["oracle_summary"]["avg_total_compute_time"] == 0.2
    assert report["oracle_summary"]["avg_schedule_tcsr"] == 1.0


def test_oracle_solution_as_dict_exposes_timing_payload() -> None:
    """Oracle solution payload should expose per-step scheduled timings."""

    subtask = Subtask(
        task_name="task",
        name="Cook Egg",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Stove|1"]),
        duration=Duration(type="Interaction", interval=5.0),
    )
    solution = OracleSolution(
        instruction="task_a.json",
        case="tasks_2_constraints_1",
        optimal_schedule_time=12.0,
        optimal_sequence=["Cook Egg"],
        solve_time=0.25,
        search_nodes=3,
        pruned_nodes=1,
        idle_advances=0,
        exact=True,
        timeout_hit=False,
        completed_entries=[
            CompletedEntry(
                subtask=subtask,
                schedule_start_time=2.0,
                schedule_end_time=12.0,
                sim_start_time=2.0,
                sim_end_time=12.0,
                execution_status=True,
            )
        ],
    )

    payload = solution.as_dict()

    assert payload["final_schedule_time"] == 12.0
    assert payload["total_compute_time"] == 0.25
    assert payload["steps"][0]["start_time_scheduled"] == 2.0
    assert payload["steps"][0]["end_time_scheduled"] == 12.0


def test_build_deterministic_scheduler_config_uses_edf_for_oracle() -> None:
    """Oracle comparisons should default to an EDF deterministic baseline."""

    config = ExperimentConfig(
        approach="oracle",
        ablation_config="DEFAULT",
        gt_distribution="gaussian",
    )

    deterministic_config = _build_deterministic_scheduler_config(config)

    assert deterministic_config.approach == "edf"
    assert deterministic_config.ablation_config == "NONE_MONITORING"
    assert deterministic_config.gt_distribution == "constant"


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


def test_exact_oracle_records_explicit_prenavigation_sequence(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle should record the actual child node name emitted by the scheduler."""

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
        name="Heat Mug",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(
            objects={"Mug|1": 1},
            primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
        ),
        duration=Duration(type="Interaction", interval=5),
    )
    initial_state = SchedulerState(
        subtask=subtask,
        completed_entries=[],
        remaining_subtasks=[subtask],
        constraints=None,
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    root_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=initial_state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=subtask,
        is_critical=False,
        actual_interaction_start_time=0.0,
        logical_interaction_start_time=0.0,
        estimated_first_nav_duration=2.0,
    )
    nav_state = SchedulerState(
        subtask=Subtask(
            task_name="task",
            name="NAVIGATE_TO_Mug|1",
            repetition=1,
            subtask_type="NAVIGATE",
            execution=Execution(objects={}, primitive_actions=["NAVIGATE_TO Mug|1"]),
            duration=Duration(type="NAVIGATE", interval=2.0),
        ),
        completed_entries=[],
        remaining_subtasks=[],
        constraints=None,
        current_time=2.0,
        scene_positions={"agent": (1.0, 0.9, 0.0)},
        held_object=None,
    )
    nav_node = SimulationNode(
        heuristic_cost=2.0,
        depth=1,
        tie_breaker=1,
        parent_node=root_node,
        state=nav_state,
        risk_level=0,
    )

    monkeypatch.setattr(
        constraint_handler,
        "get_feasible_candidates",
        lambda node: ([candidate], []) if node.state.remaining_subtasks else ([], []),
    )
    monkeypatch.setattr(
        oracle.scheduler,
        "_expand_subtask_wo_monitoring",
        lambda *_args, **_kwargs: nav_node,
    )

    oracle._best_makespan = None
    oracle._best_sequence = []
    oracle._search_nodes = 0
    oracle._pruned_nodes = 0
    oracle._idle_advances = 0
    oracle._timeout_hit = False
    oracle._started_at = time.perf_counter()

    oracle._search(root_node, ())

    assert oracle._best_sequence == ["NAVIGATE_TO_Mug|1"]


def test_exact_oracle_records_explicit_wait_sequence(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle should record WAIT nodes instead of implicit time jumps."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    heuristic_manager = HeuristicManager(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
        time_limit_seconds=5.0,
    )
    blocked_subtask = Subtask(
        task_name="task",
        name="Heat Mug",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Mug|1"]),
        duration=Duration(type="Interaction", interval=3.0),
    )
    root_state = SchedulerState(
        subtask=blocked_subtask,
        completed_entries=[],
        remaining_subtasks=[blocked_subtask],
        constraints=None,
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    root_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=root_state,
        risk_level=0,
    )
    blocked_candidate = Candidate(
        subtask=blocked_subtask,
        is_critical=False,
        actual_interaction_start_time=5.0,
        logical_interaction_start_time=5.0,
        estimated_first_nav_duration=0.0,
    )
    wait_state = SchedulerState(
        subtask=Subtask(
            task_name="task",
            name="Wait for Heat Mug",
            repetition=1,
            subtask_type="WAIT",
            execution=Execution(objects={}, primitive_actions=["WAIT 5.0"]),
            duration=Duration(type="WAIT", interval=5.0),
        ),
        completed_entries=[],
        remaining_subtasks=[],
        constraints=None,
        current_time=5.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    wait_node = SimulationNode(
        heuristic_cost=5.0,
        depth=1,
        tie_breaker=1,
        parent_node=root_node,
        state=wait_state,
        risk_level=0,
    )

    monkeypatch.setattr(
        constraint_handler,
        "get_feasible_candidates",
        lambda node: ([], [blocked_candidate]) if node.state.remaining_subtasks else ([], []),
    )
    monkeypatch.setattr(
        oracle.scheduler,
        "_expand_single_wait",
        lambda *_args, **_kwargs: wait_node,
    )

    oracle._best_makespan = None
    oracle._best_sequence = []
    oracle._search_nodes = 0
    oracle._pruned_nodes = 0
    oracle._idle_advances = 0
    oracle._timeout_hit = False
    oracle._started_at = time.perf_counter()

    oracle._search(root_node, ())

    assert oracle._best_sequence == ["Wait for Heat Mug"]
    assert oracle._idle_advances == 1


def test_exact_oracle_prefers_blocked_prenavigation_branch(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle should explore PRENAV branches for blocked candidates."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    heuristic_manager = HeuristicManager(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
        time_limit_seconds=5.0,
    )
    blocked_subtask = Subtask(
        task_name="task",
        name="Heat Mug",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(
            objects={"Mug|1": 1},
            primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
        ),
        duration=Duration(type="Interaction", interval=3.0),
    )
    root_state = SchedulerState(
        subtask=blocked_subtask,
        completed_entries=[],
        remaining_subtasks=[blocked_subtask],
        constraints=None,
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    root_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=root_state,
        risk_level=0,
    )
    blocked_candidate = Candidate(
        subtask=blocked_subtask,
        is_critical=False,
        actual_interaction_start_time=5.0,
        logical_interaction_start_time=5.0,
        estimated_first_nav_duration=2.0,
    )
    wait_node = SimulationNode(
        heuristic_cost=5.0,
        depth=1,
        tie_breaker=1,
        parent_node=root_node,
        state=SchedulerState(
            subtask=Subtask(
                task_name="task",
                name="Wait for Heat Mug",
                repetition=1,
                subtask_type="WAIT",
                execution=Execution(objects={}, primitive_actions=["WAIT 5.0"]),
                duration=Duration(type="WAIT", interval=5.0),
            ),
            completed_entries=[],
            remaining_subtasks=[],
            constraints=None,
            current_time=5.0,
            scene_positions={"agent": (0.0, 0.9, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )
    prenav_node = SimulationNode(
        heuristic_cost=2.0,
        depth=1,
        tie_breaker=2,
        parent_node=root_node,
        state=SchedulerState(
            subtask=Subtask(
                task_name="task",
                name="NAVIGATE_TO_Mug|1",
                repetition=1,
                subtask_type="NAVIGATE",
                execution=Execution(
                    objects={},
                    primitive_actions=["NAVIGATE_TO Mug|1"],
                ),
                duration=Duration(type="NAVIGATE", interval=2.0),
            ),
            completed_entries=[],
            remaining_subtasks=[],
            constraints=None,
            current_time=2.0,
            scene_positions={"agent": (1.0, 0.9, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )

    monkeypatch.setattr(
        constraint_handler,
        "get_feasible_candidates",
        lambda node: ([], [blocked_candidate]) if node is root_node else ([], []),
    )
    monkeypatch.setattr(
        oracle.scheduler,
        "_expand_single_wait",
        lambda *_args, **_kwargs: wait_node,
    )
    monkeypatch.setattr(
        oracle.scheduler,
        "_expand_blocked_prenavigation",
        lambda *_args, **_kwargs: prenav_node,
    )

    oracle._best_makespan = None
    oracle._best_sequence = []
    oracle._search_nodes = 0
    oracle._pruned_nodes = 0
    oracle._idle_advances = 0
    oracle._timeout_hit = False
    oracle._started_at = time.perf_counter()

    oracle._search(root_node, ())

    assert oracle._best_sequence == ["NAVIGATE_TO_Mug|1"]
    assert oracle._best_makespan == 2.0


def test_exact_oracle_respects_reserved_prenavigation_target(
    monkeypatch: MonkeyPatch,
) -> None:
    """Oracle should restrict branching to the reserved pre-navigation target."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    heuristic_manager = HeuristicManager(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
        time_limit_seconds=5.0,
    )
    reserved_subtask = Subtask(
        task_name="task",
        name="Reserved Task",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Mug|1"]),
        duration=Duration(type="Interaction", interval=3.0),
        decomposed=True,
    )
    setattr(reserved_subtask, "pre_navigation_reserved", True)
    other_subtask = Subtask(
        task_name="task",
        name="Other Task",
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=["TOGGLE_ON Cup|1"]),
        duration=Duration(type="Interaction", interval=3.0),
    )
    root_state = SchedulerState(
        subtask=reserved_subtask,
        completed_entries=[],
        remaining_subtasks=[reserved_subtask, other_subtask],
        constraints=None,
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    root_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=root_state,
        risk_level=0,
    )
    reserved_candidate = Candidate(
        subtask=reserved_subtask,
        is_critical=False,
        actual_interaction_start_time=0.0,
        logical_interaction_start_time=0.0,
    )
    other_candidate = Candidate(
        subtask=other_subtask,
        is_critical=False,
        actual_interaction_start_time=0.0,
        logical_interaction_start_time=0.0,
    )

    monkeypatch.setattr(
        constraint_handler,
        "get_feasible_candidates",
        lambda _node: ([reserved_candidate, other_candidate], []),
    )

    def _expand_only_reserved(
        _node: SimulationNode,
        candidate: Candidate,
        *_args: object,
        **_kwargs: object,
    ) -> SimulationNode:
        if candidate.subtask.name != "Reserved Task":
            raise AssertionError("Oracle should not branch into non-reserved candidates.")
        return SimulationNode(
            heuristic_cost=1.0,
            depth=1,
            tie_breaker=1,
            parent_node=root_node,
            state=SchedulerState(
                subtask=reserved_subtask,
                completed_entries=[],
                remaining_subtasks=[],
                constraints=None,
                current_time=1.0,
                scene_positions={"agent": (0.0, 0.9, 0.0)},
                held_object=None,
            ),
            risk_level=0,
        )

    monkeypatch.setattr(
        oracle.scheduler,
        "_expand_subtask_wo_monitoring",
        _expand_only_reserved,
    )

    oracle._best_makespan = None
    oracle._best_sequence = []
    oracle._search_nodes = 0
    oracle._pruned_nodes = 0
    oracle._idle_advances = 0
    oracle._timeout_hit = False
    oracle._started_at = time.perf_counter()

    oracle._search(root_node, ())

    assert oracle._best_sequence == ["Reserved Task"]


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
