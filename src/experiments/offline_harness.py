"""In-process offline scheduler experiment harness."""

from __future__ import annotations

import copy
import heapq
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import yaml
from src.core import Agent, Scheduler
from src.experiments.exact_oracle import (
    DeterministicExactOracle,
    build_initial_oracle_upper_bound,
)
from src.core.monitoring import (
    create_ground_truth_store,
    create_monitoring_backend,
    create_observation_model,
)
from src.models.dataclass import (
    ActionResult,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
    TaskExecutionStatus,
)
from src.models.task import Duration, Execution, Subtask
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
    planner_type: str = "bayesian"
    case: str = "tasks_3_constraints_2"
    cases: list[str] = field(default_factory=list)
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
    nav_graph_source: str = "synthetic_grid"
    output_path: Optional[str] = None
    oracle_time_limit_seconds: float = 30.0
    schema_version: str = "offline_harness.v1"


@dataclass(frozen=True)
class ExperimentTask:
    """Single rollout unit inside an offline experiment grid."""

    instruction: str
    beam_width: int
    beam_depth: int
    task_index: int
    case: str = ""


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
    payload.pop("execution_mode", None)
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


def load_ai2thor_nav_graph(scene_name: str) -> NavGraph:
    """Load the navigation graph directly from an AI2-THOR controller.

    Args:
        scene_name: AI2-THOR scene identifier such as ``FloorPlan13``.

    Returns:
        Navigation graph extracted from the controller.

    Raises:
        RuntimeError: If the controller cannot be initialized or the graph cannot
            be loaded.
    """

    from ithor.utils.math_utils import load_navigation_graph
    from src.simulation.runner_ai2thor import init_ai2thor_controller

    controller = None
    try:
        controller = init_ai2thor_controller(scene_name)
        return load_navigation_graph(controller)
    except Exception as exc:  # pragma: no cover - exercised via integration usage.
        raise RuntimeError(
            f"Failed to load AI2-THOR navigation graph for scene '{scene_name}'."
        ) from exc
    finally:
        if controller is not None:
            try:
                controller.stop()
            except Exception:
                pass


def resolve_nav_graph(
    config: ExperimentConfig,
    scene_positions: Mapping[str, Position],
) -> NavGraph:
    """Resolve the navigation graph source for offline planning.

    Args:
        config: Experiment configuration.
        scene_positions: Preloaded scene positions used by the synthetic graph path.

    Returns:
        Navigation graph chosen by ``config.nav_graph_source``.

    Raises:
        ValueError: If the nav graph source is unsupported.
    """

    if config.nav_graph_source == "synthetic_grid":
        return build_grid_nav_graph(scene_positions)
    if config.nav_graph_source == "ai2thor_controller":
        return load_ai2thor_nav_graph(config.scene)
    raise ValueError(f"Unsupported nav_graph_source: {config.nav_graph_source}")


def resolve_cases(config: ExperimentConfig) -> list[str]:
    """Resolve case names for the current experiment.

    Args:
        config: Experiment configuration.

    Returns:
        Ordered list of cases to run.
    """

    if config.cases:
        return list(config.cases)
    return [config.case]


def resolve_instructions(
    config: ExperimentConfig,
    case_name: Optional[str] = None,
) -> list[str]:
    """Resolve instruction file names for a case.

    Args:
        config: Experiment configuration.
        case_name: Optional explicit case override.

    Returns:
        Sorted instruction file names for the selected case.
    """

    resolved_case = case_name or config.case

    if config.instructions:
        return list(config.instructions)

    case_dir = (
        constants.ASSETS_PATH
        / "tasks"
        / config.task_folder_name
        / resolved_case
        / config.scene
    )
    if not case_dir.exists():
        raise FileNotFoundError(f"Task case directory not found: {case_dir}")

    task_files = sorted(path.name for path in case_dir.glob("*.json"))
    if not task_files:
        raise FileNotFoundError(f"No task files found under: {case_dir}")
    return task_files[: config.max_tasks]


def build_selected_instruction_map(config: ExperimentConfig) -> dict[str, list[str]]:
    """Build the selected instruction set for every requested case.

    Args:
        config: Experiment configuration.

    Returns:
        Mapping from case name to selected instruction file names.
    """

    return {
        case_name: resolve_instructions(config, case_name)
        for case_name in resolve_cases(config)
    }


def build_experiment_tasks(config: ExperimentConfig) -> list[ExperimentTask]:
    """Build the cartesian product of instructions and beam settings."""

    tasks: list[ExperimentTask] = []
    for case_name in resolve_cases(config):
        for task_index, instruction in enumerate(resolve_instructions(config, case_name)):
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
                        case=case_name,
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

    if config.planner_type == "edf":
        return run_single_rollout_edf(
            config,
            task,
            nav_graph=nav_graph,
            scene_positions=scene_positions,
        )
    if config.planner_type == "cpm":
        return run_single_rollout_cpm(
            config,
            task,
            nav_graph=nav_graph,
            scene_positions=scene_positions,
        )
    if config.planner_type != "bayesian":
        raise ValueError(f"Unsupported planner_type: {config.planner_type}")

    task_data = load_task_data_from_sampled_set(
        task.case or config.case,
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
    observation_model = create_observation_model(
        config.observation_mode,
        random_seed=config.gt_seed,
    )
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
    chunk_sizes: list[int] = []
    replanning_count = 0
    aborted = False
    abort_reason = ""
    while current_state.remaining_subtasks:
        next_state, compute_elapsed_time = scheduler.get_next_state(current_state)
        planned_states = [] if next_state is None else [next_state]

        total_compute_time += compute_elapsed_time
        replanning_count += 1
        if not planned_states:
            aborted = True
            abort_reason = "no_feasible_solution"
            break

        executed_in_chunk = 0
        for next_state in planned_states:
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
            executed_in_chunk += 1
            if len(steps) > 500:
                aborted = True
                abort_reason = "step_guard_exceeded"
                break
        chunk_sizes.append(executed_in_chunk)
        if aborted:
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
    avg_committed_steps = (
        sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0.0
    )

    return {
        "case": task.case or config.case,
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
        "replanning_count": replanning_count,
        "avg_committed_steps_per_replan": avg_committed_steps,
        "steps": steps,
        "timing_detail": detail_log,
        "ground_truth_intervals": ground_truth_store.as_dict(),
    }


def _simulate_subtask_actions(
    current_state: SchedulerState,
    subtask: Subtask,
    action_handler: ActionHandler,
) -> Optional[ActionResult]:
    """Simulate a subtask from the current state and return the final action log."""

    primitive_actions = subtask.execution.primitive_actions if subtask.execution else None
    if not primitive_actions:
        return None
    temp_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=current_state,
        risk_level=0,
    )
    return action_handler.get_actions_info(temp_node, primitive_actions)


def _edf_compute_nav_time(
    subtask: Subtask,
    current_state: SchedulerState,
    action_handler: ActionHandler,
) -> tuple[float, Mapping[str, Position]]:
    """Compute the first navigation duration exactly like the EDF baseline."""

    primitive_actions = subtask.execution.primitive_actions if subtask.execution else None
    if not primitive_actions:
        return 0.0, current_state.scene_positions
    first_action = primitive_actions[0]
    if not first_action.startswith("NAVIGATE_TO"):
        return 0.0, current_state.scene_positions
    nav_info = action_handler.get_actions_info(
        SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
            state=current_state,
            risk_level=0,
        ),
        [first_action],
    )
    if nav_info is None:
        return 0.0, current_state.scene_positions
    return float(nav_info.cumulative_time), nav_info.scene_positions


def _edf_offline_subtask_execution(
    subtask: Subtask,
    current_state: SchedulerState,
    action_handler: ActionHandler,
) -> Optional[ActionResult]:
    """Simulate the full subtask exactly like the EDF baseline."""

    return _simulate_subtask_actions(current_state, subtask, action_handler)


def _edf_update_state(
    current_state: SchedulerState,
    next_subtask: Subtask,
    exec_info: ActionResult,
    nav_time: Optional[float] = None,
) -> SchedulerState:
    """Append a completed entry exactly like the EDF baseline."""

    subtask_duration = float(exec_info.cumulative_time)
    subtask_entry = CompletedEntry(
        subtask=next_subtask,
        schedule_start_time=current_state.current_time,
        schedule_end_time=current_state.current_time + subtask_duration,
        schedule_nav_time=nav_time,
        execution_status=TaskExecutionStatus.SUCCESS,
    )
    new_completed = current_state.completed_entries + [subtask_entry]
    new_remaining = [
        subtask
        for subtask in current_state.remaining_subtasks
        if subtask.name != next_subtask.name
    ]
    held_object = exec_info.held_object if exec_info.held_object is not None else current_state.held_object
    return SchedulerState(
        subtask=next_subtask,
        completed_entries=new_completed,
        remaining_subtasks=new_remaining,
        constraints=current_state.constraints,
        current_time=current_state.current_time + subtask_duration,
        scene_positions=copy.deepcopy(exec_info.scene_positions),
        held_object=held_object,
        agent_location=current_state.agent_location,
    )


def _edf_is_executable(subtask: Subtask, current_state: SchedulerState) -> bool:
    """Mirror the baseline executable check for EDF."""

    incoming = list(current_state.constraints.in_edges(subtask.name))
    if incoming:
        predecessor_name = incoming[0][0]
        completed = {entry.subtask.name for entry in current_state.completed_entries}
        return predecessor_name in completed
    return True


def _edf_nav_and_wait_during_interval(
    current_state: SchedulerState,
    interval: float,
    next_subtask: Subtask,
    action_handler: ActionHandler,
) -> tuple[SchedulerState, bool]:
    """Insert NAVIGATE and WAIT entries exactly like the EDF baseline."""

    entries: list[CompletedEntry] = []
    current_time = current_state.current_time
    primitive_actions = next_subtask.execution.primitive_actions if next_subtask.execution else None
    if not primitive_actions:
        return current_state, False
    first_action = primitive_actions[0]
    if not first_action.startswith("NAVIGATE_TO"):
        return current_state, False

    nav_time, nav_positions = _edf_compute_nav_time(
        next_subtask,
        current_state,
        action_handler,
    )
    if 0.0 < nav_time <= interval:
        nav_subtask = Subtask(
            task_name=next_subtask.task_name,
            name=f"NAVIGATE_TO_{first_action.split()[1]}",
            repetition=1,
            subtask_type="NAVIGATE",
            execution=Execution(objects={}, primitive_actions=[first_action]),
            duration=Duration(type="NAVIGATE", interval=nav_time),
            temporal_constraints=[],
        )
        nav_entry = CompletedEntry(
            subtask=nav_subtask,
            schedule_start_time=current_time,
            schedule_end_time=current_time + nav_time,
            schedule_nav_time=nav_time,
            execution_status=TaskExecutionStatus.SUCCESS,
        )
        entries.append(nav_entry)
        current_time += nav_time

    wait_time = interval - nav_time
    if wait_time >= 0:
        wait_subtask = Subtask(
            task_name=next_subtask.task_name,
            name=f"WAIT {wait_time} to {next_subtask.name}",
            repetition=1,
            subtask_type="WAIT",
            execution=Execution(objects={}, primitive_actions=[f"WAIT {wait_time}"]),
            duration=Duration(type="WAIT", interval=wait_time),
            temporal_constraints=[],
        )
        wait_entry = CompletedEntry(
            subtask=wait_subtask,
            schedule_start_time=current_time,
            schedule_end_time=current_time + wait_time,
            execution_status=TaskExecutionStatus.SUCCESS,
        )
        entries.append(wait_entry)
        return (
            SchedulerState(
                subtask=current_state.subtask,
                completed_entries=current_state.completed_entries + entries,
                remaining_subtasks=current_state.remaining_subtasks,
                constraints=current_state.constraints,
                current_time=current_time + wait_time,
                scene_positions=copy.deepcopy(dict(nav_positions)),
                held_object=current_state.held_object,
                agent_location=current_state.agent_location,
            ),
            True,
        )
    return current_state, False


def _edf_compute_deadline(
    subtask: Subtask,
    current_state: SchedulerState,
    nav_time: float,
    execution_time: float,
) -> float:
    """Compute the EDF release target using interaction-start semantics."""

    constraints = current_state.constraints
    current_time = current_state.current_time
    incoming_edges = list(constraints.in_edges(subtask.name, data=True))
    deadline = current_time + execution_time
    if incoming_edges:
        critical_edges = [
            (source_name, target_name, data)
            for source_name, target_name, data in incoming_edges
            if data.get("info", {}).get("IsCritical", False)
        ]
        if critical_edges:
            critical_deadlines = []
            for source_name, _, data in critical_edges:
                predecessor_end_time = next(
                    (
                        entry.schedule_end_time
                        for entry in current_state.completed_entries
                        if entry.subtask.name == source_name
                    ),
                    current_time,
                )
                critical_deadlines.append(
                    predecessor_end_time + float(data["info"]["Interval"])
                )
            deadline = max(critical_deadlines)
        else:
            non_critical_deadlines = []
            for source_name, _, data in incoming_edges:
                predecessor_end_time = next(
                    (
                        entry.schedule_end_time
                        for entry in current_state.completed_entries
                        if entry.subtask.name == source_name
                    ),
                    current_time,
                )
                non_critical_deadlines.append(
                    predecessor_end_time + float(data["info"]["Interval"])
                )
            deadline = max(non_critical_deadlines)
    return deadline


def _edf_select_next_subtask(
    current_state: SchedulerState,
    action_handler: ActionHandler,
) -> Optional[Subtask]:
    """Select the next subtask exactly like the EDF baseline."""

    queue: list[tuple[float, int, Subtask]] = []
    for subtask in current_state.remaining_subtasks:
        if not _edf_is_executable(subtask, current_state):
            continue
        nav_time, _ = _edf_compute_nav_time(subtask, current_state, action_handler)
        exec_info = _edf_offline_subtask_execution(subtask, current_state, action_handler)
        if exec_info is None:
            continue
        execution_time = float(exec_info.cumulative_time)
        deadline = _edf_compute_deadline(
            subtask,
            current_state,
            nav_time,
            execution_time,
        )
        setattr(subtask, "deadline", deadline)
        heapq.heappush(queue, (deadline, len(queue), subtask))
    if not queue:
        return None
    chosen_subtask = heapq.heappop(queue)[2]
    chosen_exec_info = _edf_offline_subtask_execution(
        chosen_subtask,
        current_state,
        action_handler,
    )
    if chosen_exec_info is not None:
        chosen_subtask.duration.interval = float(chosen_exec_info.cumulative_time)
    return chosen_subtask


def _edf_update(
    current_state: SchedulerState,
    next_subtask: Subtask,
    action_handler: ActionHandler,
) -> SchedulerState:
    """Update EDF state exactly like the baseline implementation."""

    current_time = current_state.current_time
    incoming_edges = list(current_state.constraints.in_edges(next_subtask.name, data=True))
    designated_start = current_time
    nav_time, _ = _edf_compute_nav_time(next_subtask, current_state, action_handler)
    if incoming_edges:
        designated_start = float(getattr(next_subtask, "deadline", current_time))
        if current_time < designated_start:
            interval = designated_start - current_time
            current_state, inserted_nav_and_wait = _edf_nav_and_wait_during_interval(
                current_state,
                interval,
                next_subtask,
                action_handler,
            )
            if inserted_nav_and_wait:
                nav_time = 0.0
    exec_info = _edf_offline_subtask_execution(next_subtask, current_state, action_handler)
    if exec_info is None:
        raise ValueError(f"Failed to simulate EDF subtask: {next_subtask.name}")
    return _edf_update_state(current_state, next_subtask, exec_info, nav_time)


def run_single_rollout_edf(
    config: ExperimentConfig,
    task: ExperimentTask,
    *,
    nav_graph: NavGraph,
    scene_positions: Mapping[str, Position],
) -> dict[str, Any]:
    """Execute one offline rollout using the EDF baseline policy."""

    task_data = load_task_data_from_sampled_set(
        task.case or config.case,
        config.scene,
        task.instruction,
    )
    subtasks, constraints, _ = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{config.scene}_physics_environment.json",
    )
    current_state = TaskUtil.get_init_state(
        subtasks,
        constraints,
        copy.deepcopy(dict(scene_positions)),
    )
    action_handler = ActionHandler(nav_graph, real_world_mode=False)

    total_compute_time = 0.0
    aborted = False
    abort_reason = ""

    while current_state.remaining_subtasks:
        selection_started_at = perf_counter()
        selected = _edf_select_next_subtask(current_state, action_handler)
        total_compute_time += perf_counter() - selection_started_at
        if selected is None:
            aborted = True
            abort_reason = "no_feasible_solution"
            break

        current_state = _edf_update(current_state, selected, action_handler)
        if len(current_state.completed_entries) > 500:
            aborted = True
            abort_reason = "step_guard_exceeded"
            break

    _copy_schedule_to_sim_fields(current_state)
    _, schedule_tcsr, detail_log = calculate_timing_success_rate(
        current_state.constraints,
        current_state.completed_entries,
    )
    steps = [
        {
            "subtask_name": entry.subtask.name,
            "subtask_type": entry.subtask.subtask_type,
            "schedule_end_time": entry.schedule_end_time,
            "schedule_nav_time": entry.schedule_nav_time,
            "monitored_subtask": None,
        }
        for entry in current_state.completed_entries[1:]
    ]
    wait_count = sum(1 for entry in current_state.completed_entries if entry.subtask.subtask_type == "WAIT")
    action_count = sum(
        1
        for entry in current_state.completed_entries
        if entry.subtask.subtask_type not in {"WAIT", "Monitor", "Init"}
    )
    return {
        "case": task.case or config.case,
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
        "monitor_count": 0,
        "replanning_count": 1 if steps else 0,
        "avg_committed_steps_per_replan": float(len(steps)) if steps else 0.0,
        "steps": steps,
        "timing_detail": detail_log,
        "ground_truth_intervals": {},
    }


def run_single_rollout_cpm(
    config: ExperimentConfig,
    task: ExperimentTask,
    *,
    nav_graph: NavGraph,
    scene_positions: Mapping[str, Position],
) -> dict[str, Any]:
    """Execute one offline rollout using the CPM baseline policy."""

    from src.baselines import cpm as cpm_baseline

    task_data = load_task_data_from_sampled_set(
        task.case or config.case,
        config.scene,
        task.instruction,
    )
    subtasks, constraints, _ = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{config.scene}_physics_environment.json",
        enable_decomposition=True,
    )
    cpm_baseline.constraints = constraints
    current_state = TaskUtil.get_init_state(
        subtasks,
        constraints,
        copy.deepcopy(dict(scene_positions)),
    )
    action_handler = ActionHandler(nav_graph, real_world_mode=False)

    subtasks_without_edge = [
        subtask
        for subtask in subtasks
        if all(
            subtask.name != source_name and subtask.name != target_name
            for source_name, target_name in list(constraints.edges)
        )
    ]

    planning_started_at = perf_counter()
    critical_path = cpm_baseline.find_critical_path(subtasks)
    result_schedule = cpm_baseline.get_final_entries(
        critical_path,
        subtasks_without_edge,
        current_state,
        action_handler,
    )
    total_compute_time = perf_counter() - planning_started_at

    current_state = TaskUtil.get_init_state(
        subtasks,
        constraints,
        copy.deepcopy(dict(scene_positions)),
    )
    for entry in result_schedule:
        exec_info = cpm_baseline.offline_subtask_execution(
            current_state,
            entry.subtask,
            action_handler,
        )
        current_state = cpm_baseline.update_state(current_state, entry.subtask, exec_info)

    _copy_schedule_to_sim_fields(current_state)
    _, schedule_tcsr, detail_log = calculate_timing_success_rate(
        current_state.constraints,
        current_state.completed_entries,
    )
    steps = [
        {
            "subtask_name": entry.subtask.name,
            "subtask_type": entry.subtask.subtask_type,
            "schedule_end_time": entry.schedule_end_time,
            "schedule_nav_time": entry.schedule_nav_time,
            "monitored_subtask": None,
        }
        for entry in result_schedule
    ]
    wait_count = sum(1 for entry in result_schedule if entry.subtask.subtask_type == "WAIT")
    action_count = sum(
        1 for entry in result_schedule if entry.subtask.subtask_type not in {"WAIT", "Monitor"}
    )
    return {
        "case": task.case or config.case,
        "instruction": task.instruction,
        "beam_width": task.beam_width,
        "beam_depth": task.beam_depth,
        "completed": True,
        "abort_reason": "",
        "total_compute_time": total_compute_time,
        "final_schedule_time": current_state.current_time,
        "schedule_tcsr": schedule_tcsr,
        "action_count": action_count,
        "wait_count": wait_count,
        "monitor_count": 0,
        "replanning_count": 1 if steps else 0,
        "avg_committed_steps_per_replan": float(len(steps)) if steps else 0.0,
        "steps": steps,
        "timing_detail": detail_log,
        "ground_truth_intervals": {},
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
        replanning_counts = [int(row["replanning_count"]) for row in rows]
        committed_steps = [
            float(row["avg_committed_steps_per_replan"]) for row in rows
        ]
        summary[beam_key] = {
            "num_runs": len(rows),
            "completed_runs": len(completed_rows),
            "avg_schedule_time": mean(schedule_times) if schedule_times else None,
            "median_schedule_time": median(schedule_times) if schedule_times else None,
            "avg_compute_time": mean(compute_times) if compute_times else None,
            "avg_schedule_tcsr": mean(tcsr_values) if tcsr_values else None,
            "avg_wait_count": mean(wait_counts) if wait_counts else None,
            "avg_monitor_count": mean(monitor_counts) if monitor_counts else None,
            "avg_replanning_count": (
                mean(replanning_counts) if replanning_counts else None
            ),
            "avg_committed_steps_per_replan": (
                mean(committed_steps) if committed_steps else None
            ),
        }
    return summary


def summarize_results_by_case_setting(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate per-run results at the case-setting level.

    Args:
        results: Rollout result rows.

    Returns:
        Mapping keyed by ``case:wX_dY`` to aggregated metrics.
    """

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        beam_key = f"w{int(result['beam_width'])}_d{int(result['beam_depth'])}"
        case_key = f"{result['case']}:{beam_key}"
        grouped.setdefault(case_key, []).append(result)

    summary: dict[str, dict[str, Any]] = {}
    for case_key, rows in grouped.items():
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
        replanning_counts = [int(row["replanning_count"]) for row in rows]
        committed_steps = [
            float(row["avg_committed_steps_per_replan"]) for row in rows
        ]
        summary[case_key] = {
            "num_runs": len(rows),
            "completed_runs": len(completed_rows),
            "avg_schedule_time": mean(schedule_times) if schedule_times else None,
            "median_schedule_time": median(schedule_times) if schedule_times else None,
            "avg_compute_time": mean(compute_times) if compute_times else None,
            "avg_schedule_tcsr": mean(tcsr_values) if tcsr_values else None,
            "avg_wait_count": mean(wait_counts) if wait_counts else None,
            "avg_monitor_count": mean(monitor_counts) if monitor_counts else None,
            "avg_replanning_count": (
                mean(replanning_counts) if replanning_counts else None
            ),
            "avg_committed_steps_per_replan": (
                mean(committed_steps) if committed_steps else None
            ),
        }
    return summary


def compare_ready_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build compact comparison helpers from run results."""

    best_by_task: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        task_key = f"{result['case']}::{result['instruction']}"
        grouped.setdefault(task_key, []).append(result)

    for task_key, rows in grouped.items():
        best_row = sorted(
            rows,
            key=lambda row: (row["final_schedule_time"], row["total_compute_time"]),
        )[0]
        best_by_task[task_key] = {
            "case": best_row["case"],
            "instruction": best_row["instruction"],
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
        nav_graph = resolve_nav_graph(config, scene_positions)
        tasks = build_experiment_tasks(config)
        selected_instructions = build_selected_instruction_map(config)
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
            "selected_instructions": selected_instructions,
            "summary_by_setting": summarize_results(results),
            "summary_by_case_setting": summarize_results_by_case_setting(results),
            "comparison": compare_ready_summary(results),
            "results": results,
        }
    finally:
        _restore_runtime_overrides(previous_values)


def _build_deterministic_scheduler_config(config: ExperimentConfig) -> ExperimentConfig:
    """Build a monitoring-free deterministic config for oracle comparison.

    Args:
        config: User-provided experiment configuration.

    Returns:
        Copy of the config aligned with deterministic initial-schedule comparison.
    """

    merged = asdict(config)
    merged["disable_monitoring"] = True
    merged["gt_distribution"] = "constant"
    merged["schema_version"] = "offline_harness.v1"
    return ExperimentConfig(**merged)


def _build_oracle_task_key(case_name: str, instruction: str) -> str:
    """Return a stable lookup key for an instruction inside a case."""

    return f"{case_name}::{instruction}"


def _run_exact_oracle_rollout(
    config: ExperimentConfig,
    *,
    case_name: str,
    instruction: str,
    nav_graph: NavGraph,
    scene_positions: Mapping[str, Position],
    incumbent_upper_bound: Optional[float],
) -> dict[str, Any]:
    """Run the deterministic exact oracle for one instruction.

    Args:
        config: Deterministic experiment config.
        case_name: Case identifier.
        instruction: Instruction file name.
        nav_graph: Deterministic navigation graph.
        scene_positions: Scene positions for the selected floorplan.
        incumbent_upper_bound: Optional incumbent makespan for pruning.

    Returns:
        JSON-serializable oracle result dictionary.
    """

    task_data = load_task_data_from_sampled_set(
        case_name,
        config.scene,
        instruction,
    )
    subtasks, constraints, _ = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{config.scene}_physics_environment.json",
    )
    initial_state = TaskUtil.get_init_state(
        subtasks,
        constraints,
        copy.deepcopy(dict(scene_positions)),
    )
    action_handler = ActionHandler(nav_graph, real_world_mode=False)
    constraint_handler = ConstraintHandler(action_handler)
    oracle = DeterministicExactOracle(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=HeuristicManager(action_handler),
        time_limit_seconds=config.oracle_time_limit_seconds,
    )
    return oracle.solve(
        initial_state,
        instruction=instruction,
        case=case_name,
        incumbent_upper_bound=build_initial_oracle_upper_bound(incumbent_upper_bound),
    ).as_dict()


def summarize_oracle_results(
    oracle_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate deterministic oracle results across instructions.

    Args:
        oracle_results: Per-instruction oracle rows.

    Returns:
        Compact summary dictionary for reporting.
    """

    schedule_times = [
        float(row["optimal_schedule_time"])
        for row in oracle_results
        if row["optimal_schedule_time"] is not None
    ]
    solve_times = [float(row["solve_time"]) for row in oracle_results]
    exact_count = sum(1 for row in oracle_results if bool(row["exact"]))
    return {
        "num_instructions": len(oracle_results),
        "exact_instructions": exact_count,
        "avg_optimal_schedule_time": mean(schedule_times) if schedule_times else None,
        "avg_solve_time": mean(solve_times) if solve_times else None,
    }


def summarize_oracle_gaps(
    scheduler_results: Sequence[Mapping[str, Any]],
    oracle_results: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate scheduler-oracle gaps by beam setting.

    Args:
        scheduler_results: Deterministic scheduler rollout rows.
        oracle_results: Per-instruction oracle rows.

    Returns:
        Beam-setting summary including absolute and relative oracle gaps.
    """

    oracle_by_task = {
        _build_oracle_task_key(str(row["case"]), str(row["instruction"])): row
        for row in oracle_results
    }
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in scheduler_results:
        beam_key = f"w{int(row['beam_width'])}_d{int(row['beam_depth'])}"
        grouped.setdefault(beam_key, []).append(row)

    summary: dict[str, dict[str, Any]] = {}
    for beam_key, rows in grouped.items():
        scheduler_times: list[float] = []
        oracle_times: list[float] = []
        absolute_gaps: list[float] = []
        relative_gaps: list[float] = []
        exact_matches = 0
        for row in rows:
            oracle_row = oracle_by_task.get(
                _build_oracle_task_key(str(row["case"]), str(row["instruction"]))
            )
            if oracle_row is None or oracle_row["optimal_schedule_time"] is None:
                continue
            scheduler_time = float(row["final_schedule_time"])
            oracle_time = float(oracle_row["optimal_schedule_time"])
            absolute_gap = scheduler_time - oracle_time
            relative_gap = (
                absolute_gap / oracle_time if abs(oracle_time) > constants.EPSILON else 0.0
            )
            scheduler_times.append(scheduler_time)
            oracle_times.append(oracle_time)
            absolute_gaps.append(absolute_gap)
            relative_gaps.append(relative_gap)
            if bool(oracle_row["exact"]):
                exact_matches += 1

        summary[beam_key] = {
            "num_runs": len(rows),
            "matched_oracle_runs": len(absolute_gaps),
            "exact_oracle_runs": exact_matches,
            "avg_scheduler_time": mean(scheduler_times) if scheduler_times else None,
            "avg_oracle_time": mean(oracle_times) if oracle_times else None,
            "avg_absolute_gap": mean(absolute_gaps) if absolute_gaps else None,
            "avg_relative_gap": mean(relative_gaps) if relative_gaps else None,
        }
    return summary


def run_oracle_comparison_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Compare deterministic scheduler rollouts against an exact oracle.

    Args:
        config: User experiment configuration. Monitoring is disabled internally
            to align with the deterministic oracle definition.

    Returns:
        Structured report containing scheduler results, oracle results, and gap
        summaries.
    """

    deterministic_config = _build_deterministic_scheduler_config(config)
    scheduler_report = run_grid_experiment(deterministic_config)
    previous_values = _apply_runtime_overrides(deterministic_config)
    try:
        scene_positions = load_scene_positions(f"{deterministic_config.scene}_positions.json")
        nav_graph = resolve_nav_graph(deterministic_config, scene_positions)
        best_by_task = scheduler_report["comparison"]["best_by_task"]
        oracle_results: list[dict[str, Any]] = []
        for case_name, instructions in build_selected_instruction_map(
            deterministic_config
        ).items():
            for instruction in instructions:
                task_key = _build_oracle_task_key(case_name, instruction)
                incumbent = best_by_task.get(task_key, {}).get("final_schedule_time")
                oracle_results.append(
                    _run_exact_oracle_rollout(
                        deterministic_config,
                        case_name=case_name,
                        instruction=instruction,
                        nav_graph=nav_graph,
                        scene_positions=scene_positions,
                        incumbent_upper_bound=incumbent,
                    )
                )
    finally:
        _restore_runtime_overrides(previous_values)

    return {
        "schema_version": "offline_oracle_comparison.v1",
        "saved_time": datetime.now().isoformat(timespec="seconds"),
        "experiment": {
            "name": config.experiment_name,
            "tags": list(config.tags),
        },
        "config": asdict(deterministic_config),
        "selected_instructions": scheduler_report["selected_instructions"],
        "scheduler_report": scheduler_report,
        "oracle_results": oracle_results,
        "oracle_summary": summarize_oracle_results(oracle_results),
        "gap_by_setting": summarize_oracle_gaps(
            scheduler_report["results"],
            oracle_results,
        ),
    }


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


def iter_oracle_report_lines(report: Mapping[str, Any]) -> Iterable[str]:
    """Yield a compact CLI preview for oracle comparison reports."""

    yield f"Experiment: {report['experiment']['name']}"
    oracle_summary = report["oracle_summary"]
    yield (
        "Oracle: "
        f"exact={oracle_summary['exact_instructions']}/{oracle_summary['num_instructions']}, "
        f"avg_optimal_schedule_time={oracle_summary['avg_optimal_schedule_time']}, "
        f"avg_solve_time={oracle_summary['avg_solve_time']}"
    )
    for setting, metrics in report["gap_by_setting"].items():
        yield (
            f"- {setting}: matched_oracle_runs={metrics['matched_oracle_runs']}/{metrics['num_runs']}, "
            f"avg_scheduler_time={metrics['avg_scheduler_time']}, "
            f"avg_oracle_time={metrics['avg_oracle_time']}, "
            f"avg_absolute_gap={metrics['avg_absolute_gap']}, "
            f"avg_relative_gap={metrics['avg_relative_gap']}"
        )
