"""
ai2thor_simulation.py

This module provides:
1. A unified controller initialization function (`init_ai2thor_controller`)
   that can create an AI2-THOR Controller with default or overridden parameters.
2. A utility function (`execute_subtask`) to perform a given subtask with primitive actions.

Example usage:
    from ai2thor_simulation import init_ai2thor_controller, execute_subtask

    controller = init_ai2thor_controller()
    elapsed_time, success = execute_subtask(controller, subtask_obj)
"""

from ai2thor.controller import Controller

# Action handler import
from ithor.handlers.action import Action

# # Logging utility
# from src.utils.common.logger import create_module_logger

# Constants (unify your constants in one place)
from src.utils.config.constants import (
    GRID_SIZE,

    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from utils.common.logger import create_module_logger



def init_ai2thor_controller(
    scene: str = "FloorPlan1",
    platform=None,
    agent_mode: str = "default",
    mass_threshold: float = 0.04,
    grid_size: float = GRID_SIZE,
    movement_gaussian_sigma: float = 0.005,
    render_depth_image: bool = False,
    render_instance_segmentation: bool = False,
    width: int = SCREEN_WIDTH,
    height: int = SCREEN_HEIGHT,
    render_third_party_cameras: bool = False,
    field_of_view: int = 60,
) -> Controller:
    """
    Initializes and returns an AI2-THOR controller instance with default or user-defined settings.

    Args:
        scene (str, optional): Scene name to load. Defaults to FloorPlan1.
        platform (str, optional): Platform to use. Defaults to None.
        agent_mode (str, optional): Agent mode ("default", "locobot", "drone", or "arm"). Defaults to "default".
        mass_threshold (float, optional): Minimum mass required for objects to be moved. Defaults to 0.04.
        grid_size (float, optional): Movement grid size (mean for Move Actions). Defaults to GRID_SIZE.
        movement_gaussian_sigma (float, optional): Movement sigma for Move Actions. Defaults to 0.005.
        render_depth_image (bool, optional): Whether to render depth images. Defaults to False.
        render_instance_segmentation (bool, optional): Whether to render instance segmentation. Defaults to False.
        width (int, optional): Screen width. Defaults to SCREEN_WIDTH.
        height (int, optional): Screen height. Defaults to SCREEN_HEIGHT.
        render_third_party_cameras (bool, optional): Whether to render third-party cameras. Defaults to False.
        field_of_view (int, optional): Camera field of view. Defaults to 60.

    Returns:
        Controller: Configured AI2-THOR Controller.
    """
    controller = Controller(
        agentMode=agent_mode,
        massThreshold=mass_threshold,
        scene=scene,
        gridSize=grid_size,
        movementGaussianSigma=movement_gaussian_sigma,
        renderDepthImage=render_depth_image,
        renderInstanceSegmentation=render_instance_segmentation,
        width=width,
        height=height,
        renderThirdPartyCameras=render_third_party_cameras,
        fieldOfView=field_of_view,
        platform=platform,
    )

    return controller


def execute_subtask(controller: Controller, subtask, log_level) -> tuple[float, bool]:
    """
    Executes a given subtask using the provided AI2-THOR controller.

    Args:
        controller (Controller): An instance of the AI2-THOR Controller used to interact with the environment.
        subtask: A Subtask object containing execution details,
                 including the name, execution plan, and primitive actions.

    Returns:
        tuple[float, bool]:
            - float: The total elapsed time taken to execute the subtask.
            - bool: Whether the subtask succeeded (based on last action success).

    Raises:
        ValueError: If an invalid action format is encountered in the primitive actions.
    """
    log = create_module_logger(module_name=__name__, module_log=True, level=log_level)
    
    act = Action(controller)

    # If the subtask is just for initialization, skip
    if subtask.name == "Init":
        return 0.0, True

    log.info(f"Executing Subtask: {subtask.name}")

    # Parse execution details
    execution = subtask.execution
    primitive_actions = execution.primitive_actions
    objects = execution.objects

    # Optional debugging
    for action_str in primitive_actions:
        log.debug(f"Primitive action: {action_str}")

    # Object registry setup if needed
    object_registry = {}
    if objects is not None:
        # Force a step so controller metadata is fresh
        controller.step("Pass")
        all_obj_ids = {
            obj["objectId"] for obj in controller.last_event.metadata["objects"]
        }

        for obj_id in objects:
            if obj_id not in all_obj_ids:
                raise ValueError(f"Object '{obj_id}' not found in the environment.")
            object_registry[obj_id] = obj_id  # or store more info if needed

    # Define action mapping to AI2-THOR action primitives
    action_mapping = {
        "NAVIGATE_TO": lambda target_obj: act.move_to(target_obj),
        "GRASP": lambda target_obj: act.pickup(target_obj),
        "PLACE_INSIDE": lambda target_obj: act.put(target_obj),
        "PLACE_ON_TOP": lambda target_obj: act.put(target_obj),
        "OPEN": lambda target_obj: act.open(target_obj),
        "CLOSE": lambda target_obj: act.close(target_obj),
        "TOGGLE_ON": lambda target_obj: act.toggle_on(target_obj),
        "TOGGLE_OFF": lambda target_obj: act.toggle_off(target_obj),
        "SLICE": lambda target_obj: act.slice(target_obj),
        "MONITORING": lambda target_obj: act.monitoring(target_obj),
        "WAIT": lambda duration: act.wait(round(float(duration), 2)),
        "FILL": lambda target_obj: act.fill(target_obj),
    }

    elapsed_time = 0.0
    is_subtask_success = True

    # Execute each primitive action in sequence
    for action_str in primitive_actions:
        parts = action_str.split(" ", 1)
        if len(parts) != 2:
            log.warning(f"Invalid action format: {action_str}.")
            raise ValueError(f"Invalid action format: {action_str}")

        action_type, target_obj_id = parts
        if action_type in action_mapping:
            elapsed_time += action_mapping[action_type](target_obj_id)
        else:
            log.warning(f"Unknown action type: {action_type}. Skipping.")
            continue

        # Check success of the last action
        success = controller.last_event.metadata.get("lastActionSuccess", "N/A")
        if success is False:
            is_subtask_success = False

    log.info(
        f"Subtask '{subtask.name}' completed. Elapsed time: {round(elapsed_time, 2)}"
    )
    return elapsed_time, is_subtask_success
