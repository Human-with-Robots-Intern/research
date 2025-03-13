from pathlib import Path

# * 프로젝트 경로
ROOT_PATH = Path(__file__).resolve().parent.parent.parent

KNOWLEDGE_PATH = ROOT_PATH / "assets" / "knowledge"
PROMPT_PATH = ROOT_PATH / "assets" / "prompts"
VIS_PATH = ROOT_PATH / "assets" / "results"
TASK_PATH = ROOT_PATH / "assets" / "tasks"
LOG_PATH = ROOT_PATH / "logs"
RESULT_PATH = ROOT_PATH / "assets" / "results"

PROMPT_FILE_PATH = "e2e_generator_ver5.txt"
ESTIMATE_FILE_NAME = "bayesian_estimate.json"
GROUND_TRUTH_FILE_NAME = "bayesian_ground_truth.json"

# * 시뮬레이션 관련 상수
PRIMITIVE_ACTION_SET = {
    "NAVIGATE_TO",
    "GRASP",
    "PLACE_INSIDE",
    "PLACE_ON_TOP",
    "OPEN",
    "CLOSE",
    "TOGGLE_ON",
    "TOGGLE_OFF",
    "SLICE",
    "MONITORING",
    "WAIT",
    "FILL",
}
PRIMITIVE_ACTION_DURATION = 1
MONITORING_DURATION = 0.1
NAV_STEP_DURATION = 0.1


# * 스케쥴러 관련
SIMULATION_DEPTH = 1
BEAM_WIDTH = 1

EPSILON = 1e-1
LARGE_NUMBER = 1e2

BAYESIAN_CRITERIA = 0.7

# * 로깅 관련 상수
LOG_ROUND = 3
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
WHITE = "\x1b[37m"
RESET = "\x1b[0m"


# From Ithor

# constants.py

# test.py
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCENE_NAME = "FloorPlan1"
GRID_SIZE = 0.125
SMOOTH_LEVEL = 30

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
        # "receptacle",
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
        # "receptacleObjectIds",
    ],
}

# utils.py
OBJECTS_INFO_PATH = "data/knowledges"
