import argparse
import json
import os

from concept.agent import Agent
from concept.env import Env
from concept.task import Task, parse_constraints, parse_tasks
from task_management.handler.subtask_decomposer import SubtaskDecomposer
from task_management.planner.exhaustive_planner import ExhaustivePlanner
from task_management.scheduler.exhaustive_scheduler import ExhaustiveScheduler
from util.visualizer import visualize_graph, visualize_tree


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-name",
        help="Select the Goal [all, laundry, cook, toast]",
        choices=["all", "laundry", "cook", "toast"],
        default="cook",
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
    # Decompose tasks into batches
    batch_decomposer = SubtaskDecomposer(batch_duration=5)
    decomposed_tasks = [
        Task(task.name, batch_decomposer.decompose(task)) for task in tasks
    ]
    print(decomposed_tasks)

    # Parse constraints using decomposed tasks
    constraints = parse_constraints(decomposed_tasks)

    return tasks, constraints


def main():
    args = parse_arguments()

    tasks, constraints = load_tasks_and_constraints(args.name)
    visualize_graph(constraints)

    env = Env()
    env.gen_dummy()
    agent = Agent("Waiting", "Living Room", env)

    task_plans = ExhaustivePlanner(agent, tasks, constraints).generate_valid_plans()
    visualize_tree(task_plans)
    task_schedule = ExhaustiveScheduler(task_plans)

    # visualize_schedule(task_schedule)


if __name__ == "__main__":
    main()
