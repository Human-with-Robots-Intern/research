# interaction_handler.py


from utils.constants import OBJECT_INTERESTS
from utils.math_utils import *
from utils.object_utils import detect_manipulable_objs, obj_in_scene


class InteractionHandler:
    def __init__(self, controller):
        self.controller = controller

    def pickup_object(self):
        """
        팔의 현재 위치에서 객체를 집는 메소드.
        """
        try:
            # 팔의 현재 위치에서 집을 수 있는 객체 목록 가져오기
            pickupable_objects = self.controller.last_event.metadata["arm"].get(
                "pickupableObjects", []
            )
            if not pickupable_objects:
                print("집을 수 있는 객체가 주변에 없습니다.")
                return

            event = self.controller.step(
                action="PickupObject", objectIdCandidates=pickupable_objects
            )
            # 집기 성공 시 held_object_id 업데이트
            if event.metadata["lastActionSuccess"]:
                print(f"객체를 집었습니다: {pickupable_objects[0]}")
            else:
                print(event.metadata["errorMessage"])
        except Exception as e:
            print(f"PickupObject 액션 중 에러 발생: {str(e)}")

    def drop_object(self):
        """
        현재 들고 있는 객체를 놓는 메소드.
        """
        try:
            event = self.controller.step(action="ReleaseObject")
            if event.metadata["lastActionSuccess"]:
                print(f"객체를 놓았습니다:")
            else:
                print("객체를 놓을 수 없습니다.")
        except Exception as e:
            print(f"DropHandObject 액션 중 에러 발생: {str(e)}")

    def rotate_to_object(self, object_type):
        obj = obj_in_scene(self.controller, object_type)
        obj_position = obj["position"]

        agent_position = self.controller.last_event.metadata["agent"]["position"]

        gamma = calculate_rotation_angle(agent_position, obj_position)
        self.controller.step(action="RotateRight", degrees=gamma)

    def tp_to_object(self, object_type):
        obj = obj_in_scene(self.controller, object_type)
        reachable_positions = self.controller.step(
            action="GetReachablePositions"
        ).metadata["actionReturn"]
        closest = closest_position(obj["position"], reachable_positions)
        self.controller.step(action="Teleport", **closest)
        self.rotate_to_object(object_type)
        return obj["objectId"]

    def detect_object(self):
        """상호 작용 가능한 obj만 추출"""
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

            if detect_manipulable_objs(self.controller):
                obj_interactions.append("manipulable")

            obj_states = [
                state for state in OBJECT_INTERESTS["object_states"] if obj.get(state)
            ]

            if obj_interactions or obj_states:
                object_infos[obj_id] = {
                    "type": obj["objectType"],
                    "interactions": obj_interactions,
                    "states": obj_states,
                }
                print(f"Object ID: {obj_id}")
                print(f"Object interactions: {obj_interactions}")
                print(f"Object states: {obj_states}\n")

        return object_infos
