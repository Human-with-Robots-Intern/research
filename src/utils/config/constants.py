from pathlib import Path

# ========== 경로 설정 ==========
ROOT_PATH = Path(__file__).resolve().parents[3]
ASSETS_PATH = ROOT_PATH / "assets"
SRC_PATH = ROOT_PATH / "src"
LOG_PATH = ROOT_PATH / "logs"

AGENT_KNOWLEDGE_PATH = ASSETS_PATH / "agent_knowledge"
SCENE_KNOWLEDGE_PATH = ASSETS_PATH / "scene_knowledge"
BATHROOM_PATH = SCENE_KNOWLEDGE_PATH / "bathroom"
BEDROOM_PATH = SCENE_KNOWLEDGE_PATH / "bedroom"
KITCHEN_PATH = SCENE_KNOWLEDGE_PATH / "kitchen"
LIVING_ROOM_PATH = SCENE_KNOWLEDGE_PATH / "living_room"
BAYESIAN_PATH = SCENE_KNOWLEDGE_PATH / "bayesian"

PROMPT_PATH = ASSETS_PATH / "prompts"
TASK_PATH = ASSETS_PATH / "tasks"
RESULT_PATH = ASSETS_PATH / "results"


# ========== 파일명 상수 ==========
PROMPT_FILE_PATH = "e2e_generator_ver7.txt"
ESTIMATE_FILE_NAME = "bayesian_estimate.json"
GROUND_TRUTH_FILE_NAME = "bayesian_ground_truth.json"

# ========== 시뮬레이션 관련 ==========
DEFAULT_SCENE_NAME = "FloorPlan1"
ROOM_TYPE = ["bathroom", "bedroom", "kitchen", "living_room"]
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
STATIC_ACTION_SET = {
    "GRASP",
    "PLACE_INSIDE",
    "PLACE_ON_TOP",
    "OPEN",
    "CLOSE",
    "TOGGLE_ON",
    "TOGGLE_OFF",
    "SLICE",
    "FILL",
}
DYNAMIC_ACTION_SET = {
    "NAVIGATE_TO",
    "WAIT",
    "MONITORING",
}
PRIMITIVE_ACTION_DURATION = 1.0
MONITORING_DURATION = 0.1
NAV_STEP_DURATION = 0.1
REACHABLE_DISTANCE_THRESHOLD = 1.5
# Heuristic constants have been reduced to align with the updated algorithm's expectations:
# - ALPHA_HEURISTIC: Reduced to 2.0 to balance the weight of heuristic influence on decision-making.
# - BETA_HEURISTIC: Reduced to 3.0 to ensure smoother scaling in probabilistic calculations.
# - GAMMA_HEURISTIC: Reduced to 0.3 to minimize overfitting and maintain generalization in predictions.
ALPHA_HEURISTIC = 2.0
BETA_HEURISTIC = 3.0
GAMMA_HEURISTIC = 0.3
# ========== 베이지안 ==========
BAYESIAN_CRITERIA = 0.3
INIT_PRIOR_MEAN = 10.0
INIT_PRIOR_VARIANCE = 100.0
FACTOR_ALPHA = 0.3
SIMILARITY_THRESHOLD = 0.7
MIN_VARIANCE = 1e-6
TIMING_TOLERANCE = 0.15
# ========== 스케줄러 설정 ==========
SIMULATION_DEPTH = 3
BEAM_WIDTH = 3
EPSILON = 1e-1
LARGE_NUMBER = 1e2
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
