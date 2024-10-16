import numpy as np

from sim.utils.constants import *


class CameraHandler:
    def __init__(self, controller):
        self.controller = controller
        self.camera_mode = "egocentric"
        self.camera_modes = ["egocentric", "third_person", "top_down"]

    def toggle_view(self):
        current_index = self.camera_modes.index(self.camera_mode)
        next_index = (current_index + 1) % len(self.camera_modes)
        self.camera_mode = self.camera_modes[next_index]

        if self.camera_mode == "egocentric":
            self.set_egocentric_view()
        elif self.camera_mode == "third_person":
            self.set_third_person_view()
        elif self.camera_mode == "top_down":
            self.set_top_down_view()

    def calculate_third_person_camera_pos_rot(self):
        agent_position = self.controller.last_event.metadata["agent"]["position"]
        agent_rotation = self.controller.last_event.metadata["agent"]["rotation"]

        theta = np.deg2rad(agent_rotation["y"])
        offset_x = -CAMERA_DISTANCE_BEHIND * np.sin(theta)
        offset_z = -CAMERA_DISTANCE_BEHIND * np.cos(theta)

        position = {
            "x": agent_position["x"] + offset_x,
            "y": agent_position["y"] + CAMERA_HEIGHT_ABOVE,
            "z": agent_position["z"] + offset_z,
        }

        rotation = {
            "x": 20,
            "y": agent_rotation["y"],
            "z": 0,
        }
        return position, rotation

    def set_third_person_view(self):
        position, rotation = self.calculate_third_person_camera_pos_rot()
        self.controller.step(
            action="AddThirdPartyCamera",
            position=position,
            rotation=rotation,
            fieldOfView=60,
        )

    def update_third_person_camera(self):
        position, rotation = self.calculate_third_person_camera_pos_rot()
        self.controller.step(
            action="UpdateThirdPartyCamera",
            thirdPartyCameraId=0,
            position=position,
            rotation=rotation,
            fieldOfView=60,
        )

    def calculate_top_down_camera_pos_rot(self):
        agent_position = self.controller.last_event.metadata["agent"]["position"]
        position = {
            "x": agent_position["x"],
            "y": agent_position["y"] + CAMERA_HEIGHT_ABOVE,
            "z": agent_position["z"],
        }
        rotation = {
            "x": 90,
            "y": 0,
            "z": 0,
        }
        return position, rotation

    def set_top_down_view(self):
        position, rotation = self.calculate_top_down_camera_pos_rot()
        self.controller.step(
            action="AddThirdPartyCamera",
            position=position,
            rotation=rotation,
            fieldOfView=90,
        )

    def update_top_down_camera(self):
        position, rotation = self.calculate_top_down_camera_pos_rot()
        self.controller.step(
            action="UpdateThirdPartyCamera",
            position=position,
            rotation=rotation,
            fieldOfView=90,
        )

    def set_egocentric_view(self):
        self.controller.step(
            action="UpdateThirdPartyCamera",
            thirdPartyCameraId=0,
            position={"x": 0, "y": -100, "z": 0},
        )

    def get_current_frame(self):
        if self.camera_mode == "egocentric":
            return self.controller.last_event.frame
        else:
            return self.controller.last_event.third_party_camera_frames[0]
