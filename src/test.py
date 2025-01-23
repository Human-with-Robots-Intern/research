import argparse
import json
import time
from pathlib import Path

from core.agent import BayesianAgent
from sim.runner_ai2thor import init_ai2thor
from task_management.task_tree_builder_beam import Scheduler
from utils import visualize
from utils.task_io import (
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)
from utils.task_util import build_tasks_and_constraints
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
    task_file_name = get_user_task_choice(task_files)

    # Load the chosen task data
    task_data = load_task_data_from_file(task_file_name)

    # Build tasks and constraints
    tasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)
    # Visualize the task graph if enabled
    if args.visualize:
        visualize(task_file_name, constraints)

    agent = BayesianAgent()

    scheduler = Scheduler(tasks, constraints)
    while True:
        scheduler.constraint_handler.update_constraints(constraints)
        current_subtask = scheduler.get_next_subtask(tasks, constraints)
        if current_subtask is None:
            break


if __name__ == "__main__":
    main()
