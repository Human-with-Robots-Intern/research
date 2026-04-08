"""In-process offline scheduler experiment harness."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import yaml
from src.core import Agent, Scheduler
from src.core.monitoring import (
    create_ground_truth_store,
    create_monitoring_backend,
    create_observation_model,
)
from src.models.dataclass import SchedulerState, TaskExecutionStatus
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from src.utils.config import constants
from src.utils.io_utils.result_saver import calculate_timing_success_rate
from src.utils.io_utils.task_io import load_scene_positions, load_task_data_from_sampled_set
from src.utils.task.task_util import TaskUtil

Position = Tuple[float, float, float]
NavGraph = Dict[Position, list[Position]]


def _quantize_position(position: Position) -> Position:
    """Snap a position onto the global navigation grid."""

    return tuple(
        round(float(coord) / constants.GRID_SIZE) * constants.GRID_SIZE
        for coord in position
    )


@dataclass
class ExperimentConfig:
    """Serializable configuration for an offline experiment session."""

    experiment_name: str = "offline_experiment"
    tags: list[str] = field(default_factory=list)
    task_folder_name: str = "sampled_10_instruction_set_for_final_experiment_251203"
    case: str = "tasks_3_constraints_2"
    scene: str = "FloorPlan13"
    instructions: list[str] = field(default_factory=list)
    max_tasks: int = 3
    beam_width_values: list[int] = field(default_factory=lambda: [1, 5, 10])
    beam_depth_values: list[int] = field(default_factory=lambda: [1, 5, 10])
    belief_update_method: str = "bayesian"
    gt_distribution: str = "constant"
    gt_seed: int = 42
    init_prior_mean: Optional[float] = None
    init_prior_variance: Optional[float] = None
    disable_monitoring: bool = False
    factor_alpha: Optional[float] = None
    bayesian_threshold_probability: Optional[float] = None
    observation_mode: str = "synthetic_gaussian"
    output_path: Optional[str] = None
    schema_version: str = "offline_harness.v1"


@dataclass(frozen=True)
class ExperimentTask:
    """Single rollout unit inside an offline experiment grid."""

    instruction: str
    beam_width: int
    beam_depth: int
    task_index: int


def _read_config_file(config_path: Path) -> dict[str, Any]:
    """Load a JSON or YAML experiment config file."""

    suffix = config_path.suffix.lower()
    raw_text = config_path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(raw_text)
    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(raw_text)
        return loaded or {}
    raise ValueError(f"Unsupported config file extension: {config_path.suffix}")


def load_experiment_config(config_path: Optional[Path]) -> ExperimentConfig:
    """Load experiment configuration from disk or defaults.

    Args:
        config_path: Optional JSON/YAML path.

    Returns:
        ExperimentConfig: Parsed configuration object.
    """

    if config_path is None:
        return ExperimentConfig()

    payload = _read_config_file(config_path)
    return ExperimentConfig(**payload)


def apply_cli_overrides(
    config: ExperimentConfig,
    overrides: Mapping[str, Any],
) -> ExperimentConfig:
    """Apply non-``None`` CLI overrides onto a config object."""

    merged = asdict(config)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return ExperimentConfig(**merged)


def build_grid_nav_graph(scene_positions: Mapping[str, Position]) -> NavGraph:
    """Build a lightweight grid navigation graph from scene object positions."""

    if "agent" not in scene_positions:
        raise ValueError("Scene positions must contain an 'agent' entry.")

    grid_size = constants.GRID_SIZE
    agent_position = tuple(scene_positions["agent"])
    agent_y = _quantize_position(agent_position)[1]
    floor_points = {
        (
            _quantize_position(tuple(position))[0],
            agent_y,
            _quantize_position(tuple(position))[2],
        )
        for position in scene_positions.values()
    }
    floor_points.add(
        (
            _quantize_position(agent_position)[0],
            agent_y,
            _quantize_position(agent_position)[2],
        )
    )
    x_values = sorted({point[0] for point in floor_points})
    z_values = sorted({point[2] for point in floor_points})
    if not x_values or not z_values:
        raise ValueError("Unable to derive navigation bounds from scene positions.")

    x_min, x_max = min(x_values), max(x_values)
    z_min, z_max = min(z_values), max(z_values)
    nav_graph: NavGraph = {}
    x_steps = int(round((x_max - x_min) / grid_size))
    z_steps = int(round((z_max - z_min) / grid_size))
    for x_index in range(x_steps + 1):
        for z_index in range(z_steps + 1):
            x_coord = round(x_min + (x_index * grid_size), 3)
            z_coord = round(z_min + (z_index * grid_size), 3)
            node = (x_coord, agent_y, z_coord)
            nav_graph[node] = []

    for node in list(nav_graph.keys()):
        x_coord, y_coord, z_coord = node
        candidate_neighbors = [
            (round(x_coord + grid_size, 3), y_coord, z_coord),
            (round(x_coord - grid_size, 3), y_coord, z_coord),
            (x_coord, y_coord, round(z_coord + grid_size, 3)),
            (x_coord, y_coord, round(z_coord - grid_size, 3)),
        ]
        nav_graph[node] = [
            neighbor for neighbor in candidate_neighbors if neighbor in nav_graph
        ]
    return nav_graph


def resolve_instructions(config: ExperimentConfig) -> list[str]:
    """Resolve instruction file names for the current experiment."""

    if config.instructions:
        return list(config.instructions)

    case_dir = (
        constants.ASSETS_PATH
        / "tasks"
        / config.task_folder_name
        / config.case
        / config.scene
    )
    if not case_dir.exists():
        raise FileNotFoundError(f"Task case directory not found: {case_dir}")

    task_files = sorted(path.name for path in case_dir.glob("*.json"))
    if not task_files:
        raise FileNotFoundError(f"No task files found under: {case_dir}")
    return task_files[: config.max_tasks]


def build_experiment_tasks(config: ExperimentConfig) -> list[ExperimentTask]:
    """Build the cartesian product of instructions and beam settings."""

    tasks: list[ExperimentTask] = []
    for task_index, instruction in enumerate(resolve_instructions(config)):
        for beam_width, beam_depth in product(
            config.beam_width_values,
            config.beam_depth_values,
        ):
            tasks.append(
                ExperimentTask(
                    instruction=instruction,
                    beam_width=int(beam_width),
                    beam_depth=int(beam_depth),
                    task_index=task_index,
                )
            )
    return tasks


def _copy_schedule_to_sim_fields(state: SchedulerState) -> None:
    """Mirror schedule timestamps into simulation fields for offline evaluation."""

    for entry in state.completed_entries:
        if entry.sim_start_time == float("inf"):
            entry.sim_start_time = entry.schedule_start_time
        if entry.sim_end_time == float("inf"):
            entry.sim_end_time = entry.schedule_end_time
        if entry.execution_status == TaskExecutionStatus.NOT_EXECUTED:
            entry.execution_status = TaskExecutionStatus.SUCCESS
        if entry.sim_nav_time is None:
            entry.sim_nav_time = entry.schedule_nav_time


def _apply_runtime_overrides(config: ExperimentConfig) -> dict[str, Any]:
    """Apply temporary constants overrides and return previous values."""

    previous_values = {
        "task_path": constants.TASK_PATH,
        "monitoring_enabled": constants.MONITORING_ENABLED,
        "init_prior_mean": constants.INIT_PRIOR_MEAN,
        "init_prior_variance": constants.INIT_PRIOR_VARIANCE,
        "factor_alpha": constants.FACTOR_ALPHA,
        "bayesian_threshold_probability": constants.BAYESIAN_THRESHOLD_PROBABILITY,
    }
    constants.set_task_path(constants.ASSETS_PATH / "tasks" / config.task_folder_name)
    constants.set_monitoring_enabled(not config.disable_monitoring)
    if config.init_prior_mean is not None:
        constants.set_init_prior_mean(config.init_prior_mean)
    if config.init_prior_variance is not None:
        constants.set_init_prior_variance(config.init_prior_variance)
    if config.factor_alpha is not None:
        constants.set_factor_alpha(config.factor_alpha)
    if config.bayesian_threshold_probability is not None:
        constants.set_bayesian_threshold_probability(
            config.bayesian_threshold_probability
        )
    return previous_values


def _restore_runtime_overrides(previous_values: Mapping[str, Any]) -> None:
    """Restore mutable runtime constants after an experiment."""

    constants.set_task_path(previous_values["task_path"])
    constants.set_monitoring_enabled(previous_values["monitoring_enabled"])
    constants.set_init_prior_mean(previous_values["init_prior_mean"])
    constants.set_init_prior_variance(previous_values["init_prior_variance"])
    constants.set_factor_alpha(previous_values["factor_alpha"])
    constants.set_bayesian_threshold_probability(
        previous_values["bayesian_threshold_probability"]
    )


def run_single_rollout(
    config: ExperimentConfig,
    task: ExperimentTask,
    *,
    nav_graph: NavGraph,
    scene_positions: Mapping[str, Position],
) -> dict[str, Any]:
    """Execute one offline rollout for a task/beam combination."""

    task_data = load_task_data_from_sampled_set(
        config.case,
        config.scene,
        task.instruction,
    )
    subtasks, constraints, bayesian_load = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{config.scene}_physics_environment.json",
    )
    current_state = TaskUtil.get_init_state(
        subtasks,
        constraints,
        copy.deepcopy(dict(scene_positions)),
    )

    action_handler = ActionHandler(nav_graph, real_world_mode=False)
    constraint_handler = ConstraintHandler(action_handler)
    observation_model = create_observation_model(config.observation_mode)
    belief_store, monitoring_policy, belief_updater = create_monitoring_backend(
        config.belief_update_method,
        bayesian_load,
        particle_distribution="gaussian",
        observation_model=observation_model,
    )
    ground_truth_store = create_ground_truth_store(
        constants.CRITICAL_OBJECT_GROUND_TRUTH,
        distribution=config.gt_distribution,
        random_seed=config.gt_seed,
    )
    ground_truth_store.ensure_intervals(bayesian_load)
    agent = Agent(
        constraint_handler,
        bayesian_load,
        belief_updater=belief_updater,
        belief_store=belief_store,
        ground_truth_store=ground_truth_store,
    )
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=HeuristicManager(action_handler),
        monitoring_policy=monitoring_policy,
        beam_width=task.beam_width,
        simulation_depth=task.beam_depth,
    )

    total_compute_time = 0.0
    steps: list[dict[str, Any]] = []
    aborted = False
    abort_reason = ""
    while current_state.remaining_subtasks:
        next_state, compute_elapsed_time = scheduler.get_next_state(current_state)
        total_compute_time += compute_elapsed_time
        if next_state is None:
            aborted = True
            abort_reason = "no_feasible_solution"
            break

        _copy_schedule_to_sim_fields(next_state)
        last_entry = next_state.completed_entries[-1]
        monitored_subtask: Optional[dict[str, Any]] = None
        if (
            not config.disable_monitoring
            and next_state.subtask.subtask_type == "Monitor"
        ):
            next_state, monitored_subtask = agent.update_monitoring_belief(next_state)
            _copy_schedule_to_sim_fields(next_state)

        steps.append(
            {
                "subtask_name": next_state.subtask.name,
                "subtask_type": next_state.subtask.subtask_type,
                "schedule_end_time": last_entry.schedule_end_time,
                "schedule_nav_time": last_entry.schedule_nav_time,
                "monitored_subtask": monitored_subtask,
            }
        )
        current_state = next_state
        if len(steps) > 500:
            aborted = True
            abort_reason = "step_guard_exceeded"
            break

    _copy_schedule_to_sim_fields(current_state)
    _, schedule_tcsr, detail_log = calculate_timing_success_rate(
        current_state.constraints,
        current_state.completed_entries,
        ground_truth_overrides=ground_truth_store.as_dict(),
    )
    wait_count = sum(1 for step in steps if step["subtask_type"] == "WAIT")
    monitor_count = sum(1 for step in steps if step["subtask_type"] == "Monitor")
    action_count = sum(
        1 for step in steps if step["subtask_type"] not in {"WAIT", "Monitor"}
    )

    return {
        "instruction": task.instruction,
        "beam_width": task.beam_width,
        "beam_depth": task.beam_depth,
        "completed": not aborted and not current_state.remaining_subtasks,
        "abort_reason": abort_reason,
        "total_compute_time": total_compute_time,
        "final_schedule_time": current_state.current_time,
        "schedule_tcsr": schedule_tcsr,
        "action_count": action_count,
        "wait_count": wait_count,
        "monitor_count": monitor_count,
        "steps": steps,
        "timing_detail": detail_log,
        "ground_truth_intervals": ground_truth_store.as_dict(),
    }


def summarize_results(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate per-run results into a setting-level summary."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        beam_key = f"w{int(result['beam_width'])}_d{int(result['beam_depth'])}"
        grouped.setdefault(beam_key, []).append(result)

    summary: dict[str, dict[str, Any]] = {}
    for beam_key, rows in grouped.items():
        completed_rows = [row for row in rows if row["completed"]]
        schedule_times = [float(row["final_schedule_time"]) for row in completed_rows]
        compute_times = [float(row["total_compute_time"]) for row in rows]
        tcsr_values = [
            float(row["schedule_tcsr"])
            for row in completed_rows
            if row["schedule_tcsr"] is not None
        ]
        wait_counts = [int(row["wait_count"]) for row in rows]
        monitor_counts = [int(row["monitor_count"]) for row in rows]
        summary[beam_key] = {
            "num_runs": len(rows),
            "completed_runs": len(completed_rows),
            "avg_schedule_time": mean(schedule_times) if schedule_times else None,
            "median_schedule_time": median(schedule_times) if schedule_times else None,
            "avg_compute_time": mean(compute_times) if compute_times else None,
            "avg_schedule_tcsr": mean(tcsr_values) if tcsr_values else None,
            "avg_wait_count": mean(wait_counts) if wait_counts else None,
            "avg_monitor_count": mean(monitor_counts) if monitor_counts else None,
        }
    return summary


def compare_ready_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build compact comparison helpers from run results."""

    best_by_task: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result["instruction"]), []).append(result)

    for instruction, rows in grouped.items():
        best_row = sorted(
            rows,
            key=lambda row: (row["final_schedule_time"], row["total_compute_time"]),
        )[0]
        best_by_task[instruction] = {
            "beam_width": best_row["beam_width"],
            "beam_depth": best_row["beam_depth"],
            "final_schedule_time": best_row["final_schedule_time"],
            "total_compute_time": best_row["total_compute_time"],
        }
    return {"best_by_task": best_by_task}


def run_grid_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Run an offline experiment grid and return a structured report."""

    previous_values = _apply_runtime_overrides(config)
    try:
        scene_positions = load_scene_positions(f"{config.scene}_positions.json")
        nav_graph = build_grid_nav_graph(scene_positions)
        tasks = build_experiment_tasks(config)
        results = [
            run_single_rollout(
                config,
                task,
                nav_graph=nav_graph,
                scene_positions=scene_positions,
            )
            for task in tasks
        ]
        return {
            "schema_version": config.schema_version,
            "saved_time": datetime.now().isoformat(timespec="seconds"),
            "experiment": {
                "name": config.experiment_name,
                "tags": list(config.tags),
            },
            "config": asdict(config),
            "summary_by_setting": summarize_results(results),
            "comparison": compare_ready_summary(results),
            "results": results,
        }
    finally:
        _restore_runtime_overrides(previous_values)


def save_experiment_report(report: Mapping[str, Any], output_path: Path) -> None:
    """Persist an experiment report as JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def iter_report_lines(report: Mapping[str, Any]) -> Iterable[str]:
    """Yield a compact CLI report preview."""

    yield f"Experiment: {report['experiment']['name']}"
    for setting, metrics in report["summary_by_setting"].items():
        yield (
            f"- {setting}: completed={metrics['completed_runs']}/{metrics['num_runs']}, "
            f"avg_schedule_time={metrics['avg_schedule_time']}, "
            f"median_schedule_time={metrics['median_schedule_time']}, "
            f"avg_compute_time={metrics['avg_compute_time']}, "
            f"avg_schedule_tcsr={metrics['avg_schedule_tcsr']}"
        )
