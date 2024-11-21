import logging
import sys
from pathlib import Path

import torch as th
import yaml

import omnigibson as og
from core import BayesianAgent
from omnigibson.action_primitives.action_primitive_set_base import (
    ActionPrimitiveErrorGroup,
)
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm
from omnigibson.utils.ui_utils import create_module_logger
from sim.primitive_actions import CustomActionPrimitives
from utils.constants import LOG_PATH

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=__name__)

file_handler = logging.FileHandler(f"{LOG_PATH}/{__name__}.log", "a")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
log.addHandler(file_handler)


def _load_config():
    # # Load the config
    config_filename = Path(og.example_config_path) / "fetch_primitives.yaml"
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


def init_omnigibson():
    # Initialize environment and agent
    env = og.Environment(configs=_load_config())

    agent = BayesianAgent(env.robots[0])

    return env, agent


def execute_task(env, agent):
    controller = CustomActionPrimitives(env, agent)

    table = env.scene.object_registry("name", "breakfast_table_skczfi_0")
    apple = env.scene.object_registry("name", "apple")

    try:
        controller.apply_primitive_action(
            StarterSemanticActionPrimitiveSet.GRASP, apple
        )
        controller.apply_primitive_action(
            StarterSemanticActionPrimitiveSet.PLACE_ON_TOP, table
        )
    except ActionPrimitiveErrorGroup as e:
        log.error(f"Failed to execute action primitives: {e}")

    og.clear()
