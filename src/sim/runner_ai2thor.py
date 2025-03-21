import sys

from ai2thor.controller import Controller

from ithor.handlers.action import Action
from utils.constants import *
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, module_log=True)


def init_ai2thor(platform=None):
    """
    Initializes the AI2-THOR controller with specified parameters.

    Returns:
        Controller: An instance of the AI2-THOR Controller class.

    Parameters:
        agentMode (str): The mode of the agent. Options are "default", "locobot", "drone", or "arm".
        massThreshold (float): The minimum mass for objects to be moved by the physics engine.
        scene (str): The name of the scene to load.
        gridSize (float): The mean value for move actions.
        movementGaussianSigma (float): The sigma value for move actions.
        renderDepthImage (bool): Whether to render depth images (can be time-consuming).
        renderInstanceSegmentation (bool): Whether to render instance segmentation (can be time-consuming).
        width (int): The width of the screen.
        height (int): The height of the screen.
        renderThirdPartyCameras (bool): Whether to render third-party cameras.
        fieldOfView (int): The field of view for the camera.
    """
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
        platform=platform,
    )

    return controller


def execute_subtask(controller, subtask):
    """
    Executes a given subtask using the provided AI2-THOR controller.

        controller: An instance of the AI2-THOR controller used to interact with the environment.
        subtask: A Subtask object containing execution details, including the name, execution plan, and primitive actions.

    Args:
    subtask: Subtask object containing execution details.

    Returns:
        float: The total elapsed time taken to execute the subtask.

    Raises:
        ValueError: If an invalid action format is encountered in the primitive actions.

    The function performs the following steps:
    1. Initializes an Action object with the controller and log.
    2. Skips execution if the subtask name is "Init".
    3. Logs the subtask name and parses the execution details.
    4. Iterates over the primitive actions and prints each action.
    5. Registers objects in the environment if provided in the execution details.
    6. Maps action types to corresponding AI2-THOR action primitives.
    7. Executes each primitive action and calculates the total elapsed time.
    8. Logs the total elapsed time and successful execution of the subtask.
    """
    act = Action(controller)

    # Skip the Init subtask
    if subtask.name == "Init":
        return 0, None

    log.info(f"Executing Subtask: {subtask.name}")
    # Parse execution details
    execution = subtask.execution
    primitive_actions = execution.primitive_actions
    for action in primitive_actions:
        print(action)
    objects = execution.objects

    object_registry = {}

    if objects is not None:
        for obj_id in objects:
            ai2thor_obj = list(
                set(
                    obj["objectId"]
                    for obj in controller.step("Pass").metadata["objects"]
                )
            )
            if ai2thor_obj is None:
                raise (ValueError(f"Object {obj_id} not found in the environment."))
            object_registry[obj_id] = ai2thor_obj

    # Define action mapping to ai2thor action primitives
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

    # Execute each primitive action
    elapsed_time = 0
    is_subtask_success = True
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
            # TODO: log if the last primiive action was successful
        # e.g.,
        # wirte code here
        success = controller.last_event.metadata.get("lastActionSuccess", "N/A")
        log.info(f"Action success: {action_str}: {success}")
        if success == False:
            is_subtask_success = False
        ####

    log.info(f"{subtask.name}의 걸린시간 = {round(elapsed_time, 2)}")
    log.info(f"Successfully executed Subtask: {subtask.name}")
    return elapsed_time, is_subtask_success
