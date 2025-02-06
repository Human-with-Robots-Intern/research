import argparse

from core.agent import Agent
from core.scheduler import Scheduler
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.constants import LOG_ROUND
from utils.task import (
    build_tasks_and_constraints,
    get_init_state,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)

log = create_module_logger(module_name=__name__, is_file_handler=True)


def parse_arguments():
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
        "-s",
        "--simulation",
        action="store_true",
    )
    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    if args.simulation:
        controller = init_ai2thor()

    task_files = list_task_files()
    task_file_name = get_user_task_choice(task_files, choice=1)

    # Load the chosen task data
    task_data = load_task_data_from_file(task_file_name)

    # Build tasks and constraints
    subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)

    # Visualize the task graph if enabled
    if args.visualize:
        visualize(task_file_name, constraints)

    agent = Agent()

    scheduler = Scheduler()

    result_schedule = []
    current_state = get_init_state(subtasks, constraints)
    is_end = False

    while not is_end:

        next_state = scheduler.get_next_state(current_state)

        if next_state is None:
            log.error("No feasible solution found.")
            break

        if args.simulation:
            execute_subtask(controller, next_state.subtask)

        # TODO Simulation 수행 결과값을 얻어야 함. 지금은 스케쥴러에서 줌
        if next_state.subtask.type == "Monitor":
            agent.bayesian_estimate(next_state)

        current_state = next_state

        result_schedule.append(current_state.subtask)
        visualize(task_file_name, current_state.constraints, result_schedule)

        if not current_state.remaining_subtasks:
            is_end = True

    for subtask in current_state.completed_subtasks:
        log.info(
            f"{subtask.subtask.name} ({round(subtask.start_time, LOG_ROUND)} ~ {round(subtask.end_time,LOG_ROUND)})"
        )


if __name__ == "__main__":
    main()
