import argparse
import json
import os
import sys

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_constraints, parse_tasks
from task_management.planner.exhaustive_planner import ExhaustivePlanner
from util.visualizer import visualize_graph


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-name",
        help="Select the Goal [all, laundry, cook, toast etc.]",
        default="toast",
    )
    return parser.parse_args()


def load_tasks_and_constraints(task_name):
    file_path = os.path.join("asset", f"task_{task_name}.json")

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    constraints = parse_constraints(tasks)
    visualize_graph(constraints, is_display=False)

    return tasks, constraints


def main():
    args = parse_arguments()

    tasks, constraints = load_tasks_and_constraints(args.name)

    env = Env()
    env.gen_dummy()
    agent = Agent("Waiting", "Living Room", env)

    task_plans = ExhaustivePlanner(agent, tasks, constraints).generate_valid_plans()


if __name__ == "__main__":
    main()
