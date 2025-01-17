import argparse
import json
from datetime import datetime
from pathlib import Path

from core import Task, TaskGraphBuilder, TaskTimingPlanner

# from omnigibson.utils.ui_utils import create_module_logger
# from sim.runner import execute_subtask, init_omnigibson
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import generate_task, visualize
from utils.constants import TASK_PATH

# log = create_module_logger(module_name=__name__, is_file_handler=True)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument("-n", help="Select the natural instruction")
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
        default=False,
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
        help="select simulation(o: omnigibson / a: ai2thor)",
        default=False,
        action="store_true",
    )
    return parser.parse_args()


def load_task_data(env):
    """Load task data from a JSON file."""
    task_files = list(TASK_PATH.glob("*.json"))

    print("Select a file from the list below:")
    print("0. new instruction")
    for idx, file in enumerate(task_files, start=1):
        print(f"{idx}. {file.name}")

    while True:
        try:
            choice = int(input("Enter the number of your choice: "))

            if choice == 0:
                target_task_name = generate_task(env)
                break
            elif 1 <= choice <= len(task_files):
                target_task_name = task_files[choice - 1].name
                break
            else:
                print(
                    f"Invalid choice. Please select a number between 0 and {len(task_files)}."
                )
        except ValueError as e:
            print(f"Invalid input. Please enter a number. Error: {e}")

    target_task_path = TASK_PATH / target_task_name

    if not target_task_path.exists():
        raise FileNotFoundError(f"Task file not found: {target_task_path}")

    with open(target_task_path, "r") as file:
        return target_task_name, json.load(file)


def load_tasks_and_constraints(task_data, enable_decomposition):
    """Parse tasks and build task graph."""
    tasks = Task.parse_instruction(task_data)
    if enable_decomposition:
        for task in tasks:
            task.decompose_subtasks()

    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)

    return tasks, task_graph


def check_simulation():

    print("Select a simulation from the list below:")
    print("o: omnigibson")
    print("a: ai2thor")

    choice = str(input("Enter the alphabet of your choice: ")).lower()

    return choice


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    # sim_name = check_simulation()
    # agent, env = None, None
    # if sim_name == "o":  # To initialize with OmniGibson
        # env, agent = init_omnigibson()
    #     if args.reset:
    #         agent.reset_knowledge_to_gaussian()
    # if sim_name == "a":  # To initialize with ai2thor
    #     env, controller = init_ai2thor()

    env, controller = init_ai2thor()

    # Load task data
    task_name, task_data = load_task_data(env)

    # Parse tasks and build graph
    tasks, task_graph = load_tasks_and_constraints(task_data, args.decomposition)

    # Initialize OmniGibson or ai2thor environment

    # if args.reset:
    #     agent.reset_knowledge_to_gaussian()

    # Task scheduling
    task_timing_planner = TaskTimingPlanner(
        agent=agent, tasks=tasks, constraints=task_graph
    )
    task_tree, opt_task_tree = task_timing_planner.get_task_trees()
    scheduled_subtasks = task_timing_planner.convert_to_tasks(opt_task_tree)

    # # Task execution
    # if sim_name == "o" and env:
    #     try:
    #         for scheduled_subtask in scheduled_subtasks:
    #             execute_subtask(env, agent, scheduled_subtask)
    #     except Exception as e:
    #         # log.error(f"Error executing task: {e}")
    #         raise Exception
    # if sim_name == "a" and controller:
    try:
        for scheduled_subtask in scheduled_subtasks:
            execute_subtask(controller, scheduled_subtask)
    except Exception as e:
        # log.error(f"Error executing task: {e}")
        raise Exception

    # Result visualization
    if args.visualize:
        visualize(task_name, task_graph, task_tree, opt_task_tree)


if __name__ == "__main__":
    main()
