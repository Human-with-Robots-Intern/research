# object_utils.py


def detect_manipulable_objs(controller):
    manipulable_objects = set(
        controller.last_event.metadata["arm"]["pickupableObjects"]
    )
    held_objects = set(controller.last_event.metadata["arm"]["heldObjects"])
    return manipulable_objects - held_objects if manipulable_objects else None


def obj_in_scene(controller, object_type):
    """현재 scene에 object type과 일치하는 object가 있는지 확인"""
    types_in_scene = sorted(
        [
            obj["objectType"]
            for obj in controller.last_event.metadata["objects"]
            if obj["visible"] and obj["isInteractable"]
        ]
    )
    assert object_type in types_in_scene, "Object not in scene"
    return next(
        obj
        for obj in controller.last_event.metadata["objects"]
        if obj["objectType"] == object_type
    )
