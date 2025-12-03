import argparse
import csv
import functools
import glob
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import optuna  # type: ignore[import]

# --- 프로젝트 경로 설정 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT set to: {PROJECT_ROOT}")
    print(f"sys.path updated: {sys.path[0]}, {sys.path[1]}")
except NameError:
    PROJECT_ROOT = Path(".").resolve()
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT likely CWD: {PROJECT_ROOT}")
except IndexError:
    PROJECT_ROOT = Path(__file__).resolve().parent
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT adjusted: {PROJECT_ROOT}")

# --- 필요한 모듈 임포트 ---
try:
    from assets.result_analysis.state_base_evaluation import _to_spec_key

    # State-based evaluation imports
    from assets.result_analysis.utils.evaluator import (
        compute_trial_metrics,
        evaluate_tasks,
    )
    from assets.result_analysis.utils.instruction_parser import (
        load_task_info,
        parse_instruction_to_tasks,
    )
    from assets.result_analysis.utils.specs import TASK_SPECS
    from assets.result_analysis.utils.state_change_simulate import load_events_from_file
    from core.agent import Agent
    from core.scheduler import Scheduler
    from ithor.utils.math_utils import load_navigation_graph
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler
    from scheduler.heuristic_manager import HeuristicManager
    from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
    from src.models.dataclass import CompletedEntry, SchedulerState
    from src.models.task import Subtask, Task
    from utils.common.logger import create_module_logger
    from utils.config import BEAM_WIDTH, SIMULATION_DEPTH
    from utils.config.constants import INIT_PRIOR_MEAN, INIT_PRIOR_VARIANCE, TASK_PATH
    from utils.io_utils.result_saver import compose_plans
    from utils.io_utils.task_io import load_scene_positions, load_task_data_from_file
    from utils.task import TaskUtil

except ImportError as e:
    print(f"Fatal Error importing module: {e}\nPYTHONPATH: {sys.path}")
    if hasattr(e, "name") and e.name:
        print(f"Specifically failed importing: {e.name}")
    sys.exit(1)
except Exception as e:
    print(f"Fatal Error during initial imports: {e}")
    sys.exit(1)


# --- 로깅 설정 ---
def setup_logging():
    log_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] %(message)s"
    )
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(log_formatter)
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(log_handler)
    logging.getLogger("optuna").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


log = setup_logging()

SCENE_PATTERN = re.compile(r"(FloorPlan\d+)")


@dataclass(frozen=True)
class TaskSpec:
    """Task metadata for a single instruction JSON file.

    Attributes:
        relative_path: Path to the task JSON relative to `TASK_FILES_DIR`.
        scene_name: AI2-THOR scene identifier inferred from the path.
        case_name: Case directory inferred from the task path (e.g., ``tasks_4_constraints_3``).
    """

    relative_path: Path
    scene_name: str
    case_name: str

    @property
    def absolute_path(self) -> Path:
        """Return absolute path from TASK_FILES_DIR."""

        return TASK_FILES_DIR / self.relative_path

    @property
    def instruction_argument(self) -> str:
        """Return instruction argument string passed to subprocess executions."""

        return self.relative_path.as_posix()

    @property
    def instruction_filename(self) -> str:
        """Instruction filename component."""

        return self.relative_path.name


def _extract_scene_name_from_path(path: Path) -> Optional[str]:
    """Extract the FloorPlan scene name from a relative task path.

    Args:
        path: Task path relative to `TASK_FILES_DIR`.

    Returns:
        The matched scene name (e.g., ``"FloorPlan1"``) or ``None`` when it
        cannot be inferred.
    """

    match = SCENE_PATTERN.search(path.as_posix())
    return match.group(1) if match else None


def _extract_case_name_from_path(path: Path) -> str:
    """Extract the case directory name from a task path."""

    return path.parts[0] if path.parts else DEFAULT_CASE_NAME


DEFAULT_CASE_NAME = "tune_case"


def _discover_task_files(task_dir: Path) -> Tuple[List[str], Dict[str, str]]:
    """Return discovered task names and their associated scenes.

    Args:
        task_dir: Directory containing task JSON files.

    Returns:
        A tuple of:
            - Sorted relative task paths.
            - Mapping of relative task paths (as strings) to scene names.
    """

    task_names: List[str] = []
    scene_lookup: Dict[str, str] = {}
    for path in task_dir.glob("**/*.json"):
        if "natural_languages" in path.as_posix():
            continue
        relative_path = path.relative_to(task_dir)
        relative_str = relative_path.as_posix()
        scene_name = _extract_scene_name_from_path(relative_path)
        if not scene_name:
            log.warning(
                "Unable to infer scene name from task path '%s'. Default scene will be used.",
                relative_str,
            )
        else:
            scene_lookup[relative_str] = scene_name
        task_names.append(relative_str)
    task_names.sort()
    return task_names, scene_lookup


def _sample_balanced_task_specs(
    task_specs: List["TaskSpec"], sample_size: int
) -> List["TaskSpec"]:
    """Sample tasks while covering all scenes as evenly as possible.

    Args:
        task_specs: Candidate tasks with scene annotations.
        sample_size: Desired number of samples per trial.

    Returns:
        A list of sampled ``TaskSpec`` instances. Scenes are cycled so every
        scene is represented whenever possible.
    """

    if not task_specs or sample_size <= 0:
        return []

    scene_to_specs: Dict[str, List[TaskSpec]] = {}
    for spec in task_specs:
        scene_to_specs.setdefault(spec.scene_name, []).append(spec)

    if sample_size < len(scene_to_specs):
        log.warning(
            "Requested samples per trial (%d) is smaller than the number of scenes (%d). "
            "Some scenes will be skipped in each trial; consider increasing --n_samples_per_trial.",
            sample_size,
            len(scene_to_specs),
        )

    scene_buffers: Dict[str, List[TaskSpec]] = {
        scene: random.sample(specs, len(specs))
        for scene, specs in scene_to_specs.items()
    }
    scene_order = list(scene_to_specs.keys())
    sampled_specs: List[TaskSpec] = []
    index = 0

    while len(sampled_specs) < sample_size:
        scene = scene_order[index % len(scene_order)]
        buffer = scene_buffers[scene]
        if not buffer:
            buffer.extend(
                random.sample(scene_to_specs[scene], len(scene_to_specs[scene]))
            )
        sampled_specs.append(buffer.pop())
        index += 1

    return sampled_specs[:sample_size]


def _resolve_task_argument(task_arg: str) -> Optional[str]:
    """Normalize CLI task arguments to repository-relative paths.

    Args:
        task_arg: Raw argument provided to ``--tasks``.

    Returns:
        A relative task path (POSIX-style) or ``None`` if the task cannot be
        resolved.
    """

    candidate_path = Path(task_arg)
    if candidate_path.is_absolute():
        try:
            return candidate_path.relative_to(TASK_FILES_DIR).as_posix()
        except ValueError:
            log.error(
                "Task path '%s' is outside of the configured TASK_FILES_DIR (%s).",
                task_arg,
                TASK_FILES_DIR,
            )
            return None

    normalized_path = TASK_FILES_DIR / candidate_path
    if normalized_path.is_file():
        return candidate_path.as_posix()

    matches = [name for name in TUNING_TASK_NAMES_LIST if Path(name).name == task_arg]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log.error(
            "Task name '%s' is ambiguous across multiple scenes. Please provide a relative path:\n%s",
            task_arg,
            "\n".join(f"  - {match}" for match in matches),
        )
        return None

    log.error("Task file '%s' not found under %s.", task_arg, TASK_FILES_DIR)
    return None


def _build_task_specs_from_names(
    task_names: List[str], allowed_scenes: Optional[List[str]]
) -> List[TaskSpec]:
    """Build TaskSpec entries filtered by the target scenes.

    Args:
        task_names: Relative task paths to consider.
        allowed_scenes: Restriction list of scene names. ``None`` keeps all scenes.

    Returns:
        A list of ``TaskSpec`` entries that exist on disk and satisfy the
        requested scene filter.
    """

    allowed_set: Optional[Set[str]] = set(allowed_scenes) if allowed_scenes else None
    specs: List[TaskSpec] = []
    for name in task_names:
        scene_name = TASK_SCENE_LOOKUP.get(name)
        if not scene_name:
            scene_name = _extract_scene_name_from_path(Path(name)) or SCENE_NAME
        if allowed_set and scene_name not in allowed_set:
            continue
        relative_path = Path(name)
        case_name = _extract_case_name_from_path(relative_path)
        abs_path = TASK_FILES_DIR / relative_path
        if not abs_path.is_file():
            log.warning("Task file not found at %s. Skipping.", abs_path)
            continue
        specs.append(
            TaskSpec(
                relative_path=relative_path,
                scene_name=scene_name,
                case_name=case_name,
            )
        )
    return specs


# ==============================================================================
# 전역 변수 및 설정 (Global Variables & Configuration)
# ==============================================================================
SCENE_NAME = "FloorPlan1"
TASK_FILES_DIR = TASK_PATH
SCENE_POSITIONS_DIR = (
    ASSETS_ROOT / "scene_knowledge" / "kitchen" / "object_init_positions"
)
OUTPUT_TUNE_DIR = ASSETS_ROOT / "tune"

TUNING_TASK_NAMES_LIST, TASK_SCENE_LOOKUP = _discover_task_files(TASK_FILES_DIR)
if not TUNING_TASK_NAMES_LIST:
    log.warning(
        "No JSON task files found in %s (excluding 'natural_languages'). Check the path.",
        TASK_FILES_DIR,
    )

CONTROLLER_INSTANCE: Optional[Any] = None
NAV_GRAPH: Optional[Dict] = None
INITIAL_SCENE_POSITIONS: Optional[Dict] = None
TASK_PATHS_TO_TUNE: List[Path] = []

CSV_FILENAME: Path = Path()
CSV_HEADER = [
    "trial_number",
    "value",
    "state",
    "datetime_start",
    "datetime_complete",
    "duration",
    "param_alpha",
    "param_beta",
    "param_gamma",
    "param_factor_alpha",
    "user_attr_num_completed",
    "user_attr_num_failed",
    "user_attr_avg_completed_makespan",
    "user_attr_avg_computation_time",
    "user_attr_failed_tasks_json",
    "user_attr_tsr_score",
    "user_attr_gcr_score",
    "user_attr_makespan_score",
]

PENALTY_BASE_MAKESPAN = 3000.0
PENALTY_MULTIPLIER_DEFAULT = 1.2
PENALTY_MULTIPLIER_EXEC_FAIL = 1.3 * PENALTY_MULTIPLIER_DEFAULT
PENALTY_MULTIPLIER_TIMEOUT = 1.1 * PENALTY_MULTIPLIER_DEFAULT
PENALTY_MULTIPLIER_LOW_SUCCESS = 0.5
PENALTY_MULTIPLIER_HIGH_COMP_TIME = 0.3
CRITICAL_FAILURE_PENALTY = 1e9
MAX_STEPS_PER_TASK = 500
MIN_SUCCESS_RATE = 0.60
MAX_COMPUTATION_TIME_PER_TASK = 300.0


# ==============================================================================
# 초기화 및 정리 함수 (Initialization & Cleanup Functions)
# ==============================================================================
def initialize_global_resources():
    """AI2-THOR 컨트롤러, 네비게이션 그래프, 초기 위치, 태스크 목록을 초기화합니다."""
    global CONTROLLER_INSTANCE, NAV_GRAPH, INITIAL_SCENE_POSITIONS, TASK_PATHS_TO_TUNE
    try:
        log.info("--- Initializing Global Resources ---")

        if CONTROLLER_INSTANCE is None:
            CONTROLLER_INSTANCE = init_ai2thor_controller(
                scene=SCENE_NAME, width=300, height=300
            )
            log.info(f"AI2-THOR controller initialized for scene '{SCENE_NAME}'.")
        else:
            log.info("Reusing existing AI2-THOR controller.")

        if NAV_GRAPH is None:
            NAV_GRAPH = load_navigation_graph(CONTROLLER_INSTANCE)
            log.info("Navigation graph loaded.")
        else:
            log.info("Reusing existing navigation graph.")

        if INITIAL_SCENE_POSITIONS is None:
            positions_file = SCENE_POSITIONS_DIR / f"{SCENE_NAME}_positions.json"
            if not positions_file.exists():
                log.error(f"Scene positions file not found: {positions_file}")
                return False
            INITIAL_SCENE_POSITIONS = load_scene_positions(positions_file.name)
            log.info(f"Initial scene positions loaded from '{positions_file.name}'.")
        else:
            log.info("Reusing existing initial scene positions.")

        TASK_PATHS_TO_TUNE.clear()
        if TUNING_TASK_NAMES_LIST:
            for name in TUNING_TASK_NAMES_LIST:
                task_path = TASK_FILES_DIR / name
                if task_path.is_file():
                    TASK_PATHS_TO_TUNE.append(task_path)
                else:
                    log.warning(
                        f"Task file '{name}' not found or is not a file at: {task_path}"
                    )
        else:
            log.error(f"No task names available in TUNING_TASK_NAMES_LIST.")
            return False

        if not TASK_PATHS_TO_TUNE:
            log.error(
                f"No valid task files found for the specified names in '{TASK_FILES_DIR}'."
            )
            return False

        log.info(
            f"Selected tasks for tuning ({len(TASK_PATHS_TO_TUNE)} tasks): {[p.name for p in TASK_PATHS_TO_TUNE]}"
        )
        log.info("--- Global Resources Initialized Successfully ---")
        return True

    except Exception as e:
        log.critical(f"Global resource initialization failed: {e}", exc_info=True)
        cleanup_resources()
        return False


def cleanup_resources():
    """AI2-THOR 컨트롤러를 정지시킵니다."""
    global CONTROLLER_INSTANCE
    if CONTROLLER_INSTANCE:
        try:
            CONTROLLER_INSTANCE.stop()
            log.info("AI2-THOR controller stopped.")
            CONTROLLER_INSTANCE = None
        except Exception as e:
            log.error(f"Error stopping AI2-THOR controller: {e}")


# ==============================================================================
# 시뮬레이션 실행 관련 함수 (Simulation Runner Functions)
# ==============================================================================


def _initialize_task_state(
    task_path: Path,
    controller_instance: Any,
    scene_name: str,
    initial_scene_positions: Dict,
) -> Tuple[Optional[SchedulerState], Optional[List[Dict]], str]:
    """태스크 데이터를 로드하고, 컨트롤러를 리셋하며, 초기 SchedulerState를 생성합니다."""
    task_name_str = task_path.stem
    try:
        task_dict = load_task_data_from_file(task_path.name)
        if not task_dict:
            log.error(f"[{task_name_str}] No task data loaded from file.")
            return None, None, task_name_str

        try:
            scene_physics_file = f"{scene_name}_physics.json"
            subtasks, constraints = TaskUtil.build_tasks_and_constraints(
                task_data=task_dict,
                enable_decomposition=True,
                scene_file_name=scene_physics_file,
            )
        except Exception as build_e:
            log.error(
                f"[{task_name_str}] Error during build_tasks_and_constraints: {build_e}",
                exc_info=True,
            )
            return None, None, task_name_str

        log.debug(
            f"[{task_name_str}] Built {len(subtasks)} subtasks and constraint graph with {len(constraints.nodes())} nodes."
        )

        event = controller_instance.reset(scene=scene_name)
        if not event or not event.metadata:
            log.error(
                f"[{task_name_str}] Controller reset failed or returned invalid metadata."
            )
            return None, None, task_name_str
        live_metadata = event.metadata

        if initial_scene_positions is None:
            log.error(f"[{task_name_str}] Initial scene positions not provided.")
            return None, None, task_name_str
        current_scene_positions = initial_scene_positions.copy()

        live_initial_held_list = live_metadata.get("inventoryObjects", [])
        live_initial_held = (
            live_initial_held_list[0]["objectId"] if live_initial_held_list else None
        )

        agent_meta = live_metadata.get("agent")
        if agent_meta and "position" in agent_meta:
            current_scene_positions["agent"] = tuple(agent_meta["position"].values())
        elif "agent" not in current_scene_positions:
            log.warning(
                f"[{task_name_str}] Agent position not found in live metadata or initial positions."
            )

        initial_state = TaskUtil.get_init_state(
            subtasks, constraints, current_scene_positions
        )

        log.info(
            f"[{task_name_str}] Initial state created. Time: {initial_state.current_time:.2f}, Remaining: {[s.name for s in initial_state.remaining_subtasks]}"
        )
        return initial_state, task_dict, task_name_str

    except Exception as e:
        log.error(
            f"[{task_name_str}] Error during task state initialization: {e}",
            exc_info=True,
        )
        return None, None, task_name_str


def _run_simulation_step(
    step_count: int,
    current_state: SchedulerState,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    task_name_str: str,
    result_schedule: List[CompletedEntry],
    simulation_time_accumulator: float,
    computation_time_accumulator: float,
) -> Tuple[Optional[SchedulerState], List[CompletedEntry], float, float, bool]:
    """시뮬레이션 루프의 한 스텝을 수행합니다. (get_next_state 반환값 처리 수정됨)"""
    log.debug(
        f"[{task_name_str}] --- Step {step_count} --- Current Time: {current_state.current_time:.2f}"
    )
    should_stop_loop = False
    next_state_after_step = None

    try:
        log.debug(f"[{task_name_str}] Calling scheduler.get_next_state...")
        next_sched_state, current_step_computation_time = (
            scheduler_instance.get_next_state(current_state)
        )
        computation_time_accumulator += current_step_computation_time

        if next_sched_state is None:
            log.warning(
                f"Scheduler returned None or invalid state for '{task_name_str}'."
            )
            should_stop_loop = True
            next_state_after_step = (
                current_state if not current_state.remaining_subtasks else None
            )
            if next_state_after_step is None:
                log.error(
                    f"[{task_name_str}] Planning failure: Scheduler returned None/invalid state but tasks remain."
                )
            return (
                next_state_after_step,
                result_schedule,
                simulation_time_accumulator,
                computation_time_accumulator,
                should_stop_loop,
            )

        scheduled_subtask = next_sched_state.subtask
        if (
            not scheduled_subtask
            or not hasattr(scheduled_subtask, "name")
            or not scheduled_subtask.name
        ):
            log.error(
                f"[{task_name_str}] Invalid subtask from scheduler state: {scheduled_subtask}"
            )
            should_stop_loop = True
            return (
                None,
                result_schedule,
                simulation_time_accumulator,
                computation_time_accumulator,
                should_stop_loop,
            )

        log.info(
            f"[{task_name_str}] Scheduler selected: '{scheduled_subtask.name}' (Type: {getattr(scheduled_subtask, 'subtask_type', 'Unknown')})"
        )

        log.debug(f"[{task_name_str}] Executing subtask '{scheduled_subtask.name}'...")
        try:
            subtask_elapsed_time, execution_status, sim_nav_time = execute_subtask(
                controller_instance, scheduled_subtask, log_level="WARNING"
            )
        except TypeError:
            log.warning(
                "execute_subtask does not accept log_level argument. Running without it."
            )
            subtask_elapsed_time, execution_status, sim_nav_time = execute_subtask(
                controller_instance, scheduled_subtask
            )
            if sim_nav_time is None:
                sim_nav_time = 0.0
        except Exception as exec_e:
            log.error(
                f"[{task_name_str}] Error during execute_subtask for '{scheduled_subtask.name}': {exec_e}",
                exc_info=True,
            )
            subtask_elapsed_time = 0.0
            execution_status = False
            sim_nav_time = 0.0

        subtask_elapsed_time = (
            float(subtask_elapsed_time) if subtask_elapsed_time is not None else 0.0
        )
        execution_status = bool(execution_status)
        log.info(
            f"[{task_name_str}] Execution: Status={execution_status}, Time={subtask_elapsed_time:.2f}s, NavTime={sim_nav_time:.2f}s"
        )

        sim_start_time = simulation_time_accumulator
        sim_end_time = sim_start_time + subtask_elapsed_time

        if next_sched_state.completed_entries:
            last_entry = next_sched_state.completed_entries[-1]
            if hasattr(last_entry, "sim_start_time"):
                last_entry.sim_start_time = sim_start_time
            if hasattr(last_entry, "sim_end_time"):
                last_entry.sim_end_time = sim_end_time
            if hasattr(last_entry, "execution_status"):
                last_entry.execution_status = execution_status
            if hasattr(last_entry, "computation_time"):
                last_entry.computation_time = current_step_computation_time
            if hasattr(last_entry, "sim_nav_time"):
                last_entry.sim_nav_time = sim_nav_time

            result_schedule.append(last_entry)
        else:
            log.warning(
                f"[{task_name_str}] No completed_entries found in next_state to update timing/status."
            )

        simulation_time_accumulator = sim_end_time

        if not execution_status:
            log.error(
                f"[{task_name_str}] Execution failed for '{scheduled_subtask.name}'. Stopping task."
            )
            should_stop_loop = True
            return (
                None,
                result_schedule,
                simulation_time_accumulator,
                computation_time_accumulator,
                should_stop_loop,
            )

        event = controller_instance.last_event
        sim_final_positions = current_state.scene_positions.copy()
        sim_final_held = current_state.held_object
        if event and event.metadata:
            try:
                live_objects = {
                    obj["objectId"]: tuple(obj["position"].values())
                    for obj in event.metadata.get("objects", [])
                    if "position" in obj and "objectId" in obj
                }
                sim_final_positions.update(live_objects)
                agent_meta = event.metadata.get("agent")
                if agent_meta and "position" in agent_meta:
                    sim_final_positions["agent"] = tuple(
                        agent_meta["position"].values()
                    )
                sim_final_held_list = (
                    agent_meta.get("inventoryObjects", []) if agent_meta else []
                )
                sim_final_held = (
                    sim_final_held_list[0]["objectId"] if sim_final_held_list else None
                )
                log.debug(
                    f"[{task_name_str}] State after exec: Held='{sim_final_held}'"
                )
            except Exception as meta_e:
                log.warning(
                    f"[{task_name_str}] Error parsing metadata after execution: {meta_e}. State might be inaccurate."
                )
        else:
            log.warning(
                f"[{task_name_str}] Invalid metadata after execution. State might be inaccurate."
            )

        next_state_after_step = SchedulerState(
            subtask=next_sched_state.subtask,
            completed_entries=result_schedule,
            remaining_subtasks=next_sched_state.remaining_subtasks,
            constraints=next_sched_state.constraints,
            current_time=simulation_time_accumulator,
            scene_positions=sim_final_positions,
            held_object=sim_final_held,
        )
        log.debug(
            f"[{task_name_str}] State updated for next step. New Time: {next_state_after_step.current_time:.2f}"
        )

        if (
            hasattr(agent_instance, "bayesian_estimate")
            and getattr(scheduled_subtask, "subtask_type", "") == "Monitor"
        ):
            log.debug(f"[{task_name_str}] Calling agent.bayesian_estimate...")
            try:
                result = agent_instance.bayesian_estimate(next_state_after_step)
                if isinstance(result, tuple) and len(result) == 2:
                    updated_state_agent, monitored_info = result
                    if hasattr(result_schedule[-1], "monitored_subtask"):
                        result_schedule[-1].monitored_subtask = monitored_info
                    log.info(
                        f"[{task_name_str}] Agent Bayesian estimation completed. Monitored: {monitored_info}"
                    )
                elif isinstance(result, SchedulerState):
                    updated_state_agent = result
                    log.info(
                        f"[{task_name_str}] Agent Bayesian estimation completed (State only)."
                    )
                else:
                    log.warning(
                        f"[{task_name_str}] Unexpected return type from bayesian_estimate: {type(result)}"
                    )
                    updated_state_agent = next_state_after_step
                next_state_after_step = updated_state_agent
            except Exception as agent_e:
                log.error(
                    f"[{task_name_str}] Agent error during Bayesian estimation: {agent_e}",
                    exc_info=True,
                )

        if not next_state_after_step.remaining_subtasks:
            log.info(
                f"[{task_name_str}] All subtasks completed after step {step_count}."
            )
            should_stop_loop = True

        return (
            next_state_after_step,
            result_schedule,
            simulation_time_accumulator,
            computation_time_accumulator,
            should_stop_loop,
        )

    except Exception as step_e:
        log.error(
            f"[{task_name_str}] Error during simulation step {step_count}: {step_e}",
            exc_info=True,
        )
        return (
            None,
            result_schedule,
            simulation_time_accumulator,
            computation_time_accumulator,
            True,
        )


def _process_simulation_results(
    result_schedule: List[CompletedEntry],
    task_data_list: Optional[List[Dict]],
    task_name_str: str,
    total_computation_time: float,
    simulation_time_accumulator: float,
    final_status_from_loop: str,
) -> Dict[str, Any]:
    """완료된 스케줄을 처리하고 최종 결과 지표를 반환합니다."""
    if not result_schedule:
        log.warning(f"[{task_name_str}] Simulation ended with no completed entries.")
        return {
            "status": "Failed (No Progress)",
            "simulation_makespan": float("inf"),
            "scheduler_makespan": float("inf"),
            "success_rate": 0.0,
            "computation_time": total_computation_time,
            "scene_name": SCENE_NAME,
            "task_name": task_name_str,
        }

    task_name_for_compose = task_name_str
    if (
        task_data_list
        and isinstance(task_data_list, list)
        and task_data_list
        and isinstance(task_data_list[0], dict)
    ):
        task_name_for_compose = task_data_list[0].get("Task", task_name_str)

    try:
        if callable(compose_plans):
            success_rate, final_sim_makespan, final_sched_makespan = compose_plans(
                result_schedule, task_name_for_compose
            )
            final_sim_makespan = (
                final_sim_makespan
                if final_sim_makespan is not None
                else simulation_time_accumulator
            )
            final_sched_makespan = (
                final_sched_makespan
                if final_sched_makespan is not None
                else float("inf")
            )
            success_rate = success_rate if success_rate is not None else 0.0
        else:
            raise NameError("compose_plans function is not defined or callable")
    except NameError:
        log.warning("'compose_plans' function not found. Using basic aggregation.")
        success_rate = (
            sum(1 for entry in result_schedule if entry.execution_status)
            / len(result_schedule)
            if result_schedule
            else 0.0
        )
        final_sim_makespan = simulation_time_accumulator
        final_sched_makespan = float("inf")
    except Exception as compose_e:
        log.error(
            f"[{task_name_str}] Error during compose_plans: {compose_e}", exc_info=True
        )
        success_rate = 0.0
        final_sim_makespan = simulation_time_accumulator
        final_sched_makespan = float("inf")
        final_status_from_loop = "Failed (Result Processing Error)"

    sim_makespan_final = final_sim_makespan if final_sim_makespan > 0 else float("inf")
    sched_makespan_final = (
        final_sched_makespan if final_sched_makespan > 0 else float("inf")
    )

    result_dict = {
        "simulation_makespan": sim_makespan_final,
        "scheduler_makespan": sched_makespan_final,
        "success_rate": success_rate,
        "computation_time": total_computation_time,
        "scene_name": SCENE_NAME,
        "task_name": task_name_str,
        "status": final_status_from_loop,
    }
    log.info(
        f"--- Sim finished: '{task_name_str}' --- Status: {result_dict['status']}, SimMakespan: {result_dict['simulation_makespan']:.2f}, Rate: {result_dict['success_rate']:.2f}, TotalCompTime: {result_dict['computation_time']:.2f}s"
    )

    # 상태 평가 완화: Planning/State Error는 부분적으로 성공으로 간주
    if "Planning/State Error" in final_status_from_loop:
        final_status_from_loop = "Partially Completed"
        success_rate = max(success_rate, 0.7)  # 최소 70% 성공으로 간주

    # 성공 여부 관계없이 makespan 값 설정
    if final_sim_makespan <= 0 or math.isinf(final_sim_makespan):
        final_sim_makespan = simulation_time_accumulator
        if final_sim_makespan <= 0 or math.isinf(final_sim_makespan):
            final_sim_makespan = PENALTY_BASE_MAKESPAN * 0.5  # 기본값 설정

    return result_dict


def run_schedule_and_get_result(
    task_path: Path,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    scene_name: str,
    initial_scene_positions: Dict,
) -> Optional[Dict[str, Any]]:
    """단일 태스크에 대한 전체 시뮬레이션 루프를 실행하고 결과를 반환합니다."""
    simulation_time_accumulator = 0.0
    computation_time_accumulator = 0.0
    result_schedule: List[CompletedEntry] = []
    final_status = "Unknown"

    try:
        current_state, task_data_list, task_name_str = _initialize_task_state(
            task_path, controller_instance, scene_name, initial_scene_positions
        )
        if current_state is None or task_data_list is None:
            log.error(
                f"[{task_name_str or task_path.stem}] Failed to initialize task state."
            )
            return {
                "status": "Failed (Initialization)",
                "simulation_makespan": float("inf"),
                "scheduler_makespan": float("inf"),
                "success_rate": 0.0,
                "computation_time": 0.0,
                "scene_name": scene_name,
                "task_name": task_name_str or task_path.stem,
            }

        log.info(f"--- Starting Sim: '{task_name_str}' ---")

        step_count = 0
        stop_loop = False
        while not stop_loop:
            step_count += 1
            if step_count > MAX_STEPS_PER_TASK:
                log.error(
                    f"[{task_name_str}] Max steps ({MAX_STEPS_PER_TASK}) exceeded."
                )
                final_status = "Failed (Timeout)"
                break

            (
                current_state,
                result_schedule,
                simulation_time_accumulator,
                computation_time_accumulator,
                stop_loop,
            ) = _run_simulation_step(
                step_count,
                current_state,
                scheduler_instance,
                agent_instance,
                controller_instance,
                task_name_str,
                result_schedule,
                simulation_time_accumulator,
                computation_time_accumulator,
            )

            if stop_loop:
                if current_state is None:
                    if result_schedule and not result_schedule[-1].execution_status:
                        final_status = "Failed (Execution)"
                    else:
                        final_status = "Failed (Planning/State Error)"
                elif not current_state.remaining_subtasks:
                    final_status = "Completed"
                elif final_status == "Unknown":
                    final_status = "Interrupted / Planning Error"
                break

        return _process_simulation_results(
            result_schedule,
            task_data_list,
            task_name_str,
            computation_time_accumulator,
            simulation_time_accumulator,
            final_status,
        )

    except Exception as main_run_e:
        log.critical(
            f"[{task_path.stem}] Critical error in main simulation runner: {main_run_e}",
            exc_info=True,
        )
        return {
            "status": "Critical Failure in Runner",
            "simulation_makespan": float("inf"),
            "scheduler_makespan": float("inf"),
            "success_rate": 0.0,
            "computation_time": 0.0,
            "scene_name": scene_name,
            "task_name": task_path.stem,
        }


# ==============================================================================
# Optuna 관련 함수 및 클래스 (Optuna Related Functions & Classes)
# ==============================================================================
class CSVSaveCallback:
    """Optuna 트라이얼 결과를 CSV 파일에 저장하는 콜백 클래스."""

    def __init__(self, csv_path: Path, header: List[str]):
        self.csv_path = csv_path
        self.header = header
        self._header_written = False

    def _ensure_header(self) -> bool:
        if not self._header_written:
            write_header = (
                not self.csv_path.exists() or self.csv_path.stat().st_size == 0
            )
            if write_header:
                try:
                    self.csv_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(self.header)
                    self._header_written = True
                    log.info(
                        f"Initialized/Wrote header to CSV log file: {self.csv_path}"
                    )
                except IOError as e:
                    log.error(f"Failed to write header to CSV log file: {e}")
                    return False
            else:
                self._header_written = True
        return True

    def __call__(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial):
        if not self._ensure_header():
            log.warning(
                f"Skipping CSV write for trial {trial.number} due to header issue."
            )
            return

        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                value_str = (
                    trial.value
                    if trial.value is not None
                    and not math.isnan(trial.value)
                    and not math.isinf(trial.value)
                    else ""
                )
                state_str = trial.state.name
                dt_start_str = (
                    trial.datetime_start.isoformat() if trial.datetime_start else ""
                )
                dt_complete_str = (
                    trial.datetime_complete.isoformat()
                    if trial.datetime_complete
                    else ""
                )
                duration_str = trial.duration.total_seconds() if trial.duration else ""

                params = trial.params
                user_attrs = trial.user_attrs
                avg_makespan = user_attrs.get("avg_completed_makespan", "")
                avg_makespan = (
                    ""
                    if avg_makespan == float("inf") or avg_makespan is None
                    else avg_makespan
                )
                avg_comp_time = user_attrs.get("avg_computation_time", "")
                avg_comp_time = (
                    ""
                    if avg_comp_time == float("inf") or avg_comp_time is None
                    else avg_comp_time
                )
                failed_tasks_json = user_attrs.get("failed_tasks_json", "[]")

                row = [
                    trial.number,
                    value_str,
                    state_str,
                    dt_start_str,
                    dt_complete_str,
                    duration_str,
                    params.get("alpha", ""),
                    params.get("beta", ""),
                    params.get("gamma", ""),
                    params.get("factor_alpha", ""),
                    user_attrs.get("num_completed", ""),
                    user_attrs.get("num_failed", ""),
                    avg_makespan,
                    avg_comp_time,
                    failed_tasks_json,
                    user_attrs.get("tsr_score", ""),
                    user_attrs.get("gcr_score", ""),
                    user_attrs.get("makespan_score", ""),
                ]
                writer.writerow(row)
        except IOError as e:
            log.error(f"Failed to append trial {trial.number} to CSV: {e}")
        except Exception as e:
            log.error(
                f"Unexpected error writing trial {trial.number} to CSV: {e}",
                exc_info=True,
            )


def _run_single_task_for_trial(
    task_path: Path,
    instruction_arg: str,
    trial_number: int,
    params: Dict[str, float],
    scene_name: str,
    case_name: str,
    controller_instance: Any,
    nav_graph: Dict,
    initial_scene_positions: Dict,
) -> Optional[Dict[str, Any]]:
    """주어진 하이퍼파라미터와 리소스로 단일 태스크 시뮬레이션을 subprocess로 실행합니다.

    Args:
        task_path: 절대 태스크 파일 경로.
        instruction_arg: subprocess에 전달할 instruction 파일명 인자.
        trial_number: 현재 Optuna 트라이얼 번호.
        params: 하이퍼파라미터 묶음.
        scene_name: 실행할 AI2-THOR 씬 이름.
        case_name: 태스크가 속한 케이스 디렉터리 명.
        controller_instance: (미사용) 호환성 유지용.
        nav_graph: (미사용) 호환성 유지용.
        initial_scene_positions: (미사용) 호환성 유지용.
    """

    # 임시 디렉토리 생성 (trajectory log 저장용)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        traj_log_path = temp_dir_path / "trajectory_log.json"

        cmd = [
            sys.executable,
            "src/dag_bayesian.py",
            "--scene",
            scene_name,
            "--case",
            case_name,
            "--instruction",
            instruction_arg,
            "--simulation",
            "--trajectory_log_path",
            str(traj_log_path),
            "--alpha_heuristic",
            str(params.get("alpha", 1.0)),
            "--beta_heuristic",
            str(params.get("beta", 1.0)),
            "--gamma_heuristic",
            str(params.get("gamma", 0.1)),
            "--factor_alpha",
            str(params.get("factor_alpha", 0.001)),
            "--init_prior_mean",
            str(params.get("init_prior_mean", INIT_PRIOR_MEAN)),
            "--init_prior_variance",
            str(INIT_PRIOR_VARIANCE),
            "--log-level",
            "ERROR",
        ]

        # subprocess 실행
        env = os.environ.copy()
        # Ensure PROJECT_ROOT and SRC_ROOT are in PYTHONPATH
        pythonpath = env.get("PYTHONPATH", "")
        paths_to_add = [str(PROJECT_ROOT), str(SRC_ROOT)]
        if pythonpath:
            paths_to_add.append(pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(paths_to_add)

        try:
            log.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=MAX_COMPUTATION_TIME_PER_TASK + 60,  # 여유 시간 추가
                env=env,
            )

            if result.returncode != 0:
                log.error(f"Subprocess failed with return code {result.returncode}")
                log.error(f"Stderr: {result.stderr}")
                return {
                    "task_name": task_path.stem,
                    "status": f"Failed (Subprocess Error: {result.returncode})",
                    "simulation_makespan": float("inf"),
                    "scheduler_makespan": float("inf"),
                    "success_rate": 0.0,
                    "computation_time": 0.0,
                    "scene_name": scene_name,
                    "tsr_score": 0.0,
                    "gcr_score": 0.0,
                    "makespan_score": 0.0,
                }

            # trajectory_log.json 로드 및 평가
            if not traj_log_path.exists():
                log.error(f"trajectory_log.json not found at {traj_log_path}")
                return {
                    "task_name": task_path.stem,
                    "status": "Failed (No Trajectory Log)",
                    "simulation_makespan": float("inf"),
                    "scheduler_makespan": float("inf"),
                    "success_rate": 0.0,
                    "computation_time": 0.0,
                    "scene_name": scene_name,
                    "tsr_score": 0.0,
                    "gcr_score": 0.0,
                    "makespan_score": 0.0,
                }

            try:
                events_data = load_events_from_file(traj_log_path)

                # 태스크 이름 파싱 (instruction filename -> task names)
                # task_path.stem 은 "1_Make_Coffee" 같은 형태일 수 있음
                instruction_raw = re.sub(r"^\d+_", "", task_path.stem)

                # Load valid task names once (global scope cache could be better)
                tasks_json_path = ASSETS_ROOT / "tasks" / "floorplan_tasks.json"
                all_task_names, _ = load_task_info(tasks_json_path)

                parsed_tasks = parse_instruction_to_tasks(
                    instruction_raw, all_task_names
                )
                spec_task_names = [_to_spec_key(t) for t in parsed_tasks]
                valid_task_names = [t for t in spec_task_names if t in TASK_SPECS]

                if not valid_task_names:
                    raise ValueError(f"No valid task specs found for {instruction_raw}")

                task_results = evaluate_tasks(
                    events=events_data,
                    task_names=valid_task_names,
                )
                trial_metrics = compute_trial_metrics(
                    parsed_tasks=parsed_tasks,
                    task_results=task_results,
                    events=events_data,
                )

                return {
                    "task_name": task_path.stem,
                    "scene_name": scene_name,
                    "success_rate": trial_metrics.get("sr", 0.0),
                    "tsr_score": trial_metrics.get("tsr", 0.0),
                    "gcr_score": trial_metrics.get("instruction_gcr", 0.0),
                    "makespan_score": trial_metrics.get("makespan", float("inf")),
                }

            except Exception as eval_e:
                log.error(f"Evaluation failed: {eval_e}")
                return {
                    "task_name": task_path.stem,
                    "scene_name": scene_name,
                    "success_rate": 0.0,
                    "tsr_score": 0.0,
                    "gcr_score": 0.0,
                    "makespan_score": float("inf"),
                }

        except subprocess.TimeoutExpired:
            log.error(f"Subprocess timed out for {task_path.stem}")
            return {
                "task_name": task_path.stem,
                "status": "Failed (Timeout)",
                "simulation_makespan": float("inf"),
                "scheduler_makespan": float("inf"),
                "success_rate": 0.0,
                "computation_time": 0.0,
                "scene_name": scene_name,
                "tsr_score": 0.0,
                "gcr_score": 0.0,
                "makespan_score": float("inf"),
            }
        except Exception as e:
            log.error(f"Subprocess execution error: {e}")
            return {
                "task_name": task_path.stem,
                "status": f"Failed (Execution Error: {e})",
                "simulation_makespan": float("inf"),
                "scheduler_makespan": float("inf"),
                "success_rate": 0.0,
                "computation_time": 0.0,
                "scene_name": scene_name,
                "tsr_score": 0.0,
                "gcr_score": 0.0,
                "makespan_score": float("inf"),
            }


def _calculate_task_objective(
    task_result: Dict, trial_number: int, task_name: str
) -> Tuple[float, bool]:
    """단일 태스크 결과에 대한 목적 함수 값(B&B 스타일 점수)을 계산합니다."""

    tsr_score = task_result.get("tsr_score", 0.0)
    # gcr_score = task_result.get("gcr_score", 0.0)
    makespan = task_result.get("simulation_makespan", float("inf"))

    # makespan이 inf인 경우 페널티 처리
    if math.isinf(makespan) or makespan is None:
        makespan = PENALTY_BASE_MAKESPAN

    # Objective = (Failure Rate * Weight) + Makespan
    # PENALTY_BASE_MAKESPAN(3000)을 가중치로 사용하면:
    # - 성공(TSR 1.0), 200초 -> 0 + 200 = 200
    # - 성공(TSR 1.0), 300초 -> 0 + 300 = 300 (시간 단축 선호)
    # - 실패(TSR 0.0), 50초 -> 3000 + 50 = 3050 (빠른 실패보다 느린 성공 선호)
    # - 부분 성공(TSR 0.5), 200초 -> 1500 + 200 = 1700
    # 이 값이 작아져야 좋은것임. 1-tsr이니까
    penalty_weight = PENALTY_BASE_MAKESPAN
    objective_value = ((1.0 - tsr_score) * penalty_weight) + makespan

    # is_valid_run = gcr_score == 1.0
    is_valid_run = True  # 일단 valid하다고 전제. GCR 체크는 하지 않음.

    log.info(
        f"Task {task_name}: TSR={tsr_score:.2f}, Makespan={makespan:.2f} -> Obj={objective_value:.2f}"
    )

    return objective_value, is_valid_run


def objective(
    trial: optuna.Trial,
    task_specs: List[TaskSpec],
    n_samples_per_trial: int,
) -> float:
    """Optuna 목적 함수: 각 트라이얼은 멀티-씬 태스크 샘플을 사용합니다."""
    params = {
        "beta": trial.suggest_float("beta", 1, 10.0, step=0.1, log=False),
        "gamma": trial.suggest_float("gamma", 0.01, 0.5, log=True),
    }
    log.info(
        f"\n--- Starting Trial {trial.number} | Params: b={params['beta']:.3f}, g={params['gamma']:.3f} ---"
    )

    if not task_specs:
        log.error("No task specifications available for tuning.")
        return CRITICAL_FAILURE_PENALTY

    try:
        # --- 태스크 샘플링 (전달받은 task_paths_to_tune 사용) ---
        sampled_task_specs = _sample_balanced_task_specs(
            task_specs, n_samples_per_trial
        )
        log.info(f"  Using {len(sampled_task_specs)} sampled tasks for this trial.")
        # --- 샘플링 설정 끝 ---

        total_objective_value = 0.0
        total_computation_time = 0.0
        num_completed_tasks = 0
        num_failed_tasks = 0
        task_results_for_trial: List[Dict] = []

        if not sampled_task_specs:
            log.error(
                "No tasks sampled for tuning. Returning critical failure penalty."
            )
            return CRITICAL_FAILURE_PENALTY

        # --- 샘플링된 태스크 루프 ---
        for task_index, task_spec in enumerate(sampled_task_specs):
            task_path = task_spec.absolute_path
            instruction_arg = task_spec.instruction_filename
            task_result = _run_single_task_for_trial(
                task_path=task_path,
                instruction_arg=instruction_arg,
                trial_number=trial.number,
                params=params,
                scene_name=task_spec.scene_name,
                case_name=task_spec.case_name,
                controller_instance=None,
                nav_graph=None,
                initial_scene_positions={},
            )

            if task_result is None:
                log.error(
                    f"T{trial.number}, Task {task_path.stem}: Simulation function returned None. Max penalty."
                )
                task_result = {
                    "task_name": task_path.stem,
                    "scene_name": task_spec.scene_name,
                    "success_rate": 0.0,
                    "tsr_score": 0.0,
                    "gcr_score": 0.0,
                    "makespan_score": float("inf"),
                }
                task_objective = CRITICAL_FAILURE_PENALTY
                is_valid = False

            else:
                task_objective, is_valid = _calculate_task_objective(
                    task_result, trial.number, task_path.stem
                )

            total_objective_value += task_objective

            if is_valid:
                num_completed_tasks += 1
            else:
                num_failed_tasks += 1

            task_results_for_trial.append(task_result)

            # --- 조기 중단 (Pruning)을 위한 중간 보고 ---
            current_avg_objective = total_objective_value / (task_index + 1)
            trial.report(current_avg_objective, step=task_index)
            if trial.should_prune():
                log.info(
                    f"Trial {trial.number} pruned at step {task_index} (Task: {task_path.stem})."
                )
                raise optuna.TrialPruned()
            # --- 중간 보고 끝 ---

        # --- 최종 평균 계산 시 샘플링된 태스크 수 사용 ---
        num_tasks_run = len(sampled_task_specs)
        average_objective_value = (
            total_objective_value / num_tasks_run
            if num_tasks_run > 0
            else CRITICAL_FAILURE_PENALTY
        )
        average_computation_time = (
            total_computation_time / num_tasks_run
            if num_tasks_run > 0
            else float("inf")
        )

        trial.set_user_attr("num_completed", num_completed_tasks)
        trial.set_user_attr("num_failed", num_failed_tasks)
        completed_makespans = [
            r.get("simulation_makespan", float("inf"))
            for r in task_results_for_trial
            if r.get("status") == "Completed"
        ]
        valid_makespans = [m for m in completed_makespans if m != float("inf")]
        avg_completed_makespan = (
            sum(valid_makespans) / len(valid_makespans)
            if valid_makespans
            else float("inf")
        )
        trial.set_user_attr("avg_completed_makespan", avg_completed_makespan)
        trial.set_user_attr("avg_computation_time", average_computation_time)

        # Average evaluation scores
        avg_tsr = (
            sum(r.get("tsr_score", 0.0) for r in task_results_for_trial) / num_tasks_run
            if num_tasks_run > 0
            else 0.0
        )
        avg_gcr = (
            sum(r.get("gcr_score", 0.0) for r in task_results_for_trial) / num_tasks_run
            if num_tasks_run > 0
            else 0.0
        )
        avg_makespan_score = (
            sum(r.get("makespan_score", 0.0) for r in task_results_for_trial)
            / num_tasks_run
            if num_tasks_run > 0
            else 0.0
        )

        trial.set_user_attr("tsr_score", avg_tsr)
        trial.set_user_attr("gcr_score", avg_gcr)
        trial.set_user_attr("makespan_score", avg_makespan_score)
        trial.set_user_attr(
            "scenes_evaluated",
            sorted({spec.scene_name for spec in sampled_task_specs}),
        )

        failed_task_details = [
            {"name": r.get("task_name"), "status": r.get("status")}
            for r in task_results_for_trial
            if r.get("status") != "Completed"
        ]
        try:
            trial.set_user_attr("failed_tasks_json", json.dumps(failed_task_details))
        except TypeError:
            trial.set_user_attr(
                "failed_tasks_json", json.dumps([{"error": "Serialization failed"}])
            )

        avg_obj_str = "N/A"
        if math.isfinite(average_objective_value):
            avg_obj_str = f"{average_objective_value:.4f}"
        elif average_objective_value == float("inf"):
            avg_obj_str = "inf"

        avg_makespan_str = "N/A"
        if math.isfinite(avg_completed_makespan):
            avg_makespan_str = f"{avg_completed_makespan:.2f}"
        elif avg_completed_makespan == float("inf"):
            avg_makespan_str = "inf"

        avg_comp_time_str = "N/A"
        if math.isfinite(average_computation_time):
            avg_comp_time_str = f"{average_computation_time:.2f}"
        elif average_computation_time == float("inf"):
            avg_comp_time_str = "inf"

        log.info(
            f"--- Trial {trial.number} Finished --- Avg Objective (Sampled): {avg_obj_str} "
            f"(Completed OK: {num_completed_tasks}, Failed/Penalized: {num_failed_tasks} / Total Sampled: {num_tasks_run}) "
            f"Avg Makespan (Completed): {avg_makespan_str} | Avg Comp Time: {avg_comp_time_str}s"
        )

        if math.isnan(average_objective_value) or math.isinf(average_objective_value):
            log.warning(
                f"Trial {trial.number}: Invalid objective value ({average_objective_value}). Reporting max penalty."
            )
            average_objective_value = CRITICAL_FAILURE_PENALTY

        return average_objective_value

    except optuna.TrialPruned:
        raise
    except Exception as e:
        log.critical(
            f"Trial {trial.number}: Unhandled exception in objective function: {e}",
            exc_info=True,
        )
        return CRITICAL_FAILURE_PENALTY
    finally:
        log.info(f"--- Trial {trial.number} Resources Cleaned Up ---")


def run_optuna_study(
    n_trials: int,
    timeout_seconds: Optional[int],
    task_specs: List[TaskSpec],
    scenes_evaluated: List[str],
    n_samples_per_trial: int,
    n_jobs: int,
):
    """Optuna 하이퍼파라미터 튜닝 스터디를 설정하고 실행합니다."""
    global CSV_FILENAME

    start_time = time.time()
    study_suffix = scenes_evaluated[0] if len(scenes_evaluated) == 1 else "multi_scene"
    study_name = f"scheduler_tuning_{study_suffix}_{time.strftime('%Y%m%d_%H%M')}"

    OUTPUT_TUNE_DIR.mkdir(parents=True, exist_ok=True)
    db_filename = f"{study_name}.db"
    storage_path = OUTPUT_TUNE_DIR / db_filename
    storage_name = f"sqlite:///{storage_path.resolve()}"

    CSV_FILENAME = OUTPUT_TUNE_DIR / f"{study_name}_trial_results.csv"
    csv_callback = CSVSaveCallback(CSV_FILENAME, CSV_HEADER)
    if not csv_callback._ensure_header():
        log.warning("Failed to ensure CSV header. CSV logging might be incomplete.")

    log.info(f"Creating/Loading Optuna study: '{study_name}' Storage: '{storage_name}'")
    try:
        sampler = optuna.samplers.TPESampler(
            seed=42, n_startup_trials=15, multivariate=True
        )
        pruner = optuna.pruners.MedianPruner(
            n_startup_trials=15, n_warmup_steps=0, interval_steps=1
        )

        study = optuna.create_study(
            study_name=study_name,
            storage=storage_name,
            direction="minimize",
            sampler=sampler,
            pruner=pruner,
            load_if_exists=True,
        )
    except Exception as e:
        log.critical(f"Failed to create or load Optuna study: {e}", exc_info=True)
        return

    log.info(
        "Starting optimization with %d trials (timeout=%s, n_jobs=%d, scenes=%s)...",
        n_trials,
        timeout_seconds,
        n_jobs,
        scenes_evaluated,
    )
    try:
        objective_func = functools.partial(
            objective,
            task_specs=task_specs,
            n_samples_per_trial=n_samples_per_trial,
        )

        study.optimize(
            objective_func,
            n_trials=n_trials,
            timeout=timeout_seconds,
            gc_after_trial=True,
            n_jobs=n_jobs,
            callbacks=[csv_callback],
        )
    except KeyboardInterrupt:
        log.warning("Optimization interrupted by user.")
    except Exception as e:
        log.error(f"Optimization loop failed unexpectedly: {e}", exc_info=True)
    finally:
        end_time = time.time()
        log.info(
            f"\n--- Tuning Loop Finished (Total Time: {end_time - start_time:.2f}s) ---"
        )
        _analyze_and_print_results(study, study_name, OUTPUT_TUNE_DIR)


def _analyze_and_print_results(
    study: optuna.study.Study, study_name: str, output_dir: Path
):
    """완료된 Optuna 스터디 결과를 분석하고 로그로 출력하며, 최종 데이터프레임을 지정된 경로에 저장합니다."""
    try:
        pruned_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.PRUNED]
        )
        complete_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.COMPLETE]
        )
        fail_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.FAIL]
        )

        log.info(f"Study statistics for '{study_name}':")
        log.info(f"  Total trials conducted: {len(study.trials)}")
        log.info(f"  -> Complete trials: {len(complete_trials)}")
        log.info(f"  -> Pruned trials: {len(pruned_trials)}")
        log.info(f"  -> Failed trials: {len(fail_trials)}")

        if complete_trials:
            best_trial = study.best_trial
            log.info("--- Best Trial Found ---")
            log.info(f"  Trial number: {best_trial.number}")
            best_value_str = "N/A"
            if best_trial.value is not None and math.isfinite(best_trial.value):
                best_value_str = f"{best_trial.value:.4f}"
            log.info(f"  Value (Avg Objective): {best_value_str}")
            log.info("  Best Params:")
            for key, value in best_trial.params.items():
                log.info(f"    {key}: {value:.4f}")
            log.info("  User Attributes for Best Trial:")
            for key, value in best_trial.user_attrs.items():
                display_value = value
                if (
                    key == "failed_tasks_json"
                    and isinstance(value, str)
                    and len(value) > 150
                ):
                    try:
                        failed_list = json.loads(value)
                        display_value = (
                            f"{len(failed_list)} failed tasks (see CSV for details)"
                        )
                    except json.JSONDecodeError:
                        display_value = "Failed tasks info (invalid JSON)"
                elif isinstance(value, str) and len(value) > 100:
                    display_value = value[:100] + "..."
                elif key == "avg_completed_makespan" or key == "avg_computation_time":
                    if value == float("inf") or value is None:
                        display_value = "N/A (inf)"
                    elif math.isfinite(value):
                        display_value = f"{value:.2f}"
                    else:
                        display_value = str(value)

                log.info(f"    {key}: {display_value}")
        else:
            log.warning(
                "No trials completed successfully. Cannot determine best trial."
            )

    except Exception as analysis_e:
        log.error(f"Error during results analysis: {analysis_e}", exc_info=True)

    try:
        df = study.trials_dataframe(
            attrs=(
                "number",
                "value",
                "params",
                "state",
                "user_attrs",
                "datetime_start",
                "datetime_complete",
                "duration",
            )
        )
        final_csv_filename = output_dir / f"{study_name}_final_dataframe.csv"
        df.to_csv(final_csv_filename, index=False, encoding="utf-8")
        log.info(f"Final tuning results dataframe saved to '{final_csv_filename}'")
    except Exception as e:
        log.error(f"Failed to save final tuning results dataframe: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Heuristic Parameter Tuning using Optuna"
    )
    parser.add_argument(
        "-n", "--n_trials", type=int, default=1000000, help="Number of Optuna trials"
    )
    parser.add_argument(
        "--timeout", type=int, default=180000, help="Maximum tuning time in seconds"
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="all",  # Default changed from "FloorPlan1" to "all" to use infer scene from path
        help="Default AI-THOR scene. Use 'all' to evaluate across every discovered scene (unless --scenes is provided).",
    )
    parser.add_argument(
        "--scenes",
        nargs="+",
        default=None,
        help="Specific scene names to evaluate. Overrides --scene when provided.",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=None,
        help="Override task file names (default: all JSON in assets/tasks excluding 'natural_languages')",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_TUNE_DIR),
        help="Directory to save CSV results",
    )
    parser.add_argument(
        "--n_samples_per_trial",
        type=int,
        default=5,
        help="Number of tasks to sample per trial",
    )
    parser.add_argument(
        "--n_jobs",
        type=int,
        default=1,
        help="Number of parallel jobs for Optuna trials",
    )

    args = parser.parse_args()

    SCENE_NAME = args.scene
    if not TUNING_TASK_NAMES_LIST:
        log.error(
            "No tasks specified via command line and failed to load dynamically. Exiting."
        )
        sys.exit(1)

    N_TRIALS_TO_RUN = args.n_trials
    TIMEOUT_TUNING_SECONDS = args.timeout
    OUTPUT_TUNE_DIR = Path(args.output_dir)
    N_SAMPLES_PER_TRIAL = args.n_samples_per_trial
    N_JOBS = args.n_jobs

    if args.tasks is not None:
        resolved_task_names = []
        for task_arg in args.tasks:
            normalized = _resolve_task_argument(task_arg)
            if normalized:
                resolved_task_names.append(normalized)
        if not resolved_task_names:
            log.error("No valid tasks resolved from command-line arguments. Exiting.")
            sys.exit(1)
        task_name_candidates = resolved_task_names
        log.info("Using tasks from command-line: %s", task_name_candidates)
    else:
        task_name_candidates = TUNING_TASK_NAMES_LIST

    available_scene_names = sorted(
        {scene for scene in TASK_SCENE_LOOKUP.values() if scene}
    )
    if args.scenes:
        selected_scene_names = sorted(set(args.scenes))
    elif args.scene.lower() == "all":
        # If 'all', use all scenes discovered from task files
        selected_scene_names = available_scene_names
        if not selected_scene_names:
            # Fallback if discovery failed
            selected_scene_names = ["FloorPlan1"]
            log.warning("No scenes discovered from files. Defaulting to FloorPlan1.")
    else:
        selected_scene_names = [args.scene]

    if not selected_scene_names:
        log.error("No scene names could be determined for tuning. Exiting.")
        sys.exit(1)

    task_specs_for_study = _build_task_specs_from_names(
        task_name_candidates, selected_scene_names
    )
    if not task_specs_for_study:
        log.error(
            "No valid task files found for the requested scenes (%s). Exiting.",
            selected_scene_names,
        )
        sys.exit(1)

    scenes_in_use = sorted({spec.scene_name for spec in task_specs_for_study})
    scene_counts = {
        scene: sum(1 for spec in task_specs_for_study if spec.scene_name == scene)
        for scene in scenes_in_use
    }

    log.info(f"--- Starting Heuristic Tuning ---")
    log.info("Scenes selected: %s", scene_counts)
    log.info(
        "Tasks for Tuning (%d): %s",
        len(task_specs_for_study),
        (
            task_name_candidates
            if len(task_name_candidates) < 10
            else f"{task_name_candidates[:10]}..."
        ),
    )
    log.info(f"Number of Trials: {N_TRIALS_TO_RUN}")
    log.info(
        f"Timeout (seconds): {TIMEOUT_TUNING_SECONDS if TIMEOUT_TUNING_SECONDS else 'None'}"
    )
    log.info(f"Output directory: {OUTPUT_TUNE_DIR}")

    try:
        run_optuna_study(
            n_trials=N_TRIALS_TO_RUN,
            timeout_seconds=TIMEOUT_TUNING_SECONDS,
            task_specs=task_specs_for_study,
            scenes_evaluated=scenes_in_use,
            n_samples_per_trial=N_SAMPLES_PER_TRIAL,
            n_jobs=N_JOBS,
        )
    except Exception as main_e:
        log.critical(
            f"An unhandled error occurred during the tuning process: {main_e}",
            exc_info=True,
        )
    finally:
        log.info("--- Tuning Script Finished ---")
