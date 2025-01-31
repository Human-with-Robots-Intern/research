from ..utils.constants import GRID_SIZE, SMOOTH_LEVEL
from .navigation_handler import NavigationHandler

import time


# pick
# drop 그냥 손에서 놓기
# put 어디에다가 넣기
# toggle
# open
# close


class Action:
    def __init__(self, controller, camera_handler, log_file):
        self.controller = controller
        self.camera_handler = camera_handler
        self.grid_size = GRID_SIZE
        self.log_file = log_file
        self.navi = NavigationHandler(controller, self.camera_handler)

    def last_action_success(self, controller):  ## 마지막 행동이 성공했는지 확인
        if controller.last_event.metadata["lastActionSuccess"]:
            return "success\n"
        else:
            return "failure. " + controller.last_event.metadata["errorMessage"] + "\n"

    def get_parent_receptacle(self, object_id: str):

        # 해당 object의 부모 receptacle을 찾는 로직 구현
        object_metadata = self.controller.last_event.metadata["objects"]

        # 예시로 object의 metadata에서 parent receptacle을 가져오는 코드 작성
        # 실제로는 controller의 메타데이터나 객체 속성에 따라 다를 수 있음
        for obj in object_metadata:
            if obj["objectId"] == object_id:
                if  obj["parentReceptacles"] is not []:
                    parent_receptacle_ids = obj["parentReceptacles"]
                    print(parent_receptacle_ids)
                    break
        if parent_receptacle_ids:
            parent_receptacle_id = parent_receptacle_ids[0]
        else:
            parent_receptacle_id = None
        return parent_receptacle_id

    def pickup(self, object_id: str):
        # 물체 앞으로 갔으니 강제로 물체 집게 함.
        elapsed_time = 0
        result = self.controller.step(
            action="PickupObject",
            objectId=object_id,
            forceAction=False,
            manualInteract=False,
        )
        # 물체를 집은 후의 결과 처리
        if result.metadata["lastActionSuccess"]:
            # 물체를 성공적으로 집었다면
            self.log_file.write(
                f"pickup {object_id}: " + self.last_action_success(self.controller)
            )
            self.controller.step(action="Pass")
            self.camera_handler.update_view()
            time.sleep(0.3)
            elapsed_time += 1
            return elapsed_time
        else:
            # 물체를 집지 못한 경우, parent receptacle을 열고 다시 시도
            receptacle_id = self.get_parent_receptacle(object_id)

            if receptacle_id:
                # parent receptacle을 열기
                elapsed_time += self.navi.move_to(receptacle_id)
                self.open(receptacle_id)
                elapsed_time += 1
                time.sleep(0.5)

                # 물체를 다시 집기 시도
                result = self.controller.step(
                    action="PickupObject",
                    objectId=object_id,
                    forceAction=True,
                    manualInteract=False,
                )
                if result.metadata["lastActionSuccess"]:
                    # 물체를 성공적으로 집었으면 receptacle을 다시 닫기
                    self.close(receptacle_id)
                    elapsed_time += 1
                    return elapsed_time
                else:
                    self.log_file.write(
                        f"Failed to pick up object {object_id} even after opening the receptacle."
                    )
                    return False
            else:
                self.controller.step(
                    action="PickupObject",
                    objectId=object_id,
                    forceAction=False,
                    manualInteract=False,
                )
                self.log_file.write(
                    f"pickup {object_id}: " + self.last_action_success(self.controller)
                )
                self.controller.step(action="Pass")
                self.camera_handler.update_view()
                time.sleep(0.3)
                elapsed_time += 1
                return elapsed_time
                # self.log_file.write(
                #     f"No parent receptacle found for object {object_id}."
                # )
                # return False

    def slice(self, object_id: str):
        self.controller.step(action="SliceObject", objectId=object_id)
        self.log_file.write(
            f"slice {object_id}: " + self.last_action_success(self.controller)
        )
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time = 1
        return elapsed_time

    def put(self, target_id: str):
        elapsed_time = 1
        # 집어넣는거
        self.controller.step(
            action="PutObject",
            objectId=target_id,
            forceAction=False,
            placeStationary=True,
        )
        # log_file 에 기록
        self.log_file.write(
            f"put {target_id}: " + self.last_action_success(self.controller)
        )

        # 실패하면 일단 손에서 버려. 그래야지 다음 행동에 문제가 되지 않을 듯. 근데 버리면 땅바닥에 굴러다니니깐 거슬릴 것 같은데
        if not self.controller.last_event.metadata["lastActionSuccess"]:
            self.controller.step("MoveAhead")
            self.controller.step(action="DropHandObject", forceAction=True)
            elapsed_time += 1
            self.log_file.write(
                "Alternative Action: Drop: " + self.last_action_success(self.controller)
            )

        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time += 1
        return elapsed_time

    def drop(self):
        self.controller.step(action="DropHandObject", forceAction=False)
        step = 0
        # 강제 액션을 false로 했기 때문에 물체를 조금씩 앞으로 이동시키면서 물체를 놓는 행동이 성공할 때까지 반복(10번 제한)
        while not self.controller.last_event.metadata["lastActionSuccess"]:
            self.controller.step(
                action="MoveHeldObjectAhead", moveMagnitude=0.1, forceVisible=False
            )
            self.controller.step(action="DropHandObject", forceAction=False)
            step += 1
            if step == 10:
                break
        self.log_file.write(f"drop: " + self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time = 1
        return elapsed_time

    def toggleon(self, object_id: str):
        self.controller.step(action="ToggleObjectOn", objectId=object_id)
        self.log_file.write(
            f"toggle on {object_id}: " + self.last_action_success(self.controller)
        )
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time = 1
        return elapsed_time

    def toggleoff(self, object_id: str):
        self.controller.step(action="ToggleObjectOff", objectId=object_id)
        self.log_file.write(
            f"toggle off {object_id}: " + self.last_action_success(self.controller)
        )
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time = 1
        return elapsed_time

    def open(self, object_id: str):
        elapsed_time = 0
        # 일단 두 발자국 물러나기
        for i in range(2):
            self.controller.step(action="MoveBack", moveMagnitude=None)
            self.controller.step(action="Pass")
            elapsed_time += 0.1
        self.camera_handler.update_view()
        time.sleep(0.1)

        # 열기
        self.controller.step(
            action="OpenObject", objectId=object_id, openness=1, forceAction=False
        )
        self.log_file.write(
            f"open {object_id}: " + self.last_action_success(self.controller)
        )
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time += 1
        return elapsed_time

    def close(self, object_id: str):
        self.controller.step(
            action="CloseObject", objectId=object_id, forceAction=False
        )
        self.log_file.write(
            f"close {object_id}: " + self.last_action_success(self.controller)
        )
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
        elapsed_time = 1
        return elapsed_time

    def mornitoring(self, object_id: str):
        # object를 바라보게 하고 다시 돌아봐야함
        agent_position = self.navi.get_agent_position()
        object_position = self.navi.get_object_position(object_id)

        obj_angle, degree = self.navi.agent_rotate_angle(
            agent_position, object_position
        )
        if degree != 0:
            for _ in range(
                SMOOTH_LEVEL
            ):  # 그냥 회전하는거 잘 보고싶어서 세 번에 나누어서 회전
                # 일단 회전하고
                self.controller.step(action="RotateRight", degrees=degree)
                success = self.controller.last_event.metadata["lastActionSuccess"]
                # 실패하면 움직여서 다시 한 번 더 도전. 여기는 while문을 써야할까?
                if not success:
                    self.move_in_direction(-obj_angle, 0.2)
                    self.controller.step(
                        action="RotateRight", degrees=degree / SMOOTH_LEVEL
                    )
                    self.camera_handler.update_view()
                self.controller.step(action="Pass")
                self.camera_handler.update_view()
                time.sleep(0.2)

        time.sleep(1)
        for _ in range(SMOOTH_LEVEL):
            self.controller.step(action="RotateLeft", degrees=degree / SMOOTH_LEVEL)
            self.camera_handler.update_view()
            time.sleep(0.2)
        self.controller.step("Pass")
        time.sleep(1)
        elapsed_time = 0.1
        return elapsed_time

    def wait(self, wait_time=0.5):
        time.sleep(wait_time)
        return wait_time
