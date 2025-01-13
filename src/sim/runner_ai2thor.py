import random
import logging
from pathlib import Path

from ai2thor.controller import Controller

from ithor.handlers.arm_handler import ArmHandler
from ithor.handlers.camera_handler import CameraHandler
from ithor.handlers.interaction_handler import InteractionHandler
from ithor.handlers.move_handler import MoveHandler
from ithor.handlers.navigation_handler import NavigationHandler

from ithor.handlers.action import Action

from ithor.utils.constants import *

import numpy as np
import math
import time
import re


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


log_file = open("logs/ai2thor_log.txt", "w", buffering=1)
log = create_module_logger(module_name=__name__, is_file_handler=True)

def get_environment(controller):  # 최종 환경 추출
    scene_name = controller.step("Pass").metadata["sceneName"]
    objs = controller.step("Pass").metadata["objects"]
    openable = []
    toggleable = []
    pickupable = []
    for obj in objs:
        if obj["openable"]:
            openable.append(obj["objectType"])
        if obj["toggleable"]:
            toggleable.append(obj["objectType"])
        if obj["pickupable"]:
            pickupable.append(obj["objectType"])

    openable = list(set(openable))
    toggleable = list(set(toggleable))
    pickupable = list(set(pickupable))

    env = {
        scene_name: {
            "OPEN": openable,
            "CLOSE": openable,
            "TOGGLE_ON": toggleable,
            "TOGGLE_OFF": toggleable,
            "GRASP": pickupable
        }
    }

    return env # prompt 에 쓸 땐 str(env)로 바꿔줘야함

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

    env = get_environment(controller)

    return env, controller


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
    Execute a given subtask in the Omnigibson environment using action primitives.

    Args:
        env: Omnigibson environment instance.
        agent: The agent executing the subtask.
        subtask: Subtask object containing execution details.
    """
    camera_handler = CameraHandler(controller)
    Navi = NavigationHandler(controller, camera_handler)
    Act = Action(controller, camera_handler, log_file)

    log_file.write(f"Executing Subtask: {subtask.name}")

    # Parse execution details
    execution = subtask.execution
    objects, primitive_actions = execution.objects, execution.primitive_actions

    # Build a mapping from object names to Omnigibson objects
    object_registry = {}

    # "NAVIGATE_TO laundry_hamper",
    # "GRASP clothes",
    # "NAVIGATE_TO washing_machine",
    # "PLACE_INSIDE washing_machine"
    for obj_name in objects:
        ai2thor_obj = list(
            set(
                obj["objectType"] for obj in controller.step("Pass").metadata["objects"]
            )
        )
        if ai2thor_obj is None:
            log_file.write(f"Object '{obj_name}' not found in the environment.")
            return False
        object_registry[obj_name] = ai2thor_obj

    # Define action mapping to Omnigibson action primitives
    action_mapping = {
        "NAVIGATE_TO": lambda target_obj: Navi.move_to(target_obj),
        "GRASP": lambda target_obj: Act.pickup(target_obj),
        "PLACE_INSIDE": lambda target_obj: Act.put(target_obj),
        "PLACE_ON_TOP": lambda target_obj: Act.put(target_obj),
        "OPEN": lambda target_obj: Act.open(target_obj),
        "CLOSE": lambda target_obj: Act.close(target_obj),
        "TOGGLE_ON": lambda target_obj: Act.toggleon(target_obj),
        "TOGGLE_OFF": lambda target_obj: Act.toggleoff(target_obj),
        # 필요한 경우 다른 액션을 추가할 수 있습니다.
    }

    # Execute each primitive action
    for action_str in primitive_actions:
        # Split action into type and target
        parts = action_str.split(" ", 1)
        if len(parts) != 2:
            log.warning(f"Invalid action format: {action_str}. Skipping.")
            raise ValueError(f"Invalid action format: {action_str}")

        action_type, target_name = parts
        target_obj = object_registry.get(target_name)

        if action_type in action_mapping:
            log.info(f"Performing action: {action_type} on {target_name}")

            # 실행된 제너레이터의 최종 결과를 success로 받음
            generator = action_mapping[action_type](target_obj)
            try:
                for result in generator:
                    pass
                success = True  # 제너레이터가 정상적으로 완료되면 성공
            except StopIteration:
                success = True
            except Exception as e:
                log.error(f"Error executing action '{action_type}': {e}")
                success = False
        else:
            log.warning(f"Unknown action type: {action_type}. Skipping.")

    log.info(f"Successfully executed Subtask: {subtask.name}")
    return success
