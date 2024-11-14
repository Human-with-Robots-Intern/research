import logging
from pathlib import Path

import torch as th
import yaml

import omnigibson as og
from core.agent import Agent
from omnigibson.action_primitives.action_primitive_set_base import (
    ActionPrimitiveErrorGroup,
)
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm
from omnigibson.utils.ui_utils import create_module_logger
from utils.util import ROOT_PATH

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=__name__)

log_path = Path(ROOT_PATH) / "logs"
log_path.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(f"{log_path}/{__name__}.log", "a")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
log.addHandler(file_handler)

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True


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
    agent = Agent(env.robots[0])
    return env, agent


def _execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def execute_task(env):
    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)
    table = env.scene.object_registry("name", "breakfast_table_skczfi_0")
    apple = env.scene.object_registry("name", "apple")

    try:
        _execute_controller(
            controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple),
            env,
        )

    except ActionPrimitiveErrorGroup as e:
        log.error(f"Failed to execute action primitives: {e}")

    og.clear()
