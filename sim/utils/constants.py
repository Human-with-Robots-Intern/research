# constants.py

# test.py
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCENE_NAME = "FloorPlan1_physics"
GRID_SIZE = 0.125

# MoveHandler.py
MOVE_STEP = 0.1  # 에이전트 이동 거리
ROTATE_STEP = 2.5  # 회전 각도
RUN_SPEED_MULTIPLIER = 2  # 달리기 모드 시 속도 배수

# CameraHandler.py
CAMERA_DISTANCE_BEHIND = 0.75  # 에이전트 뒤의 거리
CAMERA_HEIGHT_ABOVE = 1.5  # Third Person View에서 에이전트 위의 거리

# ArmHandler.py
ARM_MOVE_STEP = 0.05  # 팔 이동 거리
HAND_RADIUS = [0.1, 0.3, 0.5]  # Grasp Radius

# teleop.py
OBJECT_INTERESTS = {
    "object_interactions": [
        "toggleable",
        "breakable",
        "dirtyable",
        "cookable",
        "sliceable",
        "openable",
        "pickupable",
        "moveable",
        "canFillWithLiquid",
        "canBeUsedUp",
    ],
    "object_states": [
        "isToggled",
        "isBroken",
        "isDirty",
        "isCooked",
        "isSliced",
        "isOpen",
        "isPickedUp",
        "isFilledWithLiquid",
        "isUsedUp",
    ],
}

# utils.py
OBJECTS_INFO_PATH = "sim/data/knowledges"
