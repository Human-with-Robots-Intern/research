import argparse
import json
import os

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_constraints, parse_tasks
from scheduler.exhaustive_scheduler import ExhaustiveScheduler
from util.visualizer import visualize_graph, visualize_schedule


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-name",
        help="Select the Goal [all, laundry, cook, toast]",
        choices=["all", "laundry", "cook", "toast"],
        default="laundry",
    )
    return parser.parse_args()


def load_tasks_and_constraints(task_name):
    file_mapping = {
        "all": "task_all.json",
        "cook": "task_cook.json",
        "laundry": "task_laundry.json",
        "toast": "task_toast.json",
    }

    file_name = file_mapping.get(task_name, "task_all.json")
    file_path = os.path.join("asset", file_name)

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    constraints = parse_constraints(task_data)

    return tasks, constraints


def main():
    args = parse_arguments()

    tasks, constraints = load_tasks_and_constraints(args.name)
    visualize_graph(constraints)

    env = Env()
    env.gen_dummy()

    agent = Agent("Waiting", "Living Room", env)

    scheduler = ExhaustiveScheduler(agent, tasks, constraints)
    task_schedule = scheduler.generate_schedule()

    visualize_schedule(task_schedule)


if __name__ == "__main__":
    main()
