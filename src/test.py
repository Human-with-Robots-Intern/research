import argparse
import json
import time
from pathlib import Path

from core.agent import Agent
from core.task import SchedulerState, Subtask
from core.task_tree_builder_beam import Scheduler
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import visualize
from utils.task_io import (
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)
from utils.task_util import adjust_subtasks_duration, build_tasks_and_constraints
from utils.util import create_module_logger

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

    init_subtask = Subtask(
        task_name=None,
        name="Init",
        duration=0.0,
        repetition=1,
        type="Init",
        execution=None,
        temporal_constraints=None,
    )

    scheduler = Scheduler(subtasks, constraints)
    current_state = SchedulerState(
        subtask=init_subtask,
        completed_subtasks=[],
        remaining_subtasks=subtasks,
        agent_location="agent",
    )

    while current_state.remaining_subtasks:

        current_state = scheduler.get_new_state(current_state, constraints)
        if current_state is None:
            # 스케줄링 더 이상 불가
            log.warning("No valid next subtask. Stopping.")
            break

        if args.simulation:
            execute_subtask(controller, current_state.subtask)

    if args.visualize:
        visualize(
            task_file_name,
            constraints,
            current_state.completed_subtasks + [current_state.subtask],
        )


if __name__ == "__main__":
    main()
