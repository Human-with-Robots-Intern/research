from ..utils.constants import GRID_SIZE

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

    def last_action_success(self, controller):  ## 마지막 행동이 성공했는지 확인
        if controller.last_event.metadata["lastActionSuccess"]:
            return "success\n"
        else:
            return "failure. " + controller.last_event.metadata["errorMessage"] + "\n"

    def pickup(self, object_id: str):
        # 물체 앞으로 갔으니 강제로 물체 집게 함.
        self.controller.step(
            action="PickupObject",
            objectId=object_id,
            forceAction=True,
            manualInteract=False,
        )
        # log_file 에 기록
        self.log_file.write(self.last_action_success(self.controller))

        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def slice(self, object_id: str):
        self.controller.step(action="SliceObject", objectId=object_id)
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def put(self, target_id: str):
        # 집어넣는거
        self.controller.step(
            action="PutObject",
            objectId=target_id,
            forceAction=False,
            placeStationary=True,
        )
        # log_file 에 기록
        self.log_file.write(self.last_action_success(self.controller))

        # 실패하면 일단 손에서 버려. 그래야지 다음 행동에 문제가 되지 않을 듯. 근데 버리면 땅바닥에 굴러다니니깐 거슬릴 것 같은데
        if not self.controller.last_event.metadata["lastActionSuccess"]:
            self.controller.step("MoveAhead")
            self.controller.step(action="DropHandObject", forceAction=True)
        self.log_file.write(
            "Alternative Action: Drop: " + self.last_action_success(self.controller)
        )

        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

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
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def toggleon(self, object_id: str):
        self.controller.step(action="ToggleObjectOn", objectId=object_id)
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def toggleoff(self, object_id: str):
        self.controller.step(action="ToggleObjectOff", objectId=object_id)
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def open(self, object_id: str):
        # 일단 두 발자국 물러나기
        for i in range(2):
            self.controller.step(action="MoveBack", moveMagnitude=None)
            self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.1)

        # 열기
        self.controller.step(
            action="OpenObject", objectId=object_id, openness=1, forceAction=False
        )
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)

    def close(self, object_id: str):
        self.controller.step(
            action="CloseObject", objectId=object_id, forceAction=False
        )
        self.log_file.write(self.last_action_success(self.controller))
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.3)
