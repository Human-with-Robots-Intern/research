import argparse
import json
from pathlib import Path

# from runner import execute_task, init_omnigibson
from core import Task, TaskGraphBuilder, TaskTimingPlanner
from omnigibson.utils.ui_utils import create_module_logger
from sim.runner import execute_subtask, init_omnigibson
from utils import generate_task, visualize
from utils.constants import TASK_PATH

log = create_module_logger(module_name=__name__, is_file_handler=True)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the goal [laundry, cook, toast, etc.]",
        default="task_Store_Apple_in_Cabinet",
    )
    parser.add_argument(
        "-d",
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
    parser.add_argument(
        "-r",
        "--reset",
        help="Reset the knowledge base to Gaussian",
        action="store_true",
    )
    return parser.parse_args()


def load_task_data(task_name: str) -> tuple:
    """Load task data from a JSON file."""
    if task_name == "new":
        try:
            task_name = generate_task()
        except ValueError as e:
            raise ValueError(f"Error generating task: {e}")

    file_path = Path(TASK_PATH) / f"{task_name}.json"

    if not file_path.exists():
        raise FileNotFoundError(f"Task file not found: {file_path}")

    with open(file_path, "r") as file:
        return task_name, json.load(file)


def load_tasks_and_constraints(task_data: list[dict], enable_decomposition: bool):
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

    #  ========= Initialization =========
    # 명령 -> task.json
    task_name, task_data = load_task_data(args.name)
    # task.json -> task, task_graph (task, constraints 객체로 변환)
    tasks, task_graph = load_tasks_and_constraints(task_data, args.decomposition)
    # omnigibson 환경 로드
    env, agent = init_omnigibson()
    if args.reset:
        agent.reset_knowledge_to_gaussian()

    #  ========= Task Scheduling =========
    task_timing_planner = TaskTimingPlanner(
        agent=agent, tasks=tasks, constraints=task_graph
    )

    task_tree, opt_task_tree = task_timing_planner.get_task_trees()
    scheduled_subtasks = task_timing_planner.convert_to_tasks(opt_task_tree)

    #  ========= Task Execution =========
    try:
        for scheduled_subtask in scheduled_subtasks:
            execute_subtask(env, agent, scheduled_subtask)
    except Exception as e:
        log.error(f"Error executing task: {e}")

    # Result Visualization
    if args.visualize:
        visualize(task_name, task_graph, task_tree, opt_task_tree)


if __name__ == "__main__":
    main()
