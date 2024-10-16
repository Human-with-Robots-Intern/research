from handlers.arm_handler import ArmHandler
from handlers.camera_handler import CameraHandler
from handlers.move_handler import MoveHandler
from handlers.object_handler import ObjectHandler


class Teleoperation:
    def __init__(self, controller):
        self.controller = controller
        self.camera_handler = CameraHandler(controller)
        self.move_handler = MoveHandler(controller, self.camera_handler)
        self.arm_handler = ArmHandler(controller)
        self.object_handler = ObjectHandler(controller)
        self.initial_position = None
        self.initial_rotation = None

    def save_initial_position(self):
        agent_metadata = self.controller.last_event.metadata["agent"]
        self.initial_position = agent_metadata["position"]
        self.initial_rotation = agent_metadata["rotation"]

    def teleport_to_initial_position(self):
        if self.initial_position and self.initial_rotation:
            event = self.controller.step(
                action="Teleport",
                position=self.initial_position,
                rotation=self.initial_rotation,
                horizon=self.controller.last_event.metadata["agent"]["cameraHorizon"],
                forceAction=True,
            )
            if event.metadata["lastActionSuccess"]:
                print("초기 위치로 텔레포트되었습니다.")
                # Update camera based on the current mode
                if self.camera_handler.camera_mode == "third_person":
                    self.camera_handler.update_third_person_camera()
                elif self.camera_handler.camera_mode == "top_down":
                    self.camera_handler.update_top_down_camera()
            else:
                print("초기 위치로 이동할 수 없습니다.")
        else:
            print("초기 위치가 저장되지 않았습니다.")

    # Other methods can be added here as needed
    def get_current_frame(self):
        return self.camera_handler.get_current_frame()
