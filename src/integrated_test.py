import argparse
import json
from pathlib import Path

# from runner import execute_task, init_omnigibson
from core import Task, TaskGraphBuilder, TaskTimingPlanner
from runner import execute_task, init_omnigibson
from utils import generate_task, visualize
from utils.constants import TASK_PATH


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the goal [laundry, cook, toast, etc.]",
        default="Prepare_Coffee",
    )
    parser.add_argument(
        "-de",
        "--decomposition",
        help="Enable or disable decomposition",
        action="store_true",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        help="Enable visualization of the task plan",
        action="store_true",
    )
    return parser.parse_args()


def load_task_data(task_name: str) -> dict:
    """Load task data from a JSON file."""
    if task_name == "new":
        try:
            task_name = generate_task()
        except ValueError as e:
            raise ValueError(f"Error generating task: {e}")

    file_path = Path(TASK_PATH) / f"task_{task_name}.json"

    if not file_path.exists():
        raise FileNotFoundError(f"Task file not found: {file_path}")

    with open(file_path, "r") as file:
        return task_name, json.load(file)


def load_tasks_and_constraints(task_data: dict, enable_decomposition: bool):
    """Parse tasks and build task graph."""
    tasks = Task.parse_instruction(task_data)
    if enable_decomposition:
        for task in tasks:
            task.decompose_subtasks()

    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)

    return tasks, task_graph


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    task_name, task_data = load_task_data(args.name)
    tasks, task_graph = load_tasks_and_constraints(task_data, args.decomposition)
    env, agent = init_omnigibson()

    task_timing_planner = TaskTimingPlanner(
        agent=agent, tasks=tasks, constraints=task_graph
    )

    task_trees = task_timing_planner.get_task_trees()

    execute_task(env)
    if args.visualize:
        visualize(task_name, task_graph, *task_trees)


if __name__ == "__main__":
    main()
