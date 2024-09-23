import argparse
import json
import os
from datetime import datetime

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_constraints, parse_tasks
from task_management.handler.subtask_decomposer import decompose_tasks
from task_management.planner.exhaustive_planner import ExhaustivePlanner
from utils.task_generator import generate_task_by_llm
from utils.visualizer import plot_gantt_chart, visualize_graph, visualize_tree


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the Goal [all, laundry, cook, toast etc.]",
        default=None,
    )

    return parser.parse_args()


def load_tasks_and_constraints(task_name):
    if task_name is None:
        task_name = generate_task_by_llm()

    file_path = os.path.join("assets/tasks", f"task_{task_name}.json")

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    tasks = decompose_tasks(tasks)
    constraints = parse_constraints(tasks)

    return task_name, tasks, constraints


def visualize(task_name, constraints, task_plans, opt_task_plans):
    save_path = "assets/results/"
    folder_name = datetime.now().strftime("%Y-%m-%d_%H") + f"_{task_name}"
    save_folder_path = os.path.join(save_path, folder_name)
    os.makedirs(
        save_folder_path, exist_ok=True
    )  # Create the folder if it doesn't exist

    visualize_graph(constraints, save_folder_path)
    visualize_tree(task_plans, opt_task_plans, save_folder_path)
    plot_gantt_chart(opt_task_plans, save_folder_path)
    print()

def gen_task_plan():
    args = parse_arguments()

    task_name, tasks, constraints = load_tasks_and_constraints(args.name)

    env = Env()
    env.gen_dummy()

    agent = Agent("Waiting", "Living Room", env)

    task_plans, opt_task_plans = ExhaustivePlanner(
        agent, tasks, constraints
    ).generate_valid_plans()

    visualize(task_name, constraints, task_plans, opt_task_plans)


if __name__ == "__main__":
    gen_task_plan()
