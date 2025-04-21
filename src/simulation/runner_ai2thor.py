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

import logging
import time  # 시간 측정을 위해 추가 (선택적)

from ai2thor.controller import Controller

# Action handler import
from ithor.handlers.action import Action

# Logging utility
from src.utils.common.logger import create_module_logger

# Constants (unify your constants in one place)
from src.utils.config.constants import (
    GRID_SIZE,
    SCENE_NAME,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)

log = logging.getLogger(__name__)


def init_ai2thor_controller(
    scene: str = SCENE_NAME,
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
        scene (str, optional): Scene name to load. Defaults to SCENE_NAME.
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


def execute_subtask(controller: Controller, subtask) -> tuple[float, bool]:
    """
    Executes a given subtask using the AI2-THOR controller, with enhanced error handling.

    Args:
        controller (Controller): AI2-THOR Controller instance.
        subtask: Subtask object with execution details.

    Returns:
        tuple[float, bool]:
            - float: Estimated elapsed time based on simulated action durations.
                     Accuracy depends on ithor.handlers.action implementation.
            - bool: Whether the subtask succeeded overall. False if any action fails
                    or critical errors occur.

    Raises:
        ValueError: If subtask references an object not found in the environment initially.
                    (Other ValueErrors from action parsing might be caught internally).
    """
    # Check if subtask is valid
    if not hasattr(subtask, "name") or not hasattr(subtask, "execution"):
        log.error("Invalid subtask object provided to execute_subtask.")
        return 0.0, False  # Return failure for invalid input

    # Skip Init subtask
    if subtask.name == "Init":
        log.info("Skipping Init subtask execution.")
        return 0.0, True

    # Ensure execution details exist
    if not subtask.execution or not hasattr(subtask.execution, "primitive_actions"):
        log.error(
            f"Subtask '{subtask.name}' has missing execution details or primitive_actions."
        )
        return 0.0, False

    # Initialize Action handler (potentially raises errors if controller is invalid)
    try:
        act = Action(controller)
    except Exception as e:
        log.error(
            f"Failed to initialize ithor.handlers.action.Action: {e}", exc_info=True
        )
        return 0.0, False

    log.info(f"Executing Subtask: {subtask.name}")

    primitive_actions = subtask.execution.primitive_actions
    objects = subtask.execution.objects

    # --- Initial Object Check (Optional but recommended) ---
    # Perform a step to ensure metadata is current before checking objects
    try:
        controller.step("Pass")  # Minimal action to refresh metadata
        current_metadata = getattr(controller.last_event, "metadata", None)
        if not current_metadata or "objects" not in current_metadata:
            log.error("Failed to get valid metadata from controller after 'Pass' step.")
            return 0.0, False  # Cannot verify objects

        all_obj_ids_in_scene = {
            obj.get("objectId")
            for obj in current_metadata["objects"]
            if obj.get("objectId")
        }

        if objects:  # If the subtask specifies required objects
            for obj_id in objects:
                if obj_id not in all_obj_ids_in_scene:
                    # Raise error if required object isn't present at the start
                    log.error(
                        f"Required object '{obj_id}' for subtask '{subtask.name}' not found in the environment."
                    )
                    raise ValueError(
                        f"Object '{obj_id}' not found in the environment for subtask '{subtask.name}'."
                    )
                # Optional: Store object info if needed later
                # object_registry[obj_id] = ...

    except Exception as e:
        log.error(
            f"Error during initial environment check for subtask '{subtask.name}': {e}",
            exc_info=True,
        )
        return 0.0, False  # Fail if initial check encounters issues

    # --- Action Execution Loop ---
    # Mapping remains the same
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
        "MONITORING": lambda target_obj: act.monitoring(
            target_obj
        ),  # Assumes this exists and returns duration
        "WAIT": lambda duration: act.wait(
            round(float(duration), 2)
        ),  # Assumes this exists and returns duration
        "FILL": lambda target_obj: act.fill(
            target_obj
        ),  # Assumes this exists and returns duration
    }

    elapsed_time = 0.0
    is_subtask_success = True  # Assume success initially
    start_real_time = time.time()  # For real-world timing (optional)

    # --- 주석 추가: 외부 핸들러 의존성 ---
    # NOTE: The accuracy of 'elapsed_time' and 'is_subtask_success' depends heavily
    # on the implementation of the 'ithor.handlers.action.Action' handler ('act').
    # The handler MUST return accurate simulated time costs and determine success
    # based on `controller.last_event.metadata`. Any discrepancy will lead to
    # incorrect scheduling and state representation.
    # Specifically:
    # 1. The duration returned by handler methods (e.g., act.move_to) MUST accurately
    #    reflect the simulated time cost. If it returns fixed values or simple estimates,
    #    'elapsed_time' will not match reality.
    # 2. Action success MUST be correctly determined, typically by checking
    #    controller.last_event.metadata['lastActionSuccess'] after the handler call.
    # 3. Assumed methods like act.monitoring, act.wait, act.fill MUST exist and
    #    function as expected within the handler.
    # -----------------------------------------

    for action_index, action_str in enumerate(primitive_actions):
        action_duration = 0.0  # Duration for this specific action
        action_success = False  # Success status for this specific action

        try:
            parts = action_str.split(" ", 1)
            if len(parts) < 1:  # Should have at least the action type
                log.warning(
                    f"Invalid action format (empty): '{action_str}' in subtask '{subtask.name}'. Skipping."
                )
                is_subtask_success = False
                continue  # Skip to next action

            action_type = parts[0].upper()
            # Target is the rest of the string, or None if only action type is present
            target = parts[1] if len(parts) == 2 else None

            if action_type in action_mapping:
                log.debug(
                    f"Executing action {action_index+1}/{len(primitive_actions)}: '{action_str}'"
                )
                # --- Execute Action via Handler ---
                returned_duration = action_mapping[action_type](target)

                # --- Process Result (Check duration and metadata) ---
                if (
                    isinstance(returned_duration, (int, float))
                    and returned_duration >= 0
                ):
                    action_duration = returned_duration
                else:
                    log.warning(
                        f"Action '{action_str}' returned invalid duration '{returned_duration}'. Assuming 0 duration."
                    )
                    action_duration = 0.0

                last_event = getattr(controller, "last_event", None)
                if last_event:
                    action_success = last_event.metadata.get("lastActionSuccess", False)
                    if not action_success:
                        error_message = last_event.metadata.get(
                            "errorMessage", "No error message provided."
                        )
                        log.warning(
                            f"Action '{action_str}' (Index: {action_index}) FAILED in subtask '{subtask.name}'. Reason: {error_message}"
                        )
                    else:
                        log.debug(f"Action '{action_str}' succeeded.")
                else:
                    log.error(
                        f"Failed to get valid metadata after action '{action_str}'. Assuming failure."
                    )
                    action_success = False  # Assume failure if metadata is missing

            else:
                log.warning(
                    f"Unknown action type: '{action_type}' in action '{action_str}'. Skipping."
                )
                action_success = False  # Treat unknown action as failure

        except (
            ValueError
        ) as ve:  # Catch specific errors like invalid format, missing object (if raised by handler)
            log.error(f"ValueError during action '{action_str}': {ve}", exc_info=True)
            action_success = False
        except (
            Exception
        ) as e:  # Catch unexpected errors during action execution or result processing
            log.error(
                f"Unexpected error during action '{action_str}': {e}", exc_info=True
            )
            action_success = False  # Treat unexpected errors as failure

        # Accumulate time based on the *returned* duration from the handler
        elapsed_time += action_duration

        # If any action fails, the whole subtask is marked as failed
        if not action_success:
            is_subtask_success = False
            # NOTE: No environment state rollback is implemented upon action failure.
            # The environment might be left in an inconsistent state after a failed subtask.
            # Optional: Decide whether to break the loop on first failure
            log.error(
                f"Subtask '{subtask.name}' failed due to action '{action_str}'. Stopping execution of remaining actions."
            )
            break  # Stop executing further actions in this subtask upon failure

    end_real_time = time.time()
    real_duration = end_real_time - start_real_time
    log.info(
        f"Subtask '{subtask.name}' finished. Overall Success: {is_subtask_success}. "
        f"Estimated Simulated Time (from handler): {round(elapsed_time, 2)}s. "
        f"Actual Wall Clock Time: {round(real_duration, 2)}s."
    )

    # Return the accumulated time from the handler and the overall success status
    return elapsed_time, is_subtask_success
