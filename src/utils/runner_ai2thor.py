import json
import logging
import math
import os
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
from ai2thor.controller import Controller

sys.path.append("/home/bluebottle/workspace/research/ithor")  # ithor 폴더의 절대 경로


from ithor.handlers.action import Action
from ithor.handlers.camera_handler import CameraHandler
from ithor.handlers.navigation_handler import NavigationHandler
from utils.constants import *
from utils.constants import KNOWLEDGE_PATH


def load_scene_positions(
    file_name: str,
) -> dict[str, tuple[float, float, float]]:
    """
    Load scene positions from a JSON file.

    :param file_path: Path to the JSON file containing scene positions.
    :return: Dictionary containing scene positions.
    """
    file_path = KNOWLEDGE_PATH / file_name
    with open(file_path, "r") as f:
        scene_positions = json.load(f)
    for key, value in scene_positions.items():
        scene_positions[key] = tuple(value)
    return scene_positions


def create_module_logger(module_name, is_file_handler=False):
    """
    Creates and returns a logger for logging statements from the module represented by @module_name

    Args:
    module_name (str): Module to create the logger for. Should be the module's `__name__` variable

    Returns:
        Logger: Created logger for the module
    """

    logger = logging.getLogger(module_name)
    if is_file_handler:
        logger.setLevel("DEBUG")
        file_handler = logging.FileHandler(
            f"{ Path(__file__).resolve().parent.parent.parent}/logs/{module_name}.log",
            "a",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
    return logger


log_file = open(Path.cwd() / Path("logs/ai2thor_log.log"), "w", buffering=1)
log = create_module_logger(module_name=__name__, is_file_handler=True)


def init_ai2thor():
    controller = Controller(
        agentMode="default",  # "default", "locobot", "drone", or "arm",
        massThreshold=0.04,  # 물리 엔진에서 물체를 움직이는 최소 질량
        scene=SCENE_NAME,  # Scene 이름
        gridSize=GRID_SIZE,  # Move Actions의 Mean
        movementGaussianSigma=0.005,  # Move Actions의 Sigma
        renderDepthImage=False,  # Depth Image 렌더링 여부 (오랜 시간 소요)
        renderInstanceSegmentation=False,  # Instance Segmentation 렌더링 여부 (오랜 시간 소요)
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
        renderThirdPartyCameras=False,
        fieldOfView=60,
    )

    return controller


def find_objID(controller, obj_type):  ## object type과 object id를 매칭
    for obj in controller.last_event.metadata["objects"]:
        if obj["objectType"].lower() == obj_type:
            return obj["objectId"]
    return None


def last_action_success(controller):  ## 마지막 행동이 성공했는지 확인
    if controller.last_event.metadata["lastActionSuccess"]:
        return "success\n"
    else:
        return "failure\n"


def execute_subtask(controller, subtask):
    """
    Args:
        subtask: Subtask object containing execution details.
    """
    camera_handler = CameraHandler(controller)
    Navi = NavigationHandler(controller, camera_handler)
    Act = Action(controller, camera_handler, log_file)

    # Skip the Init subtask
    if subtask.name == "Init":
        return

    log_file.write(f"Executing Subtask: {subtask.name}\n")

    # Parse execution details
    execution = subtask.execution
    print("====================================")
    print("***********EXECUTION****************")
    print(f"{subtask=}")
    ## Wait의 형식을 맞춰주든가 여기서 처리를 하든가 해야함
    primitive_actions = execution.primitive_actions
    print("<<<ACTIONS>>>")
    for action in primitive_actions:
        print(action)
    objects = execution.objects

    # Read JSON file
    # with open(KNOWLEDGE_PATH / "knowledge.json", "r") as file:
    #     knowledge = json.load(file)
    # ground_truth = knowledge["Subtasks"]["Prepare Egg Fry(subtask.name 이 맞음)"]["expected_duration"]
    object_registry = {}

    # "NAVIGATE_TO laundry_hamper",
    # "GRASP clothes",
    # "NAVIGATE_TO washing_machine",
    # "PLACE_INSIDE washing_machine"
    if objects is not None:
        for obj_id in objects:
            ai2thor_obj = list(
                set(
                    obj["objectId"]
                    for obj in controller.step("Pass").metadata["objects"]
                )
            )
            if ai2thor_obj is None:
                log_file.write(f"Object '{obj_id}' not found in the environment.")
                return False
            object_registry[obj_id] = ai2thor_obj

    # Define action mapping to ai2thor action primitives
    action_mapping = {
        "NAVIGATE_TO": lambda target_obj: Navi.move_to(target_obj),
        "GRASP": lambda target_obj: Act.pickup(target_obj),
        "PLACE_INSIDE": lambda target_obj: Act.put(target_obj),
        "PLACE_ON_TOP": lambda target_obj: Act.put(target_obj),
        "OPEN": lambda target_obj: Act.open(target_obj),
        "CLOSE": lambda target_obj: Act.close(target_obj),
        "TOGGLE_ON": lambda target_obj: Act.toggleon(target_obj),
        "TOGGLE_OFF": lambda target_obj: Act.toggleoff(target_obj),
        "SLICE": lambda target_obj: Act.slice(target_obj),
        "MONITORING": lambda target_obj: Act.monitoring(target_obj),
        "WAIT": lambda duration: Act.wait(round(float(duration), 2)),
        "FILL": lambda target_obj: Act.fill(target_obj),
    }

    # Execute each primitive action
    elapsed_time = 0
    for action_str in primitive_actions:
        # Split action into type and target
        parts = action_str.split(" ", 1)
        if len(parts) != 2:
            log.warning(f"Invalid action format: {action_str}. Skipping.")
            raise ValueError(f"Invalid action format: {action_str}")

        action_type, target_obj_ID = parts
        if action_type in action_mapping:
            log.info(
                f"Performing action: {action_type} on {target_obj_ID.split('|')[0]}"
            )
            # 총 걸린시간 계산
            elapsed_time += action_mapping[action_type](target_obj_ID)
        else:
            log.warning(
                f"Unknown action type: {action_type}. Skipping {action_str} in {subtask.name}."
            )
    print(f"{subtask.name}의 걸린시간 = {round(elapsed_time, 2)}")
    log.info(f"Successfully executed Subtask: {subtask.name}")
    print("================END=================")
    print("====================================")
    return elapsed_time
