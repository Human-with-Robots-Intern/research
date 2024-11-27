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

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

log = create_module_logger(module_name=__name__, is_file_handler=True)


def _load_config():
    # # Load the config
    config_filename = Path(og.example_config_path) / "fetch_primitives.yaml"
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    # Update it to run a grocery shopping task
    # config["scene"]["not_load_object_categories"] = [
    #     "ceilings",
    #     "pot_plant",
    #     "straight_chair",
    # ]
    # config["scene"]["load_room_types"] = ["living_room"]
    # config["scene"]["load_room_instances"] = ["living_room_0"]
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
    env.scene.object_registry("name", "apple")

    agent = BayesianAgent(env.robots[0])

    return env, agent


def execute_subtask(env, agent, subtask):
    """
    Execute a given subtask in the Omnigibson environment using action primitives.

    Args:
        env: Omnigibson environment instance.
        agent: The agent executing the subtask.
        subtask: Subtask object containing execution details.
    """
    log.info(f"Executing Subtask: {subtask.name}")

    controller = CustomActionPrimitives(env, agent)

    # Parse execution details
    execution = subtask.execution
    objects, primitive_actions = execution.objects, execution.primitive_actions

    # Build a mapping from object names to Omnigibson objects
    object_registry = {}
    for obj_name in objects:
        og_obj = env.scene.object_registry("name", obj_name)
        if og_obj is None:
            log.error(f"Object '{obj_name}' not found in the environment.")
            return False
        object_registry[obj_name] = og_obj

    # Define action mapping to Omnigibson action primitives
    action_mapping = {
        "NAVIGATE_TO": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.NAVIGATE_TO, target_obj
        ),
        "GRASP": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.GRASP, target_obj
        ),
        "PLACE_INSIDE": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.PLACE_INSIDE, target_obj
        ),
        "PLACE_ON_TOP": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.PLACE_ON_TOP, target_obj
        ),
        "OPEN": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.OPEN, target_obj
        ),
        "CLOSE": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.CLOSE, target_obj
        ),
        "TOGGLE_ON": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.TOGGLE_ON, target_obj
        ),
        "TOGGLE_OFF": lambda target_obj: controller.apply_ref(
            StarterSemanticActionPrimitiveSet.TOGGLE_OFF, target_obj
        ),
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
