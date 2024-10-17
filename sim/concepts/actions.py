def rotate(controller, direction):
    controller.step(action=f"Rotate{direction}")


def pick_up(controller, objectId, force):
    controller.step(action="PickupObject", objectId=objectId, forceAction=force)


def toggle_on(controller, objectId, force):
    controller.step(action="ToggleObjectOn", objectId=objectId, forceAction=force)


def toggle_off(controller, objectId, force):
    controller.step(action="ToggleObjectOff", objectId=objectId, forceAction=force)


def slice(controller, objectId, force):
    controller.step(action="SliceObject", objectId=objectId, forceAction=force)


def put(controller, objectId, force):
    controller.step(action="PutObject", objectId=objectId, forceAction=force)


def open(controller, objectId, force):
    controller.step(action="OpenObject", objectId=objectId, forceAction=force)


def close(controller, objectId, force):
    controller.step(action="CloseObject", objectId=objectId, forceAction=force)


def look(controller, direction):
    controller.step(action=f"Look{direction}")
