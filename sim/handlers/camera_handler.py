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

    def set_third_person_view(self):
        position, rotation = self.calculate_third_person_camera_pos_rot()
        self.controller.step(
            action="AddThirdPartyCamera",
            position=position,
            rotation=rotation,
            fieldOfView=60,
        )

    def set_top_down_view(self):
        position, rotation = self.calculate_top_down_camera_pos_rot()
        self.controller.step(
            action="AddThirdPartyCamera",
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

    def update_third_person_camera(self):
        position, rotation = self.calculate_third_person_camera_pos_rot()
        self.controller.step(
            action="UpdateThirdPartyCamera",
            thirdPartyCameraId=0,
            position=position,
            rotation=rotation,
            fieldOfView=60,
        )

    def update_top_down_camera(self):
        position, rotation = self.calculate_top_down_camera_pos_rot()
        self.controller.step(
            action="UpdateThirdPartyCamera",
            position=position,
            rotation=rotation,
            fieldOfView=90,
        )

    def get_current_frame(self):
        if self.camera_mode == "egocentric":
            return self.controller.last_event.frame
        else:
            return self.controller.last_event.third_party_camera_frames[0]

    def get_obj_info(self):
        object_infos = {}
        # 1. visible object만 추출
        objects = [
            obj
            for obj in self.controller.last_event.metadata["objects"]
            if obj["visible"] and obj["isInteractable"]
        ]

        # 2. Object 정보 출력
        for obj in objects:
            # obj_id, interactions, states 추출
            obj_id = obj["objectId"]
            obj_interactions = [
                obj_interaction
                for obj_interaction in OBJECT_INTERESTS["object_interactions"]
                if obj.get(obj_interaction)
            ]

            if self.detect_manipulable_objs is not None:
                obj_interactions.append("manipulable")

            obj_states = [
                obj_state
                for obj_state in OBJECT_INTERESTS["object_states"]
                if obj.get(obj_state)
            ]

            if obj_interactions or obj_states:
                object_infos[obj_id] = {
                    "interactions": obj_interactions,
                    "states": obj_states,
                }
                print(f"Object ID: {obj_id}")
                print(f"Object interactions: {obj_interactions}")
                print(f"Object states: {obj_states}\n")

        return object_infos

    # Manipulation 가능한 Object 감지
    def detect_manipulable_objs(self):
        manipulable_objects = set(
            self.controller.last_event.metadata["arm"]["pickupableObjects"]
        )
        held_objects = set(self.controller.last_event.metadata["arm"]["heldObjects"])
        return manipulable_objects - held_objects if manipulable_objects else None
