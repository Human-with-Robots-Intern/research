import argparse
import time
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx  # networkx import 추가 (constraints 타입 힌트용)
from ai2thor.controller import Controller

from core.agent import Agent
from core.dataclass import SchedulerState
from core.scheduler import Scheduler
from ithor.handlers.navigation_handler import load_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from utils.common.logger import create_module_logger
from utils.config import BEAM_WIDTH, LOG_ROUND, SCENE_NAME, SIMULATION_DEPTH
from utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
    result_save,
)
from utils.task import TaskUtil
from utils.visualizers import visualize


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

    parser.add_argument(
        "-d",
        "--decomposition",
        help="Enable or disable decomposition",
        default=True,
        action="store_true",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        help="Enable visualization of the task plan",
        default=True,
        action="store_true",
    )
    parser.add_argument(
        "-r",
        "--reset",
        default=True,
        help="Reset the knowledge base to Gaussian",
        action="store_true",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: INFO)",
    )

    return parser.parse_args()


log = create_module_logger(module_name=__name__, module_log=True)


def initialize_environment(scene_name: str) -> Tuple[Controller, Any, Dict[str, Any]]:
    """Initialize AI2-THOR controller, navigation graph, and load scene positions."""
    log.info("Initializing environment...")
    controller = init_ai2thor_controller()
    nav_graph = load_navigation_graph(controller)
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")
    log.info("Environment initialized.")
    return controller, nav_graph, scene_poses


def load_task(args: argparse.Namespace) -> Tuple[str, Dict[str, Any], str]:
    """Load task data based on user choice or default."""
    log.info("Loading task...")
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = (
        get_natural_language_from_task_file(f"{choice}")
        if choice is not None
        else task_file_name
    )
    log.info(f"Task '{input_natural_language}' loaded from '{task_file_name}'.")
    return task_file_name, task_data, input_natural_language


def run_simulation_loop(
    initial_state: SchedulerState,
    scheduler: Scheduler,
    agent: Agent,
    controller: Controller,
    log_level: str,
) -> Tuple[SchedulerState, float, float]:
    """Run the main simulation loop, scheduling and executing subtasks."""
    log.info("Starting simulation loop...")
    current_state = initial_state
    computation_time = 0.0
    simulation_time = 0.0
    is_end = False

    while not is_end:
        log.debug(
            f"Current state: {current_state.subtask.name if current_state.subtask else 'Initial'}"
        )

        computation_time_start = time.time()
        next_state = scheduler.get_next_state(current_state)
        computation_time += time.time() - computation_time_start

        if next_state is None:
            log.error("No feasible solution found. Exiting loop.")
            break  # 루프 종료

        log.info(f"Executing subtask: {next_state.subtask.name}")
        subtask_time, execution_status = execute_subtask(
            controller, next_state.subtask, log_level
        )

        # Update completed subtask info with simulation results
        last_completed = next_state.completed_subtasks[-1]
        last_completed.subtask.start_time_simulation = simulation_time
        last_completed.subtask.end_time_simulation = simulation_time + subtask_time
        last_completed.subtask.execution_status = execution_status
        simulation_time += subtask_time
        log.debug(
            f"Subtask {last_completed.subtask.name} executed in {subtask_time:.2f}s. Status: {execution_status}"
        )

        if next_state.subtask.type == "Monitor":
            log.info(
                f"Performing Bayesian estimation for Monitor task: {next_state.subtask.name}"
            )
            next_state, monitored_subtask = agent.bayesian_estimate(next_state)
            # monitored_subtask가 None이 아닐 경우에만 할당
            if monitored_subtask:
                last_completed.subtask.monitored_subtask = monitored_subtask
                log.debug(f"Monitored subtask: {monitored_subtask.name}")
            else:
                log.warning(
                    f"Bayesian estimation did not return a monitored subtask for {next_state.subtask.name}"
                )

        current_state = next_state

        if not current_state.remaining_subtasks:
            log.info("All subtasks completed.")
            is_end = True

    log.info("Simulation loop finished.")
    return current_state, computation_time, simulation_time


def process_and_log_results(final_state: SchedulerState) -> List[Dict]:
    """Process the final state, log results, and prepare the result schedule."""
    log.info("Processing and logging results...")
    result_schedule = []
    for ce in final_state.completed_subtasks:
        if ce.subtask.name == "Init":
            continue

        # Ensure times are rounded for logging and storage
        start_time_scheduled = round(ce.start_time, LOG_ROUND)
        end_time_scheduled = round(ce.end_time, LOG_ROUND)

        log.info(
            f"{ce.subtask.name} (Scheduled: {start_time_scheduled} ~ {end_time_scheduled})"
            f" (Simulated: {ce.subtask.start_time_simulation:.{LOG_ROUND}f} ~ {ce.subtask.end_time_simulation:.{LOG_ROUND}f})"
            f" Status: {ce.subtask.execution_status}"
        )
        # 로그 레벨 DEBUG로 변경 또는 조건부 로깅
        if log.level <= 10:  # DEBUG level
            primitive_actions_str = (
                str(ce.subtask.execution.primitive_actions)
                if hasattr(ce.subtask, "execution")
                and hasattr(ce.subtask.execution, "primitive_actions")
                else "N/A"
            )
            log.debug(f"  Primitive actions: {primitive_actions_str}\n")

        # Update scheduled times on the subtask object
        ce.subtask.start_time_scheduled = start_time_scheduled
        ce.subtask.end_time_scheduled = end_time_scheduled
        result_schedule.append(ce)  # CompletedEntry 객체를 직접 추가

    log.info("Result processing complete.")
    return result_schedule


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    log.setLevel(args.log_level)  # 로그 레벨 설정 적용
    approach_name = "dag_bayesian"
    log.info(f"Starting Task Scheduler with approach: {approach_name}")
    log.info(f"Arguments: {args}")

    controller, nav_graph, scene_poses = initialize_environment(SCENE_NAME)
    task_file_name, task_data, input_natural_language = load_task(args)

    log.info("Building tasks and constraints...")
    subtasks: List[Subtask]
    constraints: nx.DiGraph
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, args.decomposition
    )
    log.info("Tasks and constraints built.")

    agent = Agent()  # Agent 초기화 (reset 로직은 Agent 내부에 있을 것으로 추정)
    scheduler = Scheduler(
        BEAM_WIDTH, SIMULATION_DEPTH, nav_graph=nav_graph, agent=agent
    )
    initial_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

    if args.visualize:
        log.info("Visualizing initial task graph...")
        visualize(approach_name, input_natural_language, constraints)

    final_state, computation_time, simulation_time = run_simulation_loop(
        initial_state, scheduler, agent, controller, args.log_level
    )

    result_schedule = process_and_log_results(final_state)

    if args.visualize and final_state:  # final_state가 None이 아닐 때만 시각화
        log.info("Visualizing final task plan...")
        visualize(
            approach_name,
            input_natural_language,
            final_state.constraints,  # 최종 상태의 제약조건 사용
            plan=result_schedule,
        )

    # 결과 저장
    sim_approach_name = f"{approach_name}_simulation"
    result_args = {
        "task_name": input_natural_language,
        "approach_name": sim_approach_name,
        "result_schedule": result_schedule,  # CompletedEntry 리스트 전달
        "computation_time": computation_time,
        "scene_name": SCENE_NAME,
        "constraints": constraints,  # 초기 제약조건 사용 또는 final_state.constraints
        "simulationTime": simulation_time,
    }
    log.info(
        f"Saving results for task '{input_natural_language}' with approach '{sim_approach_name}'..."
    )
    result_save(**result_args)
    log.info("Results saved.")

    # Controller 종료 (필요한 경우)
    # controller.stop()
    log.info("Task Scheduler finished.")


if __name__ == "__main__":
    main()
