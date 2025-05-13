import argparse
import time

from ithor.handlers.navigation_handler import load_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.core import Agent, Scheduler
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from utils.common.logger import create_module_logger
from utils.config import BEAM_WIDTH, LOG_ROUND, SIMULATION_DEPTH
from utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
    result_save,
)
from utils.io_utils.task_io import get_user_scene_choice
from utils.task import TaskUtil

log = create_module_logger(__name__, module_log=True)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

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


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    approach_name = "dag_bayesian"

    # Set up the AI2-THOR controller and navigation graph
    scene_data = get_user_scene_choice()
    controller = init_ai2thor_controller(scene=scene_data.file_name.split("_")[0])
    nav_graph = load_navigation_graph(controller)

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)

    # task_file_name을 입력 자연어로 번역
    input_natural_language = (
        get_natural_language_from_task_file(f"{choice}")
        if choice is not None
        else task_file_name
    )

    # Build tasks and constraints
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, scene_data.file_name
    )

    # Initialize the agent and scheduler
    action_handler = ActionHandler(nav_graph or {})
    constraint_handler = ConstraintHandler(action_handler)
    agent = Agent(constraint_handler)
    cost_calculator = HeuristicManager(action_handler, agent)
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=cost_calculator,
    )
    current_state = TaskUtil.get_init_state(
        subtasks, constraints, scene_data.object_positions
    )

    result_schedule = []
    is_end = False

    total_compute_time, total_sim_time = 0, 0

    while not is_end:
        next_state, computation_elapsed_time = scheduler.get_next_state(current_state)
        total_compute_time += computation_elapsed_time

        if next_state is None:
            log.error("No feasible solution found.")
            break

        sim_elapsed_time, execution_status = execute_subtask(
            controller, next_state.subtask, args.log_level
        )

        # 시뮬레이션에서 흐른 시간과 실행 상태를 저장.
        last_entry = next_state.completed_entries[-1]
        last_entry.sim_start_time = total_sim_time
        last_entry.sim_end_time = total_sim_time + sim_elapsed_time
        last_entry.execution_status = execution_status
        total_sim_time += sim_elapsed_time

        if next_state.subtask.subtask_type == "Monitor":
            next_state, monitored_subtask = agent.bayesian_estimate(next_state)
            next_state.completed_entries[-1].monitored_subtask = monitored_subtask

        current_state = next_state

        if not current_state.remaining_subtasks:
            is_end = True

    for ce in current_state.completed_entries:
        if ce.subtask.name == "Init":
            continue

        log.info(
            f"{ce.subtask.name} ({round(ce.sim_start_time, LOG_ROUND)} ~ {round(ce.sim_end_time,LOG_ROUND)})"
        )
        log.info(f"Primitive actions: {ce.subtask.execution.primitive_actions}\n")
        # 지금 start time 과 end time은 scheduler가 계산 한 값이고 simulation을 했을때의 시간이 아니다.
        # ? 흠... ce.scheduled_start_time / end_time을 이용할 수는 없나?
        ce.start_time_scheduled = round(ce.sim_start_time, LOG_ROUND)
        ce.end_time_scheduled = round(ce.sim_end_time, LOG_ROUND)
        result_schedule.append(ce)

    approach_name = f"{approach_name}_simulation"
    result_args = {
        "task_name": input_natural_language,
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": total_compute_time,
        "scene_name": scene_data.file_name,
        "constraints": constraints,
        # "simulationTime": total_sim_time,
    }

    result_save(**result_args)


if __name__ == "__main__":
    main()
