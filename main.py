import argparse
import json
import os

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_constraints, parse_tasks
from scheduler.exhaustive_scheduler import ExhaustiveScheduler
from util.visualizer import visualize4


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-name",
        help="Select the Goal [all, laundry, cook]",
        choices=["all", "laundry", "cook"],
        default="all",
    )
    return parser.parse_args()


def load_tasks_and_constraints(task_name):
    file_mapping = {
        "all": "task.detach.json",
        "cook": "task.cook.json",
        "laundry": "task.laundry.json",
    }

    file_name = file_mapping.get(task_name, "task.detach.json")
    file_path = os.path.join("asset", file_name)

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    constraints_graph = parse_constraints(task_data)

    return tasks, constraints_graph


def main():
    args = parse_arguments()

    tasks, constraints_graph = load_tasks_and_constraints(args.name)

    env = Env()
    env.gen_dummy()

    agent = Agent("Waiting", "Living Room", env)

    scheduler = ExhaustiveScheduler(agent, tasks, constraints_graph)
    task_schedule = scheduler.generate_schedule()

    visualize4(task_schedule)


if __name__ == "__main__":
    main()
