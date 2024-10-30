import logging
import os

import omnigibson as og
import torch as th
import yaml
from omnigibson.action_primitives.action_primitive_set_base import (
    ActionPrimitiveErrorGroup,
)
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm
from omnigibson.utils.ui_utils import create_module_logger

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=__name__)
file_handler = logging.FileHandler("./src/simulation/logs/app.log", "a")
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(file_formatter)

log.addHandler(file_handler)


def execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def main():
    # Define tasks
    tasks = ["find bread", "pick bread", "place bread in toaster"]

    # # Load the config
    config_filename = os.path.join("src/simulation/fetch_primitives.yaml")
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

    # Load the environment
    env = og.Environment(configs=config)
    scene = env.scene

    # Allow user to move camera more easily
    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)
    table = scene.object_registry("name", "breakfast_table_skczfi_0")
    apple = scene.object_registry("name", "apple")

    try:
        # Grasp apple
        print("Executing controller")

        execute_controller(
            controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple), env
        )
        print("Finished executing grasp")

        # Place on table
        print("Executing controller")

        execute_controller(
            controller.apply_ref(StarterSemanticActionPrimitiveSet.PLACE_ON_TOP, table),
            env,
        )
        print("Finished executing place")
    except ActionPrimitiveErrorGroup as e:
        log.error(f"Failed to execute action primitives: {e}")

    # Always shut down the environment cleanly at the end
    og.clear()


if __name__ == "__main__":
    main()
