# object_handler.py
from sim.utils.constants import OBJECT_INTERESTS


class ObjectHandler:
    def __init__(self, controller):
        self.controller = controller

    def get_obj_info(self):
        object_infos = {}
        # 1. visible하고 상호 작용 가능한 object만 추출
        objects = [
            obj
            for obj in self.controller.last_event.metadata["objects"]
            if obj["visible"] and obj["isInteractable"]
        ]

        # 2. Object 정보 출력
        for obj in objects:
            obj_id = obj["objectId"]
            obj_interactions = [
                interaction
                for interaction in OBJECT_INTERESTS["object_interactions"]
                if obj.get(interaction)
            ]

            if self.detect_manipulable_objs():
                obj_interactions.append("manipulable")

            obj_states = [
                state for state in OBJECT_INTERESTS["object_states"] if obj.get(state)
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

    def detect_manipulable_objs(self):
        manipulable_objects = set(
            self.controller.last_event.metadata["arm"]["pickupableObjects"]
        )
        held_objects = set(self.controller.last_event.metadata["arm"]["heldObjects"])
        return manipulable_objects - held_objects if manipulable_objects else None
