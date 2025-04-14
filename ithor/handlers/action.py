import time

from src.utils.config.constants import SMOOTH_LEVEL
from src.utils.common import create_module_logger

from .navigation_handler import NavigationHandler

log = create_module_logger(module_name=__name__, module_log=True)


class Action:
    """
    Possible actions:
        - pickup, slice, put, drop, toggleon, toggleoff, open, close,
          monitoring, wait, fill, move to

    Args:
        controller: The AI2-THOR controller used to interact with the environment.
        log (logging.Logger): Logger object for recording action execution details.

    Returns (for all actions):
        elapsed_time (float): Time taken to perform the action.
    """

    def __init__(self, controller):
        self.controller = controller
        self.navi = NavigationHandler(controller)

    def success_log(self, result, action: str):
        """
        Log the result of an action.

        Args:
            result: The result from controller.step(action).
            action (str): The action description for logging.
        """
        if result.metadata["lastActionSuccess"]:
            log.debug(f"{action}: success")
        else:
            log.debug(
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
                    log.debug(f"Found parent receptacles: {parent_receptacle_ids}")
                    return parent_receptacle_ids[0]
        return None

    def pickup(self, object_id: str):
        """
        Attempt to pick up the specified object.

        Steps:
            1. Attempt to pick up the object.
            2. If pickup fails, retrieve the parent receptacle and open it,
               then try picking up again and finally close the receptacle.

        Args:
            object_id (str): The identifier of the object to pick up.

        Returns:
            float: Elapsed time for the pickup action, or False on failure.
        """
        elapsed_time = 0
        result = self.controller.step(
            action="PickupObject",
            objectId=object_id,
            forceAction=False,
            manualInteract=False,
        )

        if result.metadata["lastActionSuccess"]:
            self.success_log(result, f"pickup {object_id}")
            self.controller.step(action="Pass")
            time.sleep(0.3)
            elapsed_time += 1
            return elapsed_time

        # 만약 첫 시도에 실패한 경우
        receptacle_id = self.get_parent_receptacle(object_id)
        if receptacle_id:
            elapsed_time += self.move_to(receptacle_id)
            self.open(receptacle_id)
            elapsed_time += 1
            time.sleep(0.5)
            result = self.controller.step(
                action="PickupObject",
                objectId=object_id,
                forceAction=True,
                manualInteract=False,
            )
            if result.metadata["lastActionSuccess"]:
                self.close(receptacle_id)
                elapsed_time += 1
                log.debug(
                    f"Pick up action after opening receptacle "
                    f"{receptacle_id} was successful."
                )
                return elapsed_time
            else:
                log.warning(
                    f"Failed to pick up object {object_id} even after "
                    f"opening the receptacle {receptacle_id}."
                )
                elapsed_time += 1
                return elapsed_time
        else:
            # Re-try once more (또 한 번 시도)
            result = self.controller.step(
                action="PickupObject",
                objectId=object_id,
                forceAction=False,
                manualInteract=False,
            )
            self.success_log(result, f"pickup {object_id}")
            self.controller.step(action="Pass")
            time.sleep(0.3)
            elapsed_time += 1
            return elapsed_time

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
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

    def put(self, target_id: str):
        """
        Put the held object into the target container.

        Steps:
            1. Attempt to put the object.
            2. If unsuccessful, move back and try again.
            3. If still unsuccessful, drop the object.

        Args:
            target_id (str): The identifier of the target container.

        Returns:
            float: Elapsed time for the put action.
        """
        elapsed_time = 1
        result = self.controller.step(
            action="PutObject",
            objectId=target_id,
            forceAction=False,
            placeStationary=True,
        )
        self.success_log(result, f"put {target_id}")

        if not result.metadata["lastActionSuccess"]:
            self.controller.step(action="MoveBack")
            result = self.controller.step(
                action="PutObject",
                objectId=target_id,
                forceAction=False,
                placeStationary=True,
            )
            self.success_log(result, f"MoveBack and put {target_id}")

        if not self.controller.last_event.metadata["lastActionSuccess"]:
            self.controller.step(action="MoveAhead")
            result = self.controller.step(action="DropHandObject", forceAction=True)
            elapsed_time += 1
            self.success_log(result, "drop")
            log.debug("Alternative Action: Drop")
        self.controller.step(action="Pass")
        time.sleep(0.3)
        elapsed_time += 1
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
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

    def toggle_on(self, object_id: str):
        """
        Toggle the specified object on.

        Args:
            object_id (str): The identifier of the object.

        Returns:
            float: Elapsed time for the toggle on action.
        """
        result = self.controller.step(action="ToggleObjectOn", objectId=object_id)
        self.success_log(result, f"toggle on {object_id}")
########## modified to simulate water        
        # If the object is a faucet and there's a pot under it, wait before filling
        if "Faucet" in object_id:
            # Find the pot under the faucet
            for obj in self.controller.last_event.metadata["objects"]:
                if "Pot" in obj["objectId"] and obj["isFilledWithLiquid"] is False:
                    # Wait for 5 seconds before filling the pot
                    # time.sleep(5.0)
                    # # Set the pot's isFilled property to true
                    # self.controller.step(action="SetObjectState", 
                    #                   objectId=obj["objectId"],
                    #                   state="isFilledWithLiquid",
                    #                   value=True)
                    # break
                    pass
##########################      
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

    def toggle_off(self, object_id: str):
        """
        Toggle the specified object off.

        Args:
            object_id (str): The identifier of the object.

        Returns:
            float: Elapsed time for the toggle off action.
        """
        result = self.controller.step(action="ToggleObjectOff", objectId=object_id)
        self.success_log(result, f"toggle off {object_id}")
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

    def open(self, object_id: str):
        """
        Open the specified object (e.g., a container).

        Args:
            object_id (str): The identifier of the object to open.

        Returns:
            float: Elapsed time for the open action.
        """
        elapsed_time = 0
        # 너무 가까우면 열기 실패할 수 있으므로 살짝 뒤로 이동
        for _ in range(2):
            self.controller.step(action="MoveBack")
            self.controller.step(action="Pass")
        time.sleep(0.1)

        result = self.controller.step(
            action="OpenObject",
            objectId=object_id,
            openness=1,
            forceAction=False,
        )
        self.success_log(result, f"open {object_id}")
        self.controller.step(action="Pass")
        time.sleep(0.3)
        elapsed_time += 1
        return elapsed_time

    def close(self, object_id: str):
        """
        Close the specified object.

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
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

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
        log.debug(f"Monitoring: focusing on {object_id}")

        obj_angle, degree = self.navi.agent_rotate_angle(
            agent_position, object_position
        )
        result = None

        if degree != 0:
            # 부드럽게 회전
            for _ in range(SMOOTH_LEVEL):
                result = self.controller.step(
                    action="RotateRight", degrees=degree / SMOOTH_LEVEL
                )
                if not result.metadata["lastActionSuccess"]:
                    # 회전 실패 시 약간 이동 후 재시도
                    self.navi.move_in_direction(-obj_angle, 0.2)
                    result = self.controller.step(
                        action="RotateRight", degrees=degree / SMOOTH_LEVEL
                    )
                self.controller.step(action="Pass")

        # 카메라 각도 조정
        self.navi.adjust_camera_to_object(object_id)
        self.success_log(result, f"adjust camera to {object_id} for monitoring action")
        time.sleep(2)

        # 원위치로 회전
        if degree != 0:
            for _ in range(SMOOTH_LEVEL):
                self.controller.step(action="RotateLeft", degrees=degree / SMOOTH_LEVEL)

        self.controller.step(action="Pass")
        time.sleep(0.1)
        return 0.1

    def wait(self, wait_time=1):
        """
        Wait for the specified duration.
        Args:
            wait_time (float, optional): Duration in seconds. Defaults to 1.

        Returns:
            float: Elapsed time for the wait action.
        """
        time.sleep(wait_time)
        log.debug(f"wait: {wait_time}")
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
        self.controller.step(action="Pass")
        time.sleep(0.3)
        return 1

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
        path = self.navi.find_shortest_path(agent_position, object_position)

        if path:
            # 첫 좌표는 현재 위치이므로 제거
            path.pop(0)

        elapsed_time = 0
        for position in path:
            # 이동 하나 당 0.1초 정도 소요된다고 가정
            elapsed_time += 0.1
            self.navi.teleport_to_position(position)

            # stop_time이 설정되어 있고, elapsed_time이 일정값에 도달하면 중단
            if stop_time is not None and elapsed_time >= stop_time:
                break

        # 목표 지점에 도달한 뒤 오브젝트 쪽으로 에이전트 회전
        agent_position = self.navi.get_agent_position()
        obj_angle, degree = self.navi.agent_rotate_angle(
            agent_position, object_position
        )

        # stop_time이 없을 때에만 최종 회전 진행
        if degree != 0 and stop_time is None:
            for _ in range(SMOOTH_LEVEL):
                self.controller.step(
                    action="RotateRight", degrees=degree / SMOOTH_LEVEL
                )
                success = self.controller.last_event.metadata["lastActionSuccess"]
                if not success:
                    # 회전 실패 시 각도대로 살짝 이동 후 재시도
                    self.navi.move_in_direction(-obj_angle, 0.2)
                    self.controller.step(
                        action="RotateRight", degrees=degree / SMOOTH_LEVEL
                    )

        # 카메라 각도 조정
        self.navi.adjust_camera_to_object(object_id)
        log.debug(f"move to {object_id}")
        self.controller.step(action="Pass")
        time.sleep(0.2)
        return round(elapsed_time, 2)
