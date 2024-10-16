from sim.utils.constants import *


class MoveHandler:
    def __init__(self, controller, camera_handler):
        self.controller = controller
        self.camera_handler = camera_handler
        self.move_step = MOVE_STEP
        self.rotate_step = ROTATE_STEP
        self.run_speed_multiplier = RUN_SPEED_MULTIPLIER

    def move_agent(self, move_action, run_mode=False):
        speed = (
            self.move_step * self.run_speed_multiplier if run_mode else self.move_step
        )
        self.controller.step(action=move_action, moveMagnitude=speed)

        # 성공시, 카메라 뷰 업데이트
        if self.camera_handler.camera_mode == "third_person":
            self.camera_handler.update_third_person_camera()
        elif self.camera_handler.camera_mode == "top_down":
            self.camera_handler.update_top_down_camera()

    def rotate_agent(self, rotate_action):
        self.controller.step(action=rotate_action, degrees=self.rotate_step)
        # 성공시, 카메라 뷰 업데이트
        if self.camera_handler.camera_mode == "third_person":
            self.camera_handler.update_third_person_camera()
        elif self.camera_handler.camera_mode == "top_down":
            self.camera_handler.update_top_down_camera()
