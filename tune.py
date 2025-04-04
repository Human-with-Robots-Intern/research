# tune_hyperparameters.py

import functools  # For potential future use with partial
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

# --- 프로젝트 경로 설정 ---
try:
    # Assume this script is in the project root directory
    PROJECT_ROOT = Path(__file__).resolve().parent
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"  # Add ithor path if needed
    # Add paths to sys.path for module resolution
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))  # Add ithor if navigation_handler is there
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"sys.path updated: {sys.path[:3]}")  # Print first few paths for verification
except NameError:
    PROJECT_ROOT = Path(".").resolve()
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))

# --- 필요한 모듈 임포트 ---
try:
    # Ensure ai2thor_simulation is correctly referenced (e.g., under src)
    # Ensure navigation_handler path is correct
    from handlers.navigation_handler import (
        load_navigation_graph,  # Assuming it's under ithor.handlers
    )

    from core.agent import Agent
    from core.dataclass import CompletedEntry, SchedulerState
    from core.scheduler import Scheduler
    from core.task import Subtask, Task  # Import Task class as well
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler
    from scheduler.heuristic_manager import HeuristicManager
    from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
    from src.utils.common.logger import create_module_logger

    # Ensure config path is correct
    from src.utils.config import (  # Use constants from config; For HeuristicManager fallback
        BEAM_WIDTH,
        ESTIMATE_FILE_NAME,
        KNOWLEDGE_PATH,
        SCENE_NAME,
        SIMULATION_DEPTH,
    )
    from src.utils.io_utils.result_saver import compose_plans
    from src.utils.io_utils.task_io import (
        list_task_files,
        load_scene_positions,
        load_task_data_from_file,
    )
    from src.utils.task import TaskUtil

except ImportError as e:
    print(f"Fatal Error: Failed to import necessary modules: {e}")
    print(f"PYTHONPATH: {sys.path}")
    print("Check module locations, __init__.py files, and relative paths.")
    sys.exit(1)
except Exception as e:

    print(f"Fatal Error during initial setup (e.g., imports): {e}")
    sys.exit(1)


# --- 로깅 설정 ---
log_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] %(message)s"
)
log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(log_formatter)
root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_handler)
logging.getLogger("optuna").setLevel(logging.WARNING)  # Reduce Optuna's verbosity
log = logging.getLogger(__name__)  # Logger for this script


# --- 전역 변수 및 설정 ---
TASK_FILES_DIR = ASSETS_ROOT / "tasks"
CONTROLLER_INSTANCE = init_ai2thor_controller()
NAV_GRAPH = load_navigation_graph(CONTROLLER_INSTANCE)
INITIAL_SCENE_POSITIONS = load_scene_positions(f"{SCENE_NAME}_positions.json")
# Select tasks for tuning - use a representative subset
# Start with fewer, well-understood tasks for initial tuning
TUNING_TASK_NAMES = glob.glob(str(TASK_FILES_DIR / "*.json"))
TASK_PATHS_TO_TUNE = []  # Will be populated in initialize_global_resources


# --- 초기화 함수 ---
def initialize_global_resources():
    """Initializes global resources needed for tuning."""
    global CONTROLLER_INSTANCE, NAV_GRAPH, INITIAL_SCENE_POSITIONS, TASK_PATHS_TO_TUNE
    try:
        log.info("--- Initializing Global Resources ---")
        # 1. Initialize Controller
        log.info(f"Initializing AI2Thor controller for scene: {SCENE_NAME}...")
        CONTROLLER_INSTANCE = init_ai2thor_controller(
            scene=SCENE_NAME, width=300, height=300
        )
        log.info("AI2Thor controller initialized.")

        # 2. Load Navigation Graph
        log.info("Loading navigation graph...")
        NAV_GRAPH = load_navigation_graph(CONTROLLER_INSTANCE)
        log.info("Navigation graph loaded.")

        # 3. Load Initial Scene Positions
        log.info("Loading initial scene positions...")
        positions_file = f"{SCENE_NAME}_positions.json"
        INITIAL_SCENE_POSITIONS = load_scene_positions(positions_file)
        log.info(f"Initial scene positions loaded from {positions_file}.")

        # 4. Prepare Task List for Tuning
        log.info("Preparing task list for tuning...")
        available_task_files = list_task_files()
        available_task_files = [
            p
            for p in available_task_files
            if p.is_file()
            and p.suffix == ".json"
            and "task_natural_languages" not in p.name
        ]

        # Use predefined list or a selection strategy
        TASK_PATHS_TO_TUNE = [
            TASK_FILES_DIR / name
            for name in TUNING_TASK_NAMES
            if (TASK_FILES_DIR / name).exists()
        ]
        if not TASK_PATHS_TO_TUNE:  # Fallback if predefined names not found
            log.warning(
                f"Predefined tuning tasks not found. Selecting first few available tasks."
            )
            TASK_PATHS_TO_TUNE = available_task_files[
                : min(3, len(available_task_files))
            ]

        log.info(f"Selected tasks for tuning: {[p.name for p in TASK_PATHS_TO_TUNE]}")
        if not TASK_PATHS_TO_TUNE:
            log.error("No task files found for tuning.")
            return False  # Indicate failure

        log.info("--- Global Resources Initialized Successfully ---")
        return True

    except FileNotFoundError as e:
        log.critical(f"Initialization failed: Required file not found: {e}")
        return False
    except ImportError:  # Catch potential issues if handlers moved
        log.critical(
            "ImportError during initialization. Check handler paths.", exc_info=True
        )
        return False
    except Exception as e:
        log.critical(
            f"Fatal error during global resource initialization: {e}", exc_info=True
        )
        if CONTROLLER_INSTANCE:
            try:
                CONTROLLER_INSTANCE.stop()
            except:
                pass
        return False


# --- Simulation Runner 함수 ---
def run_schedule_and_get_result(
    task_path: Path,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    scene_name: str,
    initial_scene_positions_run: Dict,
) -> Optional[Dict[str, Any]]:
    """
    Executes the scheduling and simulation loop for a given task path.
    Returns performance metrics dictionary or None on critical failure.
    """
    task_name_str = task_path.stem
    log.info(f"--- Starting Simulation: Task '{task_name_str}' ---")
    computation_start_time = time.time()
    simulation_time_accumulator = 0.0
    result_schedule: List[CompletedEntry] = []  # Stores entries with simulation timing

    if controller_instance is None:
        log.error("Controller instance is None.")
        return None

    try:
        # --- 1. Load Task & Build ---
        log.debug(f"Loading task data from: {task_path}")
        try:
            task_data_dict = load_task_data_from_file(task_path.name)
        except Exception as e:
            log.error(
                f"Failed to load/decode task file {task_path}: {e}. Skipping task."
            )
            return None

        log.debug("Building tasks and constraints...")
        try:
            # Pass the dict and decomposition flag
            subtasks, constraints = TaskUtil.build_tasks_and_constraints(
                task_data=task_data_dict, enable_decomposition=True
            )
        except Exception as e:
            log.error(
                f"Error building tasks/constraints for {task_name_str}: {e}",
                exc_info=True,
            )
            return None

        # --- 2. Reset Controller & Create Initial State ---
        try:
            log.debug(f"Resetting controller to scene: {scene_name}")
            event = controller_instance.reset(scene=scene_name)
            if not event or not event.metadata.get("lastActionSuccess"):
                error_msg = (
                    event.metadata.get("errorMessage", "Reset action failed")
                    if event
                    else "Reset returned None"
                )
                raise RuntimeError(f"Controller reset failed. Error: {error_msg}")
            # Get live state after reset
            live_metadata = event.metadata
            live_initial_positions = INITIAL_SCENE_POSITIONS
            live_initial_held = live_metadata.get("inventoryObjects", [])
            live_initial_held = (
                live_initial_held[0]["objectId"] if live_initial_held else None
            )
            log.debug("Controller reset successful.")
        except Exception as e:
            log.error(
                f"Error resetting controller for task '{task_name_str}': {e}",
                exc_info=True,
            )
            return None

        try:
            # Use live positions for init_state
            current_state = TaskUtil.get_init_state(
                subtasks, constraints, live_initial_positions
            )
            current_state = current_state._replace(
                held_object=live_initial_held, current_time=0.0
            )
            log.debug("Initial SchedulerState created.")
        except Exception as e:
            log.error(f"Error creating initial state: {e}", exc_info=True)
            return None

        # --- 3. Scheduling and Simulation Loop ---
        is_end = False
        step_count = 0
        max_steps = 350  # Slightly increase max steps for complex tasks

        while not is_end:
            step_count += 1
            if step_count > max_steps:
                log.error(
                    f"Exceeded max steps ({max_steps}) for task '{task_name_str}'. Failing."
                )
                break

            log.debug(
                f"\n--- Task '{task_name_str}' | Step {step_count} | Sim Time: {simulation_time_accumulator:.2f} ---"
            )

            # --- Get next subtask ---
            next_sched_state: Optional[SchedulerState] = None
            try:
                next_sched_state = scheduler_instance.get_next_state(current_state)
            except Exception as scheduler_e:
                log.error(
                    f"Error during scheduler.get_next_state: {scheduler_e}",
                    exc_info=True,
                )
                break  # Stop task if scheduler fails

            if next_sched_state is None:
                log.info(
                    f"Scheduler returned None. No feasible plan found for '{task_name_str}'. Ending."
                )
                if not current_state.remaining_subtasks:
                    is_end = True  # Properly finished if no remaining tasks
                break  # End loop otherwise

            scheduled_subtask = next_sched_state.subtask
            if not scheduled_subtask or not scheduled_subtask.name:
                log.error("Scheduler returned state with invalid subtask. Stopping.")
                break
            log.debug(f"Scheduler decided: Execute '{scheduled_subtask.name}'")

            # --- Execute subtask ---
            subtask_elapsed_time = 0.0
            execution_status = False
            try:
                # Using actual execute_subtask signature
                subtask_elapsed_time, execution_status = execute_subtask(
                    controller_instance, scheduled_subtask
                )
                subtask_elapsed_time = float(subtask_elapsed_time)
                execution_status = bool(execution_status)
            except ValueError as ve:
                log.error(f"ValueError during exec: {ve}")
                execution_status = False
            except Exception as exec_e:
                log.error(f"Critical error during exec: {exec_e}", exc_info=True)
                execution_status = False

            # --- Get state AFTER execution attempt ---
            try:
                event = controller_instance.last_event
                if not event or not event.metadata or "objects" not in event.metadata:
                    raise RuntimeError("Controller metadata invalid after execution.")
                # Get object positions
                sim_final_positions = {
                    obj["objectId"]: tuple(obj["position"].values())
                    for obj in event.metadata.get("objects", [])
                }
                # *** Get agent's current position and add it ***
                agent_metadata = event.metadata.get("agent")
                if agent_metadata and "position" in agent_metadata:
                    agent_pos = tuple(agent_metadata["position"].values())
                    sim_final_positions["agent"] = (
                        agent_pos  # 'agent' 키로 현재 위치 추가
                    )
                else:
                    log.warning(
                        "Could not get agent position from controller after execution."
                    )
                    # Fallback: Keep previous agent position if available
                    if "agent" in current_state.scene_positions:
                        sim_final_positions["agent"] = current_state.scene_positions[
                            "agent"
                        ]

                sim_final_held = agent_metadata.get(
                    "inventoryObjects", []
                )  # Agent metadata has inventory
                sim_final_held = (
                    sim_final_held[0]["objectId"] if sim_final_held else None
                )
            except Exception as state_e:
                log.error(
                    f"Failed to get valid state from controller after '{scheduled_subtask.name}': {state_e}. Stopping task."
                )
                execution_status = False  # Ensure marked as failed

            # --- Record Simulation Result ---
            sim_start_time = simulation_time_accumulator
            sim_end_time = sim_start_time + subtask_elapsed_time
            # Ensure scheduled_subtask has necessary attributes before creating entry
            if not hasattr(scheduled_subtask, "start_time_simulation"):
                scheduled_subtask.start_time_simulation = None
            if not hasattr(scheduled_subtask, "end_time_simulation"):
                scheduled_subtask.end_time_simulation = None
            if not hasattr(scheduled_subtask, "execution_status"):
                scheduled_subtask.execution_status = None
            if not hasattr(scheduled_subtask, "start_time_scheduled"):
                scheduled_subtask.start_time_scheduled = None
            if not hasattr(scheduled_subtask, "end_time_scheduled"):
                scheduled_subtask.end_time_scheduled = None

            current_completed_entry = CompletedEntry(
                scheduled_subtask, sim_start_time, sim_end_time
            )
            current_completed_entry.subtask.start_time_simulation = sim_start_time
            current_completed_entry.subtask.end_time_simulation = sim_end_time
            current_completed_entry.subtask.execution_status = execution_status
            # Store scheduled times (approximation)
            last_sched_entry = (
                next_sched_state.completed_subtasks[-1]
                if next_sched_state.completed_subtasks
                else None
            )
            if (
                last_sched_entry
                and last_sched_entry.subtask.name == scheduled_subtask.name
            ):
                current_completed_entry.subtask.start_time_scheduled = (
                    last_sched_entry.start_time
                )
                current_completed_entry.subtask.end_time_scheduled = (
                    last_sched_entry.end_time
                )
            else:
                current_completed_entry.subtask.start_time_scheduled = (
                    current_state.current_time
                )
                current_completed_entry.subtask.end_time_scheduled = (
                    next_sched_state.current_time
                )
            result_schedule.append(current_completed_entry)
            simulation_time_accumulator = sim_end_time

            log.debug(
                f"Subtask '{scheduled_subtask.name}' finished. Sim Time: {simulation_time_accumulator:.2f}. Success: {execution_status}"
            )

            # --- Stop if Execution Failed ---
            if not execution_status:
                log.error(
                    f"Execution failed for '{scheduled_subtask.name}'. Stopping task '{task_name_str}'."
                )
                break

            # --- Create State for Next Iteration ---
            try:
                # Pass the scene_positions dictionary that includes the 'agent' key
                current_state = SchedulerState(
                    subtask=scheduled_subtask,
                    completed_subtasks=result_schedule,
                    remaining_subtasks=next_sched_state.remaining_subtasks,
                    constraints=next_sched_state.constraints,
                    current_time=simulation_time_accumulator,
                    scene_positions=sim_final_positions,  # This now includes 'agent'
                    held_object=sim_final_held,
                    agent_location=None,
                )
                log.debug(
                    f"State updated. Held: {current_state.held_object}, Agent Pos: {current_state.scene_positions.get('agent')}"
                )
            except Exception as state_update_e:
                log.error(f"Error creating next state: {state_update_e}", exc_info=True)
                break

            # --- Agent Bayesian Update ---
            if scheduled_subtask.type == "Monitor":
                log.debug("Monitor task. Calling Agent...")
                try:
                    updated_state_agent, monitored_info = (
                        agent_instance.bayesian_estimate(current_state)
                    )
                    current_state = updated_state_agent  # Agent returns state with updated constraints
                    if result_schedule and monitored_info:
                        result_schedule[-1].subtask.monitored_subtask = monitored_info
                    log.debug("Agent update complete.")
                except Exception as agent_e:
                    log.error(f"Error during agent update: {agent_e}", exc_info=True)
                    log.warning("Continuing without agent constraint update.")

            # --- Check End Condition ---
            if not current_state.remaining_subtasks:
                log.info(f"All subtasks appear completed for task '{task_name_str}'.")
                is_end = True

        # --- 4. Calculate Final Results ---
        total_computation_time = time.time() - computation_start_time

        if not result_schedule:
            log.warning(f"No results recorded for task '{task_name_str}'.")
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

        # Determine final status
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

        if not is_end:
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
            "success_rate": success_rate,  # Calculated by compose_plans based on recorded statuses
            "computation_time": total_computation_time,
            "scene_name": scene_name,
            "task_name": task_name_str,
            "status": final_status,
        }
        log.info(
            f"Simulation finished for task '{task_name_str}'. Status: {result_dict['status']}, "
            f"SimMakespan: {result_dict['simulation_makespan']:.2f}, SuccessRate: {result_dict['success_rate']:.2f}, "
            f"CompTime: {result_dict['computation_time']:.2f}s"
        )
        return result_dict

    except Exception as e:
        # Catch errors during setup or the main loop not caught inside
        log.critical(
            f"Critical unexpected error during simulation run for task '{task_name_str}': {e}",
            exc_info=True,
        )
        return None


# --- Optuna Objective 함수 ---
MIN_SUCCESS_RATE = 1.0  # Require 100% success for all executed steps
MAX_COMPUTATION_TIME_PER_TASK = 150.0  # Allow more time for complex tasks/computation


def objective(trial: optuna.Trial) -> float:
    """Optuna objective function."""
    # 1. Suggest Hyperparameters
    alpha = trial.suggest_float("alpha", 0.01, 15.0, log=True)  # Wider range
    beta = trial.suggest_float("beta", 0.1, 150.0, log=True)  # Wider range
    gamma = trial.suggest_float("gamma", 0.01, 70.0, log=True)  # Wider range
    delta = trial.suggest_float("delta", 0.0, 15.0)  # Wider range

    total_objective_value = 0.0
    num_completed_tasks = 0
    num_failed_tasks = 0

    log.info(
        f"\n--- Starting Trial {trial.number} | Params: a={alpha:.3f}, b={beta:.3f}, g={gamma:.3f}, d={delta:.3f} ---"
    )

    # Ensure global resources are ready
    if (
        CONTROLLER_INSTANCE is None
        or NAV_GRAPH is None
        or INITIAL_SCENE_POSITIONS is None
    ):
        log.critical("Global resources not ready for trial. Pruning.")
        raise optuna.exceptions.TrialPruned("Global resources not initialized")

    for task_path in TASK_PATHS_TO_TUNE:
        task_result = None
        try:
            # Create FRESH instances for agent, handlers, heuristic, scheduler
            agent = Agent()
            # Pass global nav_graph to handlers/managers
            action_handler = ActionHandler(NAV_GRAPH)
            constraint_handler = ConstraintHandler()
            heuristic_manager = HeuristicManager(action_handler)
            # Set tuned parameters
            heuristic_manager.alpha = alpha
            heuristic_manager.beta = beta
            heuristic_manager.gamma = gamma
            heuristic_manager.delta = delta

            scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, NAV_GRAPH)
            scheduler.cost_calculator = heuristic_manager  # Inject heuristic

            # --- Run Simulation ---
            task_result = run_schedule_and_get_result(
                task_path,
                scheduler,
                agent,
                CONTROLLER_INSTANCE,
                SCENE_NAME,
                INITIAL_SCENE_POSITIONS,
            )

            # --- Process Result ---
            penalty = 0.0
            sim_makespan = float("inf")  # Default to infinity

            if task_result is not None:
                sim_makespan = task_result.get("simulation_makespan", float("inf"))
                success_rate = task_result.get("success_rate", 0.0)
                computation_time = task_result.get("computation_time", float("inf"))
                status = task_result.get("status", "Failed")

                # --- Apply Penalties for Invalid/Failed Runs ---
                # Penalize more heavily for not completing vs. just constraint violation
                task_penalty_multiplier = 1.5  # Increase base penalty for failures
                task_base_penalty_makespan = 5000.0  # Base makespan penalty if failed

                if status != "Completed":
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - Status '{status}'. Penalty."
                    )
                    # Assign penalty based on failure type severity
                    if status == "Failed (Execution)":
                        penalty = (
                            task_base_penalty_makespan * task_penalty_multiplier * 1.5
                        )
                    elif status == "Failed (Timeout)":
                        penalty = (
                            task_base_penalty_makespan * task_penalty_multiplier * 1.2
                        )
                    else:
                        penalty = (
                            task_base_penalty_makespan * task_penalty_multiplier
                        )  # General failure / Scheduler plan
                    num_failed_tasks += 1
                elif success_rate < MIN_SUCCESS_RATE:
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - Rate {success_rate:.2f} < {MIN_SUCCESS_RATE}. Penalty."
                    )
                    penalty = (
                        task_base_penalty_makespan * 0.8
                    )  # Lower penalty if completed but low success rate
                    num_failed_tasks += 1  # Still count as failed for objective
                elif computation_time > MAX_COMPUTATION_TIME_PER_TASK:
                    log.warning(
                        f"T{trial.number}, Task {task_path.stem}: Invalid - CompTime {computation_time:.2f}s > {MAX_COMPUTATION_TIME_PER_TASK}s. Penalty."
                    )
                    penalty = (
                        task_base_penalty_makespan * 0.5
                    )  # Lowest penalty for just being slow
                    num_failed_tasks += 1  # Count as failed for objective

                # Add makespan (or base penalty) + specific penalty
                current_task_objective = (
                    sim_makespan
                    if status == "Completed" and sim_makespan != float("inf")
                    else task_base_penalty_makespan
                ) + penalty
                total_objective_value += current_task_objective

                if (
                    status == "Completed"
                    and success_rate >= MIN_SUCCESS_RATE
                    and computation_time <= MAX_COMPUTATION_TIME_PER_TASK
                ):
                    num_completed_tasks += 1

            else:  # Simulation function failed critically
                log.error(
                    f"T{trial.number}, Task {task_path.stem}: Sim func failed. Max penalty."
                )
                total_objective_value += 1e10  # Max penalty if function errors out
                num_failed_tasks += 1

        except Exception as e:
            log.critical(
                f"Critical error processing task {task_path.stem} in trial {trial.number}: {e}",
                exc_info=True,
            )
            total_objective_value += 1e10  # Max penalty
            num_failed_tasks += 1

    # --- Final Objective Calculation for Trial ---
    num_tasks_run = len(TASK_PATHS_TO_TUNE)
    if num_tasks_run == 0:
        return float("inf")

    # Average objective over all tasks attempted
    average_objective_value = total_objective_value / num_tasks_run

    # Store user attributes
    trial.set_user_attr("num_completed", num_completed_tasks)
    trial.set_user_attr("num_failed", num_failed_tasks)
    # Calculate average makespan ONLY for tasks that actually completed successfully
    completed_makespans = [
        res.get("simulation_makespan", float("inf"))
        for res in getattr(trial, "_user_attrs", {}).get(
            "task_results", []
        )  # Need to store results first
        if res.get("status") == "Completed"
    ]
    avg_completed_makespan = (
        sum(completed_makespans) / len(completed_makespans)
        if completed_makespans
        else float("inf")
    )
    trial.set_user_attr("avg_completed_makespan", avg_completed_makespan)

    log.info(
        f"Trial {trial.number} finished. Avg Objective (Lower is Better): {average_objective_value:.2f} "
        f"(Completed OK: {num_completed_tasks}, Failed/Penalized: {num_failed_tasks} / Total: {num_tasks_run})"
    )

    # Pruning
    trial.report(average_objective_value, step=0)
    if trial.should_prune():
        log.info(f"Trial {trial.number} pruned.")
        raise optuna.TrialPruned()

    return average_objective_value


# --- Optuna 스터디 실행 ---
if __name__ == "__main__":
    # Initialize global resources first
    if not initialize_global_resources():
        sys.exit(1)

    start_time = time.time()
    study_name = f"scheduler_tuning_{SCENE_NAME}_{time.strftime('%Y%m%d_%H%M%S')}"
    storage_name = f"sqlite:///{study_name}.db"  # Use SQLite for storage and resuming

    log.info(f"Creating/Loading Optuna study: {study_name} Storage: {storage_name}")
    try:
        study = optuna.create_study(
            study_name=study_name,
            storage=storage_name,
            direction="minimize",
            sampler=optuna.samplers.TPESampler(
                seed=42, n_startup_trials=20, multivariate=True
            ),  # TPE with more startup, consider multivariate
            pruner=optuna.pruners.MedianPruner(
                n_startup_trials=20, n_warmup_steps=0, interval_steps=1
            ),
            load_if_exists=True,  # Resume if study exists
        )
    except Exception as e:
        log.critical(f"Failed to create or load Optuna study: {e}", exc_info=True)
        sys.exit(1)

    n_trials = 300  # Increase trials for better exploration
    timeout_seconds = 3600 * 10  # Longer timeout (e.g., 10 hours)

    log.info(
        f"Starting optimization with {n_trials} trials (timeout={timeout_seconds}s)..."
    )
    try:
        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout_seconds,
            gc_after_trial=True,
            n_jobs=1,
        )  # n_jobs=1 for AI2THOR stability
    except KeyboardInterrupt:
        log.warning("Optimization interrupted by user.")
    except Exception as e:
        log.error(f"Optimization loop failed: {e}", exc_info=True)

    end_time = time.time()

    # --- 결과 분석 및 출력 ---
    log.info("\n--- Tuning Completed ---")
    log.info(f"Total tuning time: {(end_time - start_time)/3600:.2f} hours")
    try:
        # Get all trials (including failed/pruned) for complete picture
        all_trials = study.get_trials(deepcopy=False)
        completed_trials = [
            t for t in all_trials if t.state == optuna.trial.TrialState.COMPLETE
        ]
        pruned_trials = [
            t for t in all_trials if t.state == optuna.trial.TrialState.PRUNED
        ]
        failed_trials = [
            t for t in all_trials if t.state == optuna.trial.TrialState.FAIL
        ]
        log.info(
            f"Trial states: Completed={len(completed_trials)}, Pruned={len(pruned_trials)}, Failed={len(failed_trials)}, Total={len(all_trials)}"
        )

        if completed_trials:
            # Find best trial among COMPLETED trials only
            valid_completed_trials = [
                t
                for t in completed_trials
                if t.value is not None
                and t.value != float("inf")
                and not math.isnan(t.value)
            ]
            if valid_completed_trials:
                best_trial = min(valid_completed_trials, key=lambda t: t.value)
                log.info("--- Best Trial Found (among valid completed) ---")
                log.info(f"  Trial Number: {best_trial.number}")
                best_value = best_trial.value
                log.info(f"  Value (Avg Objective): {best_value:.4f}")
                log.info("  Params: ")
                for key, value in best_trial.params.items():
                    log.info(f"    {key}: {value:.4f}")
                # Log user attributes for best trial
                log.info("  Trial User Attributes:")
                for key, value in best_trial.user_attrs.items():
                    log.info(f"    {key}: {value}")

                # Top 5 Trials
                sorted_trials = sorted(valid_completed_trials, key=lambda t: t.value)
                log.info(
                    "\n--- Top 5 Valid Completed Trials (Value = Avg Objective) ---"
                )
                for i, t in enumerate(sorted_trials[:5]):
                    value = t.value
                    log.info(
                        f"Rank {i+1}: Trial {t.number}, Value: {value:.4f}, Params: {t.params}"
                    )
                    log.info(
                        f"        User Attrs: {t.user_attrs}"
                    )  # Print user attrs too
            else:
                log.warning(
                    "No valid completed trials found (all failed constraints or returned inf/nan)."
                )
        else:
            log.warning("No trials completed successfully.")

    except Exception as e:
        log.error(f"Error analyzing study results: {e}", exc_info=True)

    # --- 결과 DataFrame 저장 ---
    try:
        df = study.trials_dataframe(
            attrs=("number", "value", "params", "state", "user_attrs")
        )
        csv_filename = f"{study_name}_results.csv"
        df.to_csv(csv_filename, index=False)
        log.info(f"Tuning results saved to {csv_filename}")
    except Exception as e:
        log.error(f"Failed to save tuning results CSV: {e}")

    # --- AI2Thor 종료 ---
    if CONTROLLER_INSTANCE:
        try:
            CONTROLLER_INSTANCE.stop()
            log.info("AI2Thor controller stopped.")
        except Exception as e:
            log.error(f"Error stopping AI2Thor controller: {e}")

    log.info("--- Tuning Script Finished ---")
