import math

from sim.utils.constants import OBJECT_INTERESTS


def euclidean_distance(pointA, pointB):
    return math.dist(pointA, pointB)


def closest_position(object_position, reachable_positions):
    out = reachable_positions[0]
    min_distance = float("inf")
    for pos in reachable_positions:
        # NOTE: y is the vertical direction, so only care about the x/z ground positions
        dist = sum([(pos[key] - object_position[key]) ** 2 for key in ["x", "z"]])
        if dist < min_distance:
            min_distance = dist
            out = pos
    return out


class InteractionHandler:
    def __init__(self, controller):
        self.controller = controller

    def get_obj_info(self):
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

            if self.detect_manipulable_objs():
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

    def detect_manipulable_objs(self):
        manipulable_objects = set(
            self.controller.last_event.metadata["arm"]["pickupableObjects"]
        )
        held_objects = set(self.controller.last_event.metadata["arm"]["heldObjects"])
        return manipulable_objects - held_objects if manipulable_objects else None

    def rotate_to_object(self, object_type):
        obj = self.obj_in_scene(object_type)
        # 0 is arbitrary
        obj_x = obj["position"]["x"]
        obj_z = obj["position"]["z"]

        agent_position = self.controller.last_event.metadata["agent"]["position"]
        agent_x = agent_position["x"]
        agent_z = agent_position["z"]

        a = euclidean_distance([agent_x, agent_z], [obj_x, obj_z])
        b = euclidean_distance([agent_x, agent_z], [agent_x - 2, agent_z])
        c = euclidean_distance([obj_x, obj_z], [agent_x - 2, agent_z])

        gamma = math.degrees(math.acos((a**2 + b**2 - c**2) / (2 * a * b)))
        # print((a ** 2 + b ** 2 - c ** 2) / (2 * a * b))
        # print(f"gamma is {gamma}")
        self.controller.step(action="RotateRight", degrees=gamma)

    def rotate(self, direction):
        self.controller.step(action=f"Rotate{direction}")

    def pick_up(self, objectId, force):
        self.controller.step(
            action="PickupObject", objectId=objectId, forceAction=force
        )

    def toggle_on(self, objectId, force):
        self.controller.step(
            action="ToggleObjectOn", objectId=objectId, forceAction=force
        )

    def toggle_off(self, objectId, force):
        self.controller.step(
            action="ToggleObjectOff", objectId=objectId, forceAction=force
        )

    def slice(self, objectId, force):
        self.controller.step(action="SliceObject", objectId=objectId, forceAction=force)

    def put(self, objectId, force):
        self.controller.step(action="PutObject", objectId=objectId, forceAction=force)

    def open(self, objectId, force):
        self.controller.step(action="OpenObject", objectId=objectId, forceAction=force)

    def close(self, objectId, force):
        self.controller.step(action="CloseObject", objectId=objectId, forceAction=force)

    def look(self, direction):
        self.controller.step(action=f"Look{direction}")

    def obj_in_scene(self, object_type):
        """현재 scene에 object type과 일치하는 object가 있는지 확인"""
        types_in_scene = sorted(
            [
                obj["objectType"]
                for obj in self.controller.last_event.metadata["objects"]
                if obj["visible"] and obj["isInteractable"]
            ]
        )
        assert object_type in types_in_scene, "Object not in scene"
        return next(
            obj
            for obj in self.controller.last_event.metadata["objects"]
            if obj["objectType"] == object_type
        )

    def tp_to_object(self, object_type):
        obj = self.obj_in_scene(object_type)
        reachable_positions = self.controller.step(
            action="GetReachablePositions"
        ).metadata["actionReturn"]
        closest = closest_position(obj["position"], reachable_positions)
        self.controller.step(action="Teleport", **closest)
        self.rotate_to_object(object_type)
        return obj["objectId"]
