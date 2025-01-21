import argparse
import json
import time

from core import Task, TaskGraphBuilder, TaskTimingPlanner
from core.agent import BayesianAgent
from utils.util import create_module_logger

# from sim.runner import execute_subtask, init_omnigibson
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import generate_task, visualize
from utils.constants import TASK_PATH
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
        help="select simulation(o: omnigibson / a: ai2thor)",
        default=False,
        action="store_true",
    )
    return parser.parse_args()


def check_place(tasks):
    # list-dict("Subtasks")-list-dict("Executions")-dict("PrimitiveActions")-list
    for task in tasks:
        for subtask in task["Subtasks"]:
            actions = subtask["Executions"]["PrimitiveActions"]
            updated_actions = []
            for i, action in enumerate(actions):
                if i > 0 and "PLACE" in action and "NAVIGATE" not in actions[i - 1]:
                    to_obj = action.split(" ")[1]
                    updated_actions.append(f"NAVIGATE_TO {to_obj}")
                updated_actions.append(action)
            subtask["Executions"]["PrimitiveActions"] = updated_actions
    return tasks


def load_task_data():
    """Load task data from a JSON file."""
    task_files = sorted(TASK_PATH.glob("*.json"), key=lambda p: p.name)

    print("Select a file from the list below:")
    print("0. new instruction")
    for idx, file in enumerate(task_files, start=1):
        print(f"{idx}. {file.name}")

    while True:
        try:
            choice = int(input("Enter the number of your choice: "))

            if choice == 0:
                target_task_name = generate_task()
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
        target_task = json.load(file)  # 일단 불러오기
    target_task = check_place(target_task)
    print(target_task)
    return target_task_name, target_task


def load_tasks_and_constraints(task_data, enable_decomposition):
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

    # Initialize ai2thor environment
    controller = init_ai2thor()

    # Load task data
    task_name, task_data = load_task_data()

    # Parse tasks and build graph
    tasks, task_graph = load_tasks_and_constraints(task_data, args.decomposition)
    visualize(task_name, task_graph)
    agent = BayesianAgent(None)
    # Task scheduling
    start_time = time.time()
    task_timing_planner = TaskTimingPlanner(
        agent=agent, tasks=tasks, constraints=task_graph
    )
    task_tree, opt_task_tree = task_timing_planner.get_task_trees()
    elapsed_time = time.time() - start_time
    log.info(f"Task {task_name} scheduled in {elapsed_time:.2f} seconds")
    # Scheduling 결과 sequence of subtasks
    scheduled_subtasks = task_timing_planner.convert_to_tasks(opt_task_tree)

    # Task execution
    # try:
    for scheduled_subtask in scheduled_subtasks:
        print(f"{scheduled_subtask=}")
        execute_subtask(controller, scheduled_subtask)
    # except Exception as e:
    #     # log.error(f"Error executing task: {e}")
    #     raise Exception

    # Result visualization
    # if args.visualize:
    #     visualize(task_name, task_graph, task_tree, opt_task_tree)


if __name__ == "__main__":
    main()
