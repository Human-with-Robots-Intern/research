# main.py

import argparse
import json
from pathlib import Path

from runner import execute_task, init_env
from src.core import Task, TaskGraphBuilder
from utils import ROOT_PATH, generate_task_by_llm, visualize


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the goal [laundry, cook, toast, etc.]",
        default="new",
    )
    parser.add_argument(
        "-d",
        "--decomposition",
        help="Select the decomposition setting [True, False]",
        default=False,
    )
    parser.add_argument(
        "-v",
        "--visualize",
        default=False,
        help="Enable visualization of the task plan",
    )
    return parser.parse_args()


def load_tasks_and_constraints(args):
    if args.name == "all":
        task_name = generate_task_by_llm()
    else:
        task_name = args.name

    file_path = Path(ROOT_PATH) / f"assets/tasks/task_{args.name}.json"

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = Task.parse_instruction(task_data)
    if args.decomposition:
        for task in tasks:
            task.decompose_subtasks()

    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)

    return task_name, tasks, task_graph


if __name__ == "__main__":
    args = parse_arguments()
    task_name, tasks, task_graph = load_tasks_and_constraints(args)

    if args.visualize:
        visualize(task_name, task_graph)

    # execute_task(*init_env())

    # # Task plan generation
    # task_name, tasks, constraints = load_tasks_and_constraints(args.name)
    # planner = ExhaustivePlanner(agent, tasks, constraints)
    # task_plans, opt_task_plans = planner.generate_valid_plans()

    # # task_plans to schedule & simulate it
    # opt_task_plan = convert_tree_to_schedule(opt_task_plans)
    # simulated_task_plan = simulate_task_plan(opt_task_plan)

    # # Task plan visualization
    # if args.visualize:
    #     visualize(task_name, constraints, task_plans, opt_task_plans)

    # # Estimate task durations using Bayesian estimation
    # estimator = TaskEstimator()
    # estimator.estimate_tasks(opt_task_plan, simulated_task_plan)
