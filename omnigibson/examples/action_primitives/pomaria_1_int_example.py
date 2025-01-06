import argparse
import os

import yaml
import torch as th
import time
import omnigibson as og
from omnigibson import object_states
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm
from omnigibson.utils.ui_utils import create_module_logger

# Don't use GPU dynamics and use flatcache for performance boost
# gm.USE_GPU_DYNAMICS = True
# gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=os.path.basename(__file__), is_file_handler=True)


def execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def init_scene():

    # Load the config
    config_filename = os.path.join(og.example_config_path, "fetch_primitives.yaml")
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    # Update it to run a grocery shopping task
    config["scene"]["scene_model"] = "Pomaria_1_int"
    config["scene"]["not_load_object_categories"] = [
        "ceilings",
        "rocking_chair",
        "straight_chair",
        "floor_lamp",
        # "pool_table",
        "breakfast_table",
        # "coffee_table", #이거 세개중에 있음.
        "commercial_kitchen_table",
        "conference_table",
        "console",
    ]

    # Load the environment

    env = og.Environment(configs=config)
    scene = env.scene
    robot = env.robots[0]
    return env, scene


def main():
    """
    Demonstrates how to use the action primitives to pick and place an object in a crowded scene.

    It loads Rs_int with a robot, and the robot picks and places an apple.
    """

    parser = argparse.ArgumentParser(description="안녕? 액션을 테스팅해보자!")
    parser.add_argument(
        "-c",
        "--case",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help=(
            "Choose a case:\n"
            "  1) pick & place\n"
            "  2) open & close\n"
            "  3) on & off"
        ),
    )
    args = parser.parse_args()  # ArgumentParser 객체의 parse_args 호출로 인수 파싱
    start_time = time.time()
    env, scene = init_scene()
    end_time = time.time()
    log.info(f"Scene initialization time: {end_time - start_time:.2f}s")

    # Allow user to move camera more easily
    og.sim.enable_viewer_camera_teleoperation()

    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)


"""
    # objects
    switch1 = scene.object_registry("name", "electric_switch_wseglt_1")
    switch2 = scene.object_registry("name", "electric_switch_wseglt_2")
    apple = scene.object_registry("name", "apple")
    cabinet = scene.object_registry("name", "bottom_cabinet_bamfsz_0")

    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.TOGGLE_ON, switch1),
        env,
    )
    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple),
        env,
    )
    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.PLACE_ON_TOP, cabinet),
        env,
    )
    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.TOGGLE_ON, switch2),
        env,
    )
    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.TOGGLE_OFF, switch1),
        env,
    )
"""

if __name__ == "__main__":
    main()
