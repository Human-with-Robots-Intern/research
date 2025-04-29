from pathlib import Path

# ========== 경로 설정 ==========
ROOT_PATH = Path(__file__).resolve().parents[3]
ASSETS_PATH = ROOT_PATH / "assets"
SRC_PATH = ROOT_PATH / "src"
LOG_PATH = ROOT_PATH / "logs"

KNOWLEDGE_PATH = ASSETS_PATH / "knowledge"
PROMPT_PATH = ASSETS_PATH / "prompts"
TASK_PATH = ASSETS_PATH / "tasks"
RESULT_PATH = ASSETS_PATH / "results"


# ========== 파일명 상수 ==========
PROMPT_FILE_PATH = "e2e_generator_ver5.txt"
ESTIMATE_FILE_NAME = "bayesian_estimate.json"
GROUND_TRUTH_FILE_NAME = "bayesian_ground_truth.json"

# ========== 시뮬레이션 관련 ==========
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
PRIMITIVE_ACTION_DURATION = 1.0
MONITORING_DURATION = 0.1
NAV_STEP_DURATION = 0.1
# ========== 베이지안 ==========
INIT_PRIOR_MEAN = 10.0
INIT_PRIOR_VARIANCE = 10.0
FACTOR_ALPHA = 1.0
# ========== 스케줄러 설정 ==========
SIMULATION_DEPTH = 3
BEAM_WIDTH = 3
EPSILON = 1e-1
LARGE_NUMBER = 1e2
BAYESIAN_CRITERIA = 0.7
TOP_K = 1

# ========== ANSI 로그 색상 ==========
LOG_ROUND = 3
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
WHITE = "\x1b[37m"
RESET = "\x1b[0m"

# ========== AI2-THOR 환경 상수 ==========
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
# SCENE_NAME = "FloorPlan1" 이제 변수로 받아온다.
GRID_SIZE = 0.125
SMOOTH_LEVEL = 30

MOVE_STEP = 0.1
ROTATE_STEP = 2.5
RUN_SPEED_MULTIPLIER = 2

CAMERA_DISTANCE_BEHIND = 0.75
CAMERA_HEIGHT_ABOVE = 1.5

ARM_MOVE_STEP = 0.05
HAND_RADIUS = [0.1, 0.3, 0.5]

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

# ========== 환경 상수 ==========
ENV_PLACEHOLDER = "<ENVIRONMENT_INFO>"

