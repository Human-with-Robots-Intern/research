import logging
import time

from src.utils.common import create_module_logger
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PLACE_ACTION_DURATION,
    SMOOTH_LEVEL,
    TOGGLE_ACTION_DURATION,
)

from .navigation_handler import NavigationHandler

log = create_module_logger(module_name=__name__, module_log=True, level="DEBUG")

ACTION_TIME_SLEEP = 0.01
MOVE_BACKWARD_DISTANCE = 1


class Action:
    """
    Possible actions:
        - pickup, slice, put, drop, toggleon, toggleoff, open, close,
          monitoring, wait, fill, move to

    Args:
        controller: The AI2-THOR controller used to interact with the environment.
        logger (logging.Logger): The logger instance to use.

    Returns (for all actions):
        elapsed_time (float): Time taken to perform the action.
    """

    def __init__(self, controller, logger: logging.Logger):
        self.controller = controller
        self.navi = NavigationHandler(controller)
        self.log = logger

    def success_log(self, result, action: str):
        """
        Log the result of an action.

        Args:
            result: The result from controller.step(action).
            action (str): The action description for logging.
        """
        if result.metadata["lastActionSuccess"]:
            self.log.debug(f"{action}: success")
        else:
            self.log.debug(
                f"{action}: failure. {result.metadata.get('errorMessage', 'Unknown error')}"
            )

    def get_parent_receptacle(self, object_id: str):
        """
        Retrieve the parent receptacle of the specified object.

        Args:
            object_id (str): The object identifier.

        Returns:
            The parent receptacle identifier, or None if not found.
        """
        object_metadata = self.controller.last_event.metadata.get("objects", [])
        for obj in object_metadata:
            if obj.get("objectId") == object_id:
                # parentReceptacles 키가 없을 수도 있으므로 get으로 가져오기
                parent_receptacle_ids = obj.get("parentReceptacles")
                if parent_receptacle_ids:
                    self.log.debug(f"Found parent receptacles: {parent_receptacle_ids}")
                    return parent_receptacle_ids[0]
        return None

    def pickup(self, object_id: str):
        """
        Attempt to pick up the specified object.

        Steps:
            1. Attempt to pick up the object.
            2. If pickup fails, retrieve the parent receptacle, check if it's openable,
               and open it, then try picking up again and finally close the receptacle.

        Args:
            object_id (str): The identifier of the object to pick up.

        Returns:
            float: Elapsed time for the pickup action, or False on failure.
        """
        elapsed_time = GRASP_ACTION_DURATION

        # 1. 첫 번째 시도
        result = self.controller.step(
            action="PickupObject",
            objectId=object_id,
            forceAction=False,
            manualInteract=False,
        )

        if result.metadata["lastActionSuccess"]:
            self.success_log(result, f"pickup {object_id} (initial attempt)")
            time.sleep(ACTION_TIME_SLEEP)
            return elapsed_time

        # 2. 첫 시도 실패 시, 부모 컨테이너 확인 및 열기 후 재시도
        self.log.warning(
            f"Initial pickup failed for {object_id}. Checking for a receptacle."
        )
        receptacle_id = self.get_parent_receptacle(object_id)

        if receptacle_id:
            receptacle_obj = next(
                (
                    obj
                    for obj in self.controller.last_event.metadata["objects"]
                    if obj["objectId"] == receptacle_id
                ),
                None,
            )

            # 부모가 '열 수 있는' 객체일 경우에만 진행
            if receptacle_obj and receptacle_obj.get("openable"):
                self.log.debug(
                    f"Parent {receptacle_id} is openable. Opening it to retry pickup."
                )
                self.open(receptacle_id)
                time.sleep(ACTION_TIME_SLEEP)

                # 열고 나서 forceAction으로 재시도
                result = self.controller.step(
                    action="PickupObject",
                    objectId=object_id,
                    forceAction=True,
                    manualInteract=False,
                )
                self.controller.step(action="Pass")

                if result.metadata["lastActionSuccess"]:
                    self.success_log(
                        result, f"pickup {object_id} (after opening {receptacle_id})"
                    )
                    self.close(receptacle_id)
                    self.log.debug(
                        f"Pick up action after opening receptacle {receptacle_id} was successful."
                    )
                    time.sleep(ACTION_TIME_SLEEP)
                    return elapsed_time
                else:
                    self.log.error(
                        f"Pickup of {object_id} failed even after opening parent {receptacle_id}."
                    )
                    return False
            else:
                self.log.debug(
                    f"Parent receptacle {receptacle_id} is not openable. Skipping open action."
                )

        # 3. 부모가 없거나, 열 수 없는 객체이거나, 다른 이유로 실패 시 최종 재시도
        self.log.warning(
            f"Falling back to a final force pickup attempt for {object_id}."
        )
        result = self.controller.step(
            action="PickupObject",
            objectId=object_id,
            forceAction=True,
            manualInteract=False,
        )

        if result.metadata["lastActionSuccess"]:
            self.success_log(result, f"pickup {object_id} (final force attempt)")
            time.sleep(ACTION_TIME_SLEEP)
            return elapsed_time

        self.log.error(f"All pickup attempts for {object_id} have failed.")
        return False

    def slice(self, object_id: str):
        """
        Slice the specified object.

        Args:
            object_id (str): The identifier of the object to slice.

        Returns:
            float: Elapsed time for the slice action.
        """
        result = self.controller.step(action="SliceObject", objectId=object_id)
        self.success_log(result, f"slice {object_id}")
        time.sleep(ACTION_TIME_SLEEP)
        return TOGGLE_ACTION_DURATION

    def put(self, target_id: str):
        """
        Put the held object into the target container.
        If the initial attempt fails, it tries various recovery strategies
        before finally dropping the object as a last resort.

        Args:
            target_id (str): The identifier of the target container.

        Returns:
            float: Elapsed time for the put action.
        """
        elapsed_time = PLACE_ACTION_DURATION
        result = self.controller.step(
            action="PutObject",
            objectId=target_id,
            forceAction=False,
            placeStationary=True,
        )
        self.success_log(result, f"put {target_id}")

        if not result.metadata["lastActionSuccess"]:
            self.log.warning(
                f"Initial 'PutObject' on {target_id} failed. Attempting recovery with Teleport."
            )
            reachable_positions_event = self.controller.step(
                action="GetReachablePositions"
            )
            if reachable_positions_event.metadata["lastActionSuccess"]:
                positions = reachable_positions_event.metadata["actionReturn"]
                if positions:
                    best_pos = positions[0]
                    agent_meta = self.controller.last_event.metadata["agent"]
                    self.controller.step(
                        action="Teleport",
                        position=best_pos,
                        rotation=agent_meta["rotation"],
                        horizon=agent_meta["cameraHorizon"],
                        standing=True,
                    )
                    self.log.info(
                        f"Teleported to a reachable position {best_pos} for retrying 'PutObject'."
                    )
                    result = self.controller.step(
                        action="PutObject",
                        objectId=target_id,
                        forceAction=True,
                        placeStationary=True,
                    )
                    self.success_log(result, f"Retry put {target_id} after Teleport")

        if not result.metadata["lastActionSuccess"]:
            error_message = result.metadata.get("errorMessage", "")
            if "CLOSED" in error_message.upper():
                self.log.warning(
                    f"Put failed because '{target_id}' is closed. Forcing it open and retrying."
                )
                self.open(target_id)
                target_obj_state = next(
                    (
                        obj
                        for obj in self.controller.last_event.metadata["objects"]
                        if obj["objectId"] == target_id
                    ),
                    None,
                )
                if target_obj_state and target_obj_state.get("isOpen"):
                    self.log.debug(
                        f"Successfully opened '{target_id}'. Final retry for PutObject."
                    )
                    result = self.controller.step(
                        action="PutObject",
                        objectId=target_id,
                        forceAction=True,
                        placeStationary=True,
                    )
                    self.success_log(
                        result, f"Final retry put {target_id} after force open"
                    )
                else:
                    self.log.error(
                        f"Could not open '{target_id}' even with force. Cannot place object inside."
                    )

        if not result.metadata["lastActionSuccess"]:
            self.log.error(
                f"'PutObject' on {target_id} failed through all recovery attempts. Dropping object as last resort."
            )
            result = self.controller.step(action="DropHandObject", forceAction=True)
            self.success_log(result, "drop")
            self.log.debug("Alternative Action: Drop")

        time.sleep(ACTION_TIME_SLEEP)
        return elapsed_time

    def drop(self):
        """
        Drop the held object.

        Returns:
            float: Elapsed time for the drop action.
        """
        result = self.controller.step(action="DropHandObject", forceAction=False)
        step = 0
        # 여러 번 시도해도 실패할 경우 탈출
        while not result.metadata["lastActionSuccess"] and step < 10:
            self.controller.step(
                action="MoveHeldObjectAhead", moveMagnitude=0.1, forceVisible=False
            )
            result = self.controller.step(action="DropHandObject", forceAction=False)
            step += 1
        self.success_log(result, "drop")
        time.sleep(ACTION_TIME_SLEEP)
        return TOGGLE_ACTION_DURATION

    def toggle_on(self, object_id: str):
        """
        Toggle the specified object on. Checks if the object is already on
        to prevent unnecessary actions and errors.

        Args:
            object_id (str): The identifier of the object to toggle on.

        Returns:
            float: Elapsed time for the toggle on action.
        """
        for obj in self.controller.last_event.metadata["objects"]:
            if obj["objectId"] == object_id:
                if obj["isToggled"]:
                    self.log.info(
                        f"Object {object_id} is already on. Skipping toggle on action."
                    )
                    return TOGGLE_ACTION_DURATION
                break

        result = self.controller.step(action="ToggleObjectOn", objectId=object_id)
        self.success_log(result, f"toggle on {object_id}")
        time.sleep(ACTION_TIME_SLEEP)
        return TOGGLE_ACTION_DURATION

    def toggle_off(self, object_id: str):
        """
        Toggle the specified object off. Checks if the object is already off
        to prevent unnecessary actions and errors.

        Args:
            object_id (str): The identifier of the object to toggle off.

        Returns:
            float: Elapsed time for the toggle off action.
        """
        for obj in self.controller.last_event.metadata["objects"]:
            if obj["objectId"] == object_id:
                if not obj["isToggled"]:
                    self.log.info(
                        f"Object {object_id} is already off. Skipping toggle off action."
                    )
                    return TOGGLE_ACTION_DURATION
                break

        result = self.controller.step(action="ToggleObjectOff", objectId=object_id)
        self.success_log(result, f"toggle off {object_id}")
        time.sleep(ACTION_TIME_SLEEP)
        return TOGGLE_ACTION_DURATION

    def open(self, object_id: str):
        """
        Open the specified object (e.g., a container).
        If the initial attempt fails, it tries to teleport to a reachable
        position and retries the action. As a final resort, it forces
        the object's state to be open.

        Args:
            object_id (str): The identifier of the object to open.

        Returns:
            float: Elapsed time for the open action.
        """
        elapsed_time = TOGGLE_ACTION_DURATION
        # Face the target and make a small backward offset to avoid door collision
        agent_pos = self.navi.get_agent_position()
        object_pos = self.navi.get_object_position(object_id)
        if object_pos is not None:
            obj_angle, degree = self.navi.agent_rotate_angle(agent_pos, object_pos)
            if degree != 0:
                for _ in range(SMOOTH_LEVEL):
                    step_deg = abs(degree) / SMOOTH_LEVEL
                    if degree > 0:
                        self.controller.step(action="RotateRight", degrees=step_deg)
                    else:
                        self.controller.step(action="RotateLeft", degrees=step_deg)
                    self.controller.step(action="Pass")
            # Back off slightly away from the door plane
            try:
                self.navi.move_in_direction(-obj_angle, MOVE_BACKWARD_DISTANCE)
            except Exception:
                # non-fatal, continue
                pass
        result = self.controller.step(
            action="OpenObject",
            objectId=object_id,
            openness=1,
            forceAction=False,
        )
        self.success_log(result, f"open {object_id}")

        # If door failed to stay open due to collision, back off and try once more with force
        try:
            obj_state = next(
                (
                    o
                    for o in self.controller.last_event.metadata["objects"]
                    if o["objectId"] == object_id
                ),
                None,
            )
            is_open_now = bool(obj_state and obj_state.get("isOpen"))
        except Exception:
            is_open_now = result.metadata.get("lastActionSuccess", False)

        if not result.metadata["lastActionSuccess"] or not is_open_now:
            self.log.warning(
                f"Initial 'OpenObject' on {object_id} failed. Attempting recovery with Teleport."
            )
            reachable_positions_event = self.controller.step(
                action="GetReachablePositions"
            )
            if reachable_positions_event.metadata["lastActionSuccess"]:
                positions = reachable_positions_event.metadata["actionReturn"]
                if positions:
                    best_pos = positions[0]
                    agent_meta = self.controller.last_event.metadata["agent"]
                    self.controller.step(
                        action="Teleport",
                        position=best_pos,
                        rotation=agent_meta["rotation"],
                        horizon=agent_meta["cameraHorizon"],
                        standing=True,
                    )
                    self.log.info(
                        f"Teleported to a reachable position {best_pos} for retrying 'OpenObject'."
                    )
                    # Additional small backoff after teleport to reduce collision chance
                    try:
                        agent_pos = self.navi.get_agent_position()
                        object_pos = self.navi.get_object_position(object_id)
                        if object_pos is not None:
                            obj_angle, _ = self.navi.agent_rotate_angle(
                                agent_pos, object_pos
                            )
                            self.navi.move_in_direction(
                                -obj_angle, MOVE_BACKWARD_DISTANCE
                            )
                    except Exception:
                        pass
                    result = self.controller.step(
                        action="OpenObject",
                        objectId=object_id,
                        openness=1,
                        forceAction=True,
                    )
                    self.success_log(result, f"Retry open {object_id} after Teleport")

        if not result.metadata["lastActionSuccess"]:
            self.log.warning(
                f"'OpenObject' on {object_id} failed again. Brute-forcing with forceAction."
            )
            result = self.controller.step(
                action="OpenObject",
                objectId=object_id,
                openness=1,
                forceAction=True,
            )
            self.success_log(result, f"Force open {object_id} via forceAction")

        time.sleep(ACTION_TIME_SLEEP)
        return elapsed_time

    def close(self, object_id: str):
        """
        Close the specified object.
        Includes a fallback mechanism to force the state if the action fails.

        Args:
            object_id (str): The identifier of the object to close.

        Returns:
            float: Elapsed time for the close action.
        """
        result = self.controller.step(
            action="CloseObject",
            objectId=object_id,
            forceAction=False,
        )
        self.success_log(result, f"close {object_id}")

        if not result.metadata["lastActionSuccess"]:
            self.log.warning(
                f"'CloseObject' on {object_id} failed. Brute-forcing with forceAction."
            )
            result = self.controller.step(
                action="CloseObject",
                objectId=object_id,
                forceAction=True,
            )
            self.success_log(result, f"Force close {object_id} via forceAction")

        time.sleep(ACTION_TIME_SLEEP)
        return TOGGLE_ACTION_DURATION

    def monitoring(self, object_id: str):
        """
        Monitor a specified object by rotating the agent to face it,
        adjusting the camera, and then rotating back.

        Args:
            object_id (str): The ID of the object to monitor.

        Returns:
            float: Elapsed time for the monitoring action.
        """
        agent_position = self.navi.get_agent_position()
        object_position = self.navi.get_object_position(object_id)
        self.log.debug(f"Monitoring: focusing on {object_id}")

        obj_angle, degree = self.navi.agent_rotate_angle(
            agent_position, object_position
        )
        result = None

        if degree != 0:
            # 부드럽게 회전 (방향성 보장)
            for _ in range(SMOOTH_LEVEL):
                step_deg = abs(degree) / SMOOTH_LEVEL
                if degree > 0:
                    result = self.controller.step(
                        action="RotateRight", degrees=step_deg
                    )
                else:
                    result = self.controller.step(action="RotateLeft", degrees=step_deg)
                if not result.metadata["lastActionSuccess"]:
                    # 회전 실패 시 약간 이동 후 재시도 (문짝 등 충돌 완화)
                    self.navi.move_in_direction(-obj_angle, 0.2)
                    if degree > 0:
                        result = self.controller.step(
                            action="RotateRight", degrees=step_deg
                        )
                    else:
                        result = self.controller.step(
                            action="RotateLeft", degrees=step_deg
                        )
                self.controller.step(action="Pass")

        # 카메라 각도 조정
        self.navi.adjust_camera_to_object(object_id)
        self.success_log(result, f"adjust camera to {object_id} for monitoring action")
        time.sleep(MONITORING_DURATION)

        # 원위치로 회전
        if degree != 0:
            for _ in range(SMOOTH_LEVEL):
                step_deg = abs(degree) / SMOOTH_LEVEL
                # 되돌릴 때는 반대 방향으로 회전
                if degree > 0:
                    self.controller.step(action="RotateLeft", degrees=step_deg)
                else:
                    self.controller.step(action="RotateRight", degrees=step_deg)

        time.sleep(MONITORING_DURATION)
        return MONITORING_DURATION

    def wait(self, wait_time: float):
        """
        Wait for the specified duration.
        Args:
            wait_time (float, optional): Duration in seconds. Defaults to 1.
        Returns:
            float: Elapsed time for the wait action.
        """
        time.sleep(ACTION_TIME_SLEEP)
        self.log.debug(f"wait: {wait_time}")
        return wait_time

    def fill(self, object_id: str):
        """
        Fill the specified object with water.

        Args:
            object_id (str): The identifier of the object to fill.

        Returns:
            float: Elapsed time for the fill action.
        """
        result = self.controller.step(
            action="FillObjectWithLiquid",
            objectId=object_id,
            fillLiquid="water",
            forceAction=True,
        )
        self.success_log(result, f"fill {object_id} with water")
        time.sleep(ACTION_TIME_SLEEP)
        return PLACE_ACTION_DURATION

    def move_to(self, object_id: str):
        """
        Move the agent to the nearest reachable point near the specified object.

        Args:
            object_id (str): The identifier of the target object.
                           (Optionally can include a stop_time after a space,
                           e.g., 'Tomato 2.0' -> objectId='Tomato', stop_time=2.0)

        Returns:
            float: Elapsed time for the move action.
        """
        # stop_time 파라미터가 포함되어 있으면 분리
        stop_time = None
        if " " in object_id:
            splits = object_id.split(" ", 1)
            object_id, stop_time_str = splits[0], splits[1]
            try:
                stop_time = float(stop_time_str)
            except ValueError:
                stop_time = None

        agent_position = self.navi.get_agent_position()
        object_position = self.navi.get_object_position(object_id)
        if object_position is None:
            self.log.error(
                f"목표 오브젝트 '{object_id}'를 찾을 수 없어 이동에 실패했습니다."
            )
            return 0

        path = self.navi.find_shortest_path(agent_position, object_position)

        if path:
            # 첫 좌표는 현재 위치이므로 제거
            path.pop(0)

        elapsed_time = 0
        for position in path:
            # 이동 하나 당 0.1초 정도 소요된다고 가정
            elapsed_time += NAV_STEP_DURATION
            self.navi.teleport_to_position(position)

            # stop_time이 설정되어 있고, elapsed_time이 일정값에 도달하면 중단
            if stop_time is not None and elapsed_time >= stop_time:
                break

        # 목표 지점에 도달한 뒤 오브젝트 쪽으로 에이전트 회전
        agent_position = self.navi.get_agent_position()
        # object_position이 회전 전에 다시 필요하므로, None 체크를 위에서 수행한 것을 재활용
        obj_angle, degree = self.navi.agent_rotate_angle(
            agent_position, object_position
        )

        # stop_time이 없을 때에만 최종 회전 진행
        if degree != 0 and stop_time is None:
            for _ in range(SMOOTH_LEVEL):
                result = self.controller.step(
                    action="RotateRight", degrees=degree / SMOOTH_LEVEL
                )
                success = self.controller.last_event.metadata["lastActionSuccess"]
                if not success:
                    error_message = result.metadata.get(
                        "errorMessage", "No error message."
                    )
                    self.log.warning(
                        f"NAV_DEBUG: Final rotation to {object_id} failed. Error: {error_message}"
                        f"NAV_DEBUG: Final rotation to {object_id} failed. Error: {error_message}"
                    )
                    # 회전 실패 시 각도대로 살짝 이동 후 재시도
                    self.navi.move_in_direction(-obj_angle, 0.2)
                    recovery_result = self.controller.step(
                        action="RotateRight", degrees=degree / SMOOTH_LEVEL
                    )
                    if not recovery_result.metadata["lastActionSuccess"]:
                        _ = recovery_result.metadata.get(
                            "errorMessage", "No error message."
                        )
                        # self.log.error(f"NAV_DEBUG: Rotation recovery also failed.")

        # 카메라 각도 조정
        self.navi.adjust_camera_to_object(object_id)
        self.log.debug(f"move to {object_id}")
        self.log.debug(f"move to {object_id} elapsed_time in action.py: {elapsed_time}")
        time.sleep(ACTION_TIME_SLEEP)
        self.controller.step(action="Pass")
        return elapsed_time
