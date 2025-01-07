import argparse
import os

import yaml
import torch as th

import omnigibson as og
from omnigibson import object_states
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm

# Don't use GPU dynamics and use flatcache for performance boost
# gm.USE_GPU_DYNAMICS = True
# gm.ENABLE_FLATCACHE = True


def execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def init_scene():

    # Load the config
    config_filename = os.path.join(og.example_config_path, "fetch_primitives.yaml")
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    # Update it to run a grocery shopping task
    config["scene"]["scene_model"] = "Rs_int"
    config["scene"]["not_load_object_categories"] = [
        "ceilings",
        "rocking_chair",
        "straight_chair",
        "floor_lamp",
        # "breakfast_table",
        "pot_plant",
    ]
    config["objects"] = [
        {
            "type": "DatasetObject",
            "name": "apple1",
            "category": "apple",
            "model": "agveuv",
            "position": [-0.3, -1.1, 0.5],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "apple2",
            "category": "apple",
            "model": "omzprq",
            "position": [-0.3, -1.3, 0.5],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "apple3",
            "category": "apple",
            "model": "rizrsp",
            "position": [-0.3, -1.4, 0.5],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "banana1",
            "category": "banana",
            "model": "znakxm",
            "position": [-0.3, -1.5, 0.5],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "trash_can1",
            "category": "trash_can",
            "model": "zotrbg",
            "position": [-0.7, 1.0, 0.3],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "trash_can2",
            "category": "trash_can",
            "model": "zotrbg",
            "position": [0.0, 1.0, 0.3],
            "orientation": [0, 0, 0, 1],
        },
        {
            "type": "DatasetObject",
            "name": "storage_box1",
            "category": "storage_box",
            "model": "kjidns",
            "position": [0.0, 0.5, 0.2],
            "orientation": [0, 0, 0, 1],
        },
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
    env, scene = init_scene()

    # Allow user to move camera more easily
    og.sim.enable_viewer_camera_teleoperation()
    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)

    # Pick and Place

    apple1 = scene.object_registry("name", "apple1")
    apple2 = scene.object_registry("name", "apple2")
    apple3 = scene.object_registry("name", "apple3")
    banana1 = scene.object_registry("name", "banana1")
    trash_can1 = scene.object_registry("name", "trash_can1")
    trash_can2 = scene.object_registry("name", "trash_can2")
    storage_box1 = scene.object_registry("name", "storage_box1")

    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple1),
        env,
    )
    execute_controller(
        controller.apply_ref(
            StarterSemanticActionPrimitiveSet.PLACE_INSIDE, storage_box1
        ),
        env,
    )
    execute_controller(
        controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple2),
        env,
    )
    execute_controller(
        controller.apply_ref(
            StarterSemanticActionPrimitiveSet.PLACE_INSIDE, trash_can2
        ),
        env,
    )


if __name__ == "__main__":
    main()
