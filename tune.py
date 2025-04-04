# tune_hyperparameters.py (Ensure CSV Callback Works)

import csv  # Import csv module
import functools
import glob
import json
import logging
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import optuna

# import threading # Lock not strictly needed for n_jobs=1

# --- 프로젝트 경로 설정 ---
# ... (이전과 동일) ...
try:
    PROJECT_ROOT = Path(__file__).resolve().parent
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"sys.path updated: {sys.path[:3]}")
except NameError:
    PROJECT_ROOT = Path(".").resolve()
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))

# --- 필요한 모듈 임포트 ---
# ... (이전과 동일 - 경로 확인 필수) ...
try:
    from handlers.navigation_handler import load_navigation_graph

    from core.agent import Agent
    from core.dataclass import CompletedEntry, SchedulerState
    from core.scheduler import Scheduler
    from core.task import Subtask, Task
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler
    from scheduler.heuristic_manager import HeuristicManager
    from src.simulation.runner_ai2thor import (  # 경로 확인
        execute_subtask,
        init_ai2thor_controller,
    )
    from src.utils.common.logger import create_module_logger  # 경로 확인
    from src.utils.config import BEAM_WIDTH, SCENE_NAME, SIMULATION_DEPTH  # 경로 확인
    from src.utils.io_utils.result_saver import compose_plans  # 경로 확인
    from src.utils.io_utils.task_io import (  # 경로 확인
        list_task_files,
        load_scene_positions,
        load_task_data_from_file,
    )
    from src.utils.task import TaskUtil  # 경로 확인
except ImportError as e:
    print(f"Fatal Error importing: {e}\nPYTHONPATH: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Fatal Error during initial imports: {e}")
    sys.exit(1)


# --- 로깅 설정 ---
# ... (이전과 동일) ...
log_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] %(message)s"
)
log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(log_formatter)
root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()
root_logger.setLevel(logging.WARNING)
root_logger.addHandler(log_handler)
logging.getLogger("optuna").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# --- 전역 변수 및 설정 ---
TASK_FILES_DIR = ASSETS_ROOT / "tasks"
CONTROLLER_INSTANCE: Optional[Any] = None
NAV_GRAPH: Optional[Dict] = None
INITIAL_SCENE_POSITIONS: Optional[Dict] = None
TUNING_TASK_NAMES_LIST = glob.glob(str(TASK_FILES_DIR / "*.json"))  # Get all task files
TASK_PATHS_TO_TUNE: List[Path] = []
CSV_FILENAME = ""  # Will be set after study creation
CSV_HEADER = [  # CSV 파일 헤더 정의
    "trial_number",
    "value",
    "state",
    "datetime_start",
    "datetime_complete",
    "duration",
    "param_alpha",
    "param_beta",
    "param_gamma",
    "param_delta",
    "user_attr_num_completed",
    "user_attr_num_failed",
    "user_attr_avg_completed_makespan",
]


# --- 초기화 함수 ---
# ... (initialize_global_resources 함수는 이전과 동일) ...
def initialize_global_resources():
    global CONTROLLER_INSTANCE, NAV_GRAPH, INITIAL_SCENE_POSITIONS, TASK_PATHS_TO_TUNE
    try:
        log.info("--- Initializing Global Resources ---")
        if CONTROLLER_INSTANCE is None:
            CONTROLLER_INSTANCE = init_ai2thor_controller(
                scene=SCENE_NAME, width=300, height=300
            )
            log.info("Controller initialized.")
        if NAV_GRAPH is None:
            NAV_GRAPH = load_navigation_graph(CONTROLLER_INSTANCE)
            log.info("Nav graph loaded.")
        if INITIAL_SCENE_POSITIONS is None:
            positions_file = f"{SCENE_NAME}_positions.json"
            INITIAL_SCENE_POSITIONS = load_scene_positions(positions_file)
            log.info(f"Initial positions loaded.")
        TASK_PATHS_TO_TUNE.clear()
        found_tasks = []
        for name in TUNING_TASK_NAMES_LIST:
            task_path = TASK_FILES_DIR / name
        if task_path.exists():
            found_tasks.append(task_path)
        else:
            log.warning(f"Task file not found: {task_path}")
        if not found_tasks:
            log.warning(f"Using fallback tasks.")
            all_available = list_task_files()
            found_tasks = [p for p in all_available if p.is_file()][
                : min(3, len(all_available))
            ]
        TASK_PATHS_TO_TUNE.extend(found_tasks)
        if not TASK_PATHS_TO_TUNE:
            log.error("No task files found.")
            return False
        log.info(f"Selected tasks for tuning: {[p.name for p in TASK_PATHS_TO_TUNE]}")
        log.info("--- Global Resources Initialized ---")
        return True
    except Exception as e:
        log.critical(f"Initialization failed: {e}", exc_info=True)
        return False


# --- Simulation Runner 함수 ---
# ... (run_schedule_and_get_result 함수는 이전 버전 사용 - 변경 없음) ...
# (이전 답변의 최종 코드 사용)
def run_schedule_and_get_result(
    task_path: Path,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    scene_name: str,
    initial_scene_positions_run: Dict,
) -> Optional[Dict[str, Any]]:
    # Placeholder - Use the full implementation from the previous verified answer
    task_name_str = task_path.stem
    log.info(f"--- Starting Sim: '{task_name_str}' ---")
    computation_start_time = time.time()
    simulation_time_accumulator = 0.0
    result_schedule: List[CompletedEntry] = []
    try:
        task_data_dict = load_task_data_from_file(task_path.name)
        subtasks, constraints = TaskUtil.build_tasks_and_constraints(
            task_data=task_data_dict, enable_decomposition=True
        )
        event = controller_instance.reset(scene=scene_name)
        live_metadata = event.metadata
        live_initial_positions = INITIAL_SCENE_POSITIONS
        live_initial_held = live_metadata.get("inventoryObjects", [])
        live_initial_held = (
            live_initial_held[0]["objectId"] if live_initial_held else None
        )
        current_state = TaskUtil.get_init_state(
            subtasks, constraints, live_initial_positions
        )
        current_state = current_state._replace(
            held_object=live_initial_held, current_time=0.0
        )
        is_end = False
        step_count = 0
        max_steps = 350
        while not is_end:
            step_count += 1
            if step_count > max_steps:
                log.error(f"Max steps exceeded for '{task_name_str}'.")
                break
            next_sched_state: Optional[SchedulerState] = None
            try:
                next_sched_state = scheduler_instance.get_next_state(current_state)
            except Exception as scheduler_e:
                log.error(f"Scheduler error: {scheduler_e}", exc_info=True)
                break
            if next_sched_state is None:
                log.info(f"Scheduler returned None for '{task_name_str}'.")
            if not current_state.remaining_subtasks:
                is_end = True
                break
            scheduled_subtask = next_sched_state.subtask
            if not scheduled_subtask or not scheduled_subtask.name:
                log.error("Invalid subtask.")
                break
            subtask_elapsed_time = 0.0
            execution_status = False
            sim_final_positions = current_state.scene_positions
            sim_final_held = current_state.held_object
            try:
                subtask_elapsed_time, execution_status = execute_subtask(
                    controller_instance, scheduled_subtask
                )
                subtask_elapsed_time = float(subtask_elapsed_time)
                execution_status = bool(execution_status)
                event = controller_instance.last_event
                if not event or not event.metadata or "objects" not in event.metadata:
                    raise RuntimeError("Invalid metadata")
                sim_final_positions = {
                    obj["objectId"]: tuple(obj["position"].values())
                    for obj in event.metadata.get("objects", [])
                }
                agent_meta = event.metadata.get("agent")
                if agent_meta and "position" in agent_meta:
                    sim_final_positions["agent"] = tuple(
                        agent_meta["position"].values()
                    )
                elif "agent" in current_state.scene_positions:
                    sim_final_positions["agent"] = current_state.scene_positions[
                        "agent"
                    ]
                sim_final_held = agent_meta.get("inventoryObjects", [])
                sim_final_held = (
                    sim_final_held[0]["objectId"] if sim_final_held else None
                )
            except Exception as exec_e:
                log.error(f"Exec Error: {exec_e}")
                execution_status = False
            if not execution_status:
                log.error(f"Exec failed for '{scheduled_subtask.name}'.")
                break
            sim_start_time = simulation_time_accumulator
            sim_end_time = sim_start_time + subtask_elapsed_time
            for attr in [
                "start_time_simulation",
                "end_time_simulation",
                "execution_status",
                "start_time_scheduled",
                "end_time_scheduled",
                "monitored_subtask",
            ]:
                if not hasattr(scheduled_subtask, attr):
                    setattr(scheduled_subtask, attr, None)
            current_completed_entry = CompletedEntry(
                scheduled_subtask, sim_start_time, sim_end_time
            )
            current_completed_entry.subtask.start_time_simulation = sim_start_time
            current_completed_entry.subtask.end_time_simulation = sim_end_time
            current_completed_entry.subtask.execution_status = execution_status
            # ... store scheduled times approx ...
            result_schedule.append(current_completed_entry)
            simulation_time_accumulator = sim_end_time
            try:
                current_state = SchedulerState(
                    subtask=scheduled_subtask,
                    completed_subtasks=result_schedule,
                    remaining_subtasks=next_sched_state.remaining_subtasks,
                    constraints=next_sched_state.constraints,
                    current_time=simulation_time_accumulator,
                    scene_positions=sim_final_positions,
                    held_object=sim_final_held,
                    agent_location=None,
                )
            except Exception as state_update_e:
                log.error(f"State update error: {state_update_e}", exc_info=True)
                break
            if scheduled_subtask.type == "Monitor":
                try:
                    updated_state_agent, monitored_info = (
                        agent_instance.bayesian_estimate(current_state)
                    )
                    current_state = updated_state_agent
                    # ... store monitored_info ...
                except Exception as agent_e:
                    log.error(f"Agent error: {agent_e}", exc_info=True)
                    log.warning("Continuing without agent update.")
            if not current_state.remaining_subtasks:
                log.info(f"All subtasks completed for '{task_name_str}'.")
                is_end = True
        total_computation_time = time.time() - computation_start_time
        if not result_schedule:
            return {
                "status": "Failed (No Progress)",
                "simulation_makespan": float("inf"),
                "success_rate": 0.0,
                "computation_time": total_computation_time,
                "scene_name": scene_name,
                "task_name": task_name_str,
            }
        task_name_for_compose = task_data_dict.get("Task", task_name_str)
        plans, success_rate, final_sim_makespan, final_sched_makespan = compose_plans(
            result_schedule, task_name_for_compose
        )
        final_status = "Unknown"
        last_step_succeeded = result_schedule[-1].subtask.execution_status
        if is_end and last_step_succeeded:
            final_status = "Completed"
        elif not last_step_succeeded:
            final_status = "Failed (Execution)"
        elif step_count > max_steps:
            final_status = "Failed (Timeout)"
        else:
            final_status = "Failed (Scheduler Plan/Unknown)"
        if not is_end and result_schedule:
            final_sim_makespan = result_schedule[-1].end_time
        result_dict = {
            "simulation_makespan": (
                final_sim_makespan if final_sim_makespan is not None else float("inf")
            ),
            "scheduler_makespan": (
                final_sched_makespan
                if final_sched_makespan is not None
                else float("inf")
            ),
            "success_rate": success_rate,
            "computation_time": total_computation_time,
            "scene_name": scene_name,
            "task_name": task_name_str,
            "status": final_status,
        }
        log.info(
            f"Sim finished '{task_name_str}'. Status: {result_dict['status']}, SimMakespan: {result_dict['simulation_makespan']:.2f}, Rate: {result_dict['success_rate']:.2f}, CompTime: {result_dict['computation_time']:.2f}s"
        )
        return result_dict
    except Exception as e:
        log.critical(f"Critical error in sim run '{task_name_str}': {e}", exc_info=True)
        return None


# --- Optuna Callback for CSV Logging ---
class CSVSaveCallback:
    def __init__(self, csv_path: Path, header: List[str]):
        self.csv_path = csv_path
        self.header = header
        self._header_written = False  # Flag to track if header is written
        # self.lock = threading.Lock() # Uncomment if n_jobs > 1

    def __call__(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial):
        # Ensure header is written only once, even if file exists from previous run
        # Use a lock if multiple processes might try to write the header simultaneously (n_jobs > 1)
        # with self.lock:
        if not self._header_written and not self.csv_path.exists():
            try:
                with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                self._header_written = True  # Mark header as written for this run
                log.info(f"Initialized CSV log file: {self.csv_path}")
            except IOError as e:
                log.error(f"Failed to initialize CSV log file: {e}")
                return  # Stop if cannot write header

        # File exists, check if we need to write header (e.g., script restarted)
        # This check might be redundant if using load_if_exists but adds safety
        if not self._header_written and self.csv_path.exists():
            # Simple check: if file is empty, write header
            if self.csv_path.stat().st_size == 0:
                try:
                    with open(
                        self.csv_path, "w", newline="", encoding="utf-8"
                    ) as f:  # Overwrite if empty
                        writer = csv.writer(f)
                        writer.writerow(self.header)
                    self._header_written = True
                    log.info(
                        f"Wrote header to empty existing CSV file: {self.csv_path}"
                    )
                except IOError as e:
                    log.error(f"Failed to write header to empty CSV file: {e}")
                    return
            else:
                self._header_written = True  # Assume header exists if file not empty

        # Append data for the completed/failed trial
        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Prepare data row, handling potential None values
                value = (
                    trial.value
                    if trial.value is not None and not math.isnan(trial.value)
                    else ""
                )  # Write empty string for None/NaN value
                state = trial.state.name
                dt_start = (
                    trial.datetime_start.isoformat() if trial.datetime_start else ""
                )
                dt_complete = (
                    trial.datetime_complete.isoformat()
                    if trial.datetime_complete
                    else ""
                )
                duration = trial.duration.total_seconds() if trial.duration else ""
                # Get params safely
                p_alpha = trial.params.get("alpha", "")
                p_beta = trial.params.get("beta", "")
                p_gamma = trial.params.get("gamma", "")
                p_delta = trial.params.get("delta", "")
                # Get user attributes safely
                ua_completed = trial.user_attrs.get("num_completed", "")
                ua_failed = trial.user_attrs.get("num_failed", "")
                ua_avg_makespan = trial.user_attrs.get("avg_completed_makespan", "")
                if ua_avg_makespan == float("inf"):
                    ua_avg_makespan = ""  # Write empty if inf

                row = [
                    trial.number,
                    value,
                    state,
                    dt_start,
                    dt_complete,
                    duration,
                    p_alpha,
                    p_beta,
                    p_gamma,
                    p_delta,
                    ua_completed,
                    ua_failed,
                    ua_avg_makespan,
                ]
                writer.writerow(row)
        except IOError as e:
            log.error(f"Failed to append trial {trial.number} to CSV: {e}")
        except Exception as e:
            log.error(
                f"Unexpected error writing trial {trial.number} to CSV: {e}",
                exc_info=True,
            )


# --- Optuna Objective 함수 ---
MIN_SUCCESS_RATE = 1.0
MAX_COMPUTATION_TIME_PER_TASK = 150.0


def objective(trial: optuna.Trial) -> float:
    """Optuna objective function."""
    # 1. Suggest Hyperparameters
    alpha = trial.suggest_float("alpha", 0.01, 15.0, log=True)
    beta = trial.suggest_float("beta", 0.1, 150.0, log=True)
    gamma = trial.suggest_float("gamma", 0.01, 70.0, log=True)
    delta = trial.suggest_float("delta", 0.0, 15.0)

    total_objective_value = 0.0
    num_completed_tasks = 0
    num_failed_tasks = 0
    task_results_for_trial = []  # Store individual results for user_attrs

    log.info(
        f"\n--- Starting Trial {trial.number} | Params: a={alpha:.3f}, b={beta:.3f}, g={gamma:.3f}, d={delta:.3f} ---"
    )

    if (
        CONTROLLER_INSTANCE is None
        or NAV_GRAPH is None
        or INITIAL_SCENE_POSITIONS is None
    ):
        log.critical("T{trial.number}: Global resources missing. Pruning.")
        raise optuna.exceptions.TrialPruned("Global resources not initialized")

    for task_path in TASK_PATHS_TO_TUNE:
        task_result = None
        try:
            agent = Agent()
            action_handler = ActionHandler(NAV_GRAPH)
            constraint_handler = ConstraintHandler()
            # Pass fresh handler instances to HeuristicManager
            heuristic_manager = HeuristicManager(action_handler)
            heuristic_manager.alpha = alpha
            heuristic_manager.beta = beta
            heuristic_manager.gamma = gamma
            heuristic_manager.delta = delta

            scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, NAV_GRAPH)
            scheduler.cost_calculator = heuristic_manager

            task_result = run_schedule_and_get_result(
                task_path,
                scheduler,
                agent,
                CONTROLLER_INSTANCE,
                SCENE_NAME,
                INITIAL_SCENE_POSITIONS,
            )

            penalty = 0.0
            sim_makespan = float("inf")
            status = "Critical Failure in Runner"  # Default if task_result is None

            if task_result is not None:
                task_results_for_trial.append(task_result)  # Store detailed result
                sim_makespan = task_result.get("simulation_makespan", float("inf"))
                success_rate = task_result.get("success_rate", 0.0)
                computation_time = task_result.get("computation_time", float("inf"))
                status = task_result.get("status", "Failed")

                is_valid = True
                task_base_penalty_makespan = 5000.0
                task_penalty_multiplier = 1.5

                if status != "Completed":
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - Status '{status}'. Penalty."
                    )
                    if status == "Failed (Execution)":
                        penalty = (
                            task_base_penalty_makespan * task_penalty_multiplier * 1.5
                        )
                    elif status == "Failed (Timeout)":
                        penalty = (
                            task_base_penalty_makespan * task_penalty_multiplier * 1.2
                        )
                    else:
                        penalty = task_base_penalty_makespan * task_penalty_multiplier
                    is_valid = False
                    num_failed_tasks += 1
                elif success_rate < MIN_SUCCESS_RATE:
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - Rate {success_rate:.2f} < {MIN_SUCCESS_RATE}. Penalty."
                    )
                    penalty = task_base_penalty_makespan * 0.8
                    is_valid = False
                    num_failed_tasks += 1
                elif computation_time > MAX_COMPUTATION_TIME_PER_TASK:
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - CompTime {computation_time:.2f}s > {MAX_COMPUTATION_TIME_PER_TASK}s. Penalty."
                    )
                    penalty = task_base_penalty_makespan * 0.5
                    is_valid = False
                    num_failed_tasks += 1

                current_task_objective = (
                    sim_makespan
                    if is_valid and sim_makespan != float("inf")
                    else task_base_penalty_makespan
                ) + penalty
                total_objective_value += current_task_objective

                if is_valid:
                    num_completed_tasks += 1

            else:  # Simulation function failed critically
                log.error(
                    f"T{trial.number}, Task {task_path.stem}: Sim func failed. Max penalty."
                )
                total_objective_value += 1e10  # Max penalty
                num_failed_tasks += 1
                task_results_for_trial.append(
                    {"task_name": task_path.stem, "status": status}
                )  # Store failure info

        except Exception as e:
            log.critical(
                f"Critical error processing task {task_path.stem} in trial {trial.number}: {e}",
                exc_info=True,
            )
            total_objective_value += 1e10
            num_failed_tasks += 1
            task_results_for_trial.append(
                {
                    "task_name": task_path.stem,
                    "status": "Critical Failure in Trial Loop",
                }
            )

    # --- Final Objective Calculation & User Attrs ---
    num_tasks_run = len(TASK_PATHS_TO_TUNE)
    if num_tasks_run == 0:
        return float("inf")
    average_objective_value = total_objective_value / num_tasks_run

    trial.set_user_attr("num_completed", num_completed_tasks)
    trial.set_user_attr("num_failed", num_failed_tasks)
    completed_makespans = [
        res.get("simulation_makespan", float("inf"))
        for res in task_results_for_trial
        if res.get("status") == "Completed"
    ]
    avg_completed_makespan = (
        sum(
            comp_makespan
            for comp_makespan in completed_makespans
            if comp_makespan != float("inf")
        )
        / len(completed_makespans)
        if completed_makespans
        else float("inf")
    )
    trial.set_user_attr(
        "avg_completed_makespan",
        avg_completed_makespan if avg_completed_makespan != float("inf") else None,
    )
    # Optional: Store list of failed tasks
    failed_task_names = [
        res.get("task_name")
        for res in task_results_for_trial
        if res.get("status") != "Completed"
    ]
    trial.set_user_attr(
        "failed_tasks", json.dumps(failed_task_names)
    )  # Store as JSON string

    log.info(
        f"Trial {trial.number} finished. Avg Objective: {average_objective_value:.2f} "
        f"(Completed OK: {num_completed_tasks}, Failed/Penalized: {num_failed_tasks} / Total: {num_tasks_run})"
    )

    # Pruning
    # Ensure objective value is valid before reporting
    if (
        average_objective_value is None
        or math.isnan(average_objective_value)
        or math.isinf(average_objective_value)
    ):
        log.warning(
            f"Trial {trial.number}: Invalid objective value ({average_objective_value}). Cannot prune or report."
        )
        # Return a large value instead of None/NaN/Inf if Optuna requires a float
        return 1e12  # Return very large number if calculation failed
    else:
        trial.report(average_objective_value, step=0)
        if trial.should_prune():
            log.info(f"Trial {trial.number} pruned.")
            raise optuna.TrialPruned()

    return average_objective_value


# --- Optuna 스터디 실행 ---
if __name__ == "__main__":
    # Initialize global resources first
    if not initialize_global_resources():
        log.critical("Exiting due to resource initialization failure.")
        sys.exit(1)  # Ensure exit if init fails

    start_time = time.time()
    study_name = f"scheduler_tuning_{SCENE_NAME}_{time.strftime('%Y%m%d_%H%M%S')}"
    storage_name = f"sqlite:///{study_name}.db"
    # *** Set CSV Filename based on study name ***
    CSV_FILENAME = Path(f"{study_name}_results.csv")
    # *** Create Callback instance ***
    csv_callback = CSVSaveCallback(CSV_FILENAME, CSV_HEADER)  # <<< 콜백 객체 생성
    # *** Initialize CSV file header ***
    if not CSV_FILENAME.exists() or CSV_FILENAME.stat().st_size == 0:
        try:
            with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
            log.info(f"Initialized CSV log file: {CSV_FILENAME}")
            # Mark header as written in the callback instance if needed for robustness
            # csv_callback._header_written = True # Generally not needed if checking file size
        except IOError as e:
            log.error(
                f"Failed to create initial CSV log file: {e}. CSV logging might fail."
            )

    log.info(f"Creating/Loading Optuna study: {study_name} Storage: {storage_name}")
    try:
        study = optuna.create_study(
            study_name=study_name,
            storage=storage_name,
            direction="minimize",
            sampler=optuna.samplers.TPESampler(
                seed=42, n_startup_trials=20, multivariate=True
            ),
            pruner=optuna.pruners.MedianPruner(
                n_startup_trials=20, n_warmup_steps=0, interval_steps=1
            ),
            load_if_exists=True,
        )
        # study.add_trial_callback(csv_callback) # <<< 이 줄 삭제

    except Exception as e:
        log.critical(f"Failed to create or load Optuna study: {e}", exc_info=True)
        sys.exit(1)

    n_trials = 1000  # Adjust number of trials
    timeout_seconds = 3600 * 24 * 2  # Adjust timeout

    log.info(
        f"Starting optimization with {n_trials} trials (timeout={timeout_seconds}s)..."
    )
    try:
        # *** Pass the callback object in a list to the 'callbacks' argument ***
        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout_seconds,
            gc_after_trial=True,
            n_jobs=1,
            callbacks=[csv_callback],  # <<< 콜백 리스트 전달
        )
    except KeyboardInterrupt:
        log.warning("Optimization interrupted by user.")
    except optuna.exceptions.TrialPruned as e:
        log.info(
            f"Pruning stopped optimization early: {e}"
        )  # Catch pruning specific exception if needed
    except Exception as e:
        log.error(f"Optimization loop failed: {e}", exc_info=True)

    end_time = time.time()

    # --- 결과 분석 및 출력 ---
    # (이전과 동일 - Robustness Enhanced 버전 사용)
    log.info("\n--- Tuning Completed ---")
    # ... (Analysis and print results) ...

    # --- 최종 DataFrame 저장 ---
    # (이전과 동일 - 추가 확인용)
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
        final_csv_filename = f"{study_name}_final_dataframe.csv"  # Different name
        df.to_csv(final_csv_filename, index=False)
        log.info(f"Final tuning results dataframe saved to {final_csv_filename}")
    except Exception as e:
        log.error(f"Failed to save final tuning results CSV: {e}")

    # --- AI2Thor 종료 ---
    if CONTROLLER_INSTANCE:
        try:
            CONTROLLER_INSTANCE.stop()
            log.info("AI2Thor controller stopped.")
        except Exception as e:
            log.error(f"Error stopping AI2Thor controller: {e}")

    log.info("--- Tuning Script Finished ---")
