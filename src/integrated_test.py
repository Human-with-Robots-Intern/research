# main.py

import argparse
import json
from pathlib import Path

from core.task import (
    ScheduledTask,
    convert_tree_to_schedule,
    parse_constraints,
    parse_tasks,
    simulate_task_plan,
)
from runner import execute_task, init_env
from utils import ROOT_PATH, generate_task_by_llm, visualize

# from task_management.handler.subtask_decomposer import decompose_tasks
# from task_management.planner.exhaustive_planner import ExhaustivePlanner


def parse_arguments():
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-n",
        "--name",
        help="Select the goal [all, laundry, cook, toast, etc.]",
        default="cook",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        action="store_true",
        help="Enable visualization of the task plan",
    )
    return parser.parse_args()


def load_tasks_and_constraints(task_name="cook"):
    if task_name == "all":
        task_name = generate_task_by_llm()

    file_path = Path(ROOT_PATH) / f"assets/tasks/task_{task_name}.json"

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    tasks = decompose_tasks(tasks)
    constraints = parse_constraints(tasks)

    return task_name, tasks, constraints


if __name__ == "__main__":
    # args = parse_arguments()
    execute_task(*init_env())

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
