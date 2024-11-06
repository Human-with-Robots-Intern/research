# main.py

import argparse
import json
import logging
import os
from pathlib import Path

import torch as th
import yaml
from concept.bayesian import TaskEstimator
from task_management.planner.schedule import (
    convert_tree_to_schedule,
    simulate_task_plan,
)
from tasks.decomposer import decompose_tasks
from tasks.task import parse_constraints, parse_tasks

import omnigibson as og
from core.exhaustive_planner import ExhaustivePlanner
from omnigibson.action_primitives.action_primitive_set_base import (
    ActionPrimitiveErrorGroup,
)
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm
from omnigibson.utils.ui_utils import create_module_logger
from utils.task_generator import generate_task_by_llm
from utils.util import ROOT_PATH
from utils.visualizer import visualize

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=__name__)
# file_handler = logging.FileHandler(f"./src/simulation/logs/{__name__}.log", "a")
log_path = Path(ROOT_PATH / "logs")
log_path.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(f"{log_path}/{__name__}.log", "a")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

log.addHandler(file_handler)
gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True


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

    file_path = os.path.join(
        ROOT_PATH,
        f"assets/tasks/task_{task_name}.json",
    )

    with open(file_path, "r") as file:
        task_data = json.load(file)

    tasks = parse_tasks(task_data)
    tasks = decompose_tasks(tasks)
    constraints = parse_constraints(tasks)

    return task_name, tasks, constraints


def execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def load_config():
    # # Load the config
    config_filename = os.path.join(og.example_config_path, "fetch_primitives.yaml")
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    # Update it to run a grocery shopping task
    config["scene"]["not_load_object_categories"] = [
        "ceilings",
        "pot_plant",
        "straight_chair",
    ]
    config["scene"]["load_room_types"] = ["living_room"]
    config["scene"]["load_room_instances"] = ["living_room_0"]
    config["objects"] = [
        {
            "type": "DatasetObject",
            "name": "apple",
            "category": "apple",
            "model": "agveuv",
            "position": [-0.3, -1.1, 0.5],
            "orientation": [0, 0, 0, 1],
        },
    ]
    return config


def execute_task():
    table = scene.object_registry("name", "breakfast_table_skczfi_0")
    apple = scene.object_registry("name", "apple")

    try:
        execute_controller(
            controller.apply_ref(StarterSemanticActionPrimitiveSet.NAVIGATE_TO, apple),
            env,
        )

    except ActionPrimitiveErrorGroup as e:
        log.error(f"Failed to execute action primitives: {e}")

    og.clear()


if __name__ == "__main__":
    args = parse_arguments()

    # Initialize environment and agent
    env = og.Environment(configs=load_config())
    scene = env.scene
    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)

    # Task plan generation
    task_name, tasks, constraints = load_tasks_and_constraints(args.name)
    planner = ExhaustivePlanner(tasks, constraints)
    task_plans, opt_task_plans = planner.generate_valid_plans()

    # task_plans to schedule & simulate it
    opt_task_plan = convert_tree_to_schedule(opt_task_plans)
    simulated_task_plan = simulate_task_plan(opt_task_plan)

    # Task plan visualization
    if args.visualize:
        visualize(task_name, constraints, task_plans, opt_task_plans)

    # Estimate task durations using Bayesian estimation
    estimator = TaskEstimator()
    estimator.estimate_tasks(opt_task_plan, simulated_task_plan)
