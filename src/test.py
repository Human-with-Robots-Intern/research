import argparse
import json
import os

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_constraints, parse_tasks
from task_management.handler.subtask_decomposer import decompose_tasks
from task_management.planner.exhaustive_planner import ExhaustivePlanner
from utils.task_generator import generate_task_by_llm
from utils.util import get_paths_to_leaves
from utils.visualizer import visualize


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the Goal [all, laundry, cook, toast etc.]",
        default="cook",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        type=bool,
        help="True is save results else is don't",
        default=False,
    )

    return parser.parse_args()


def load_tasks_and_constraints(task_name="cook"):
    if task_name is None:
        task_name = generate_task_by_llm()

    file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        f"assets/tasks/task_{task_name}.json",
    )

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    tasks = decompose_tasks(tasks)
    constraints = parse_constraints(tasks)

    return task_name, tasks, constraints


if __name__ == "__main__":
    args = parse_arguments()

    # Initialize env, agent
    env = Env()
    env.gen_dummy()
    agent = Agent("Waiting", "Living Room", env)

    # Task Plan generation
    task_name, tasks, constraints = load_tasks_and_constraints(args.name)
    task_plans, opt_task_plans = ExhaustivePlanner(
        agent, tasks, constraints
    ).generate_valid_plans()
    opt_task_paths = get_paths_to_leaves(opt_task_plans)

    # Task Plan Visualization
    if args.visualize:
        visualize(task_name, constraints, task_plans, opt_task_plans)

    print(opt_task_paths)
