from pathlib import Path

MONITORING_ENABLED = True

# ========== 경로 설정 ==========
ROOT_PATH = Path(__file__).resolve().parents[3]
ASSETS_PATH = ROOT_PATH / "assets"
SRC_PATH = ROOT_PATH / "src"
LOG_PATH = ROOT_PATH / "logs"
SCRIPTS_PATH = ROOT_PATH / "scripts"

AGENT_KNOWLEDGE_PATH = ASSETS_PATH / "agent_knowledge"
SCENE_KNOWLEDGE_PATH = ASSETS_PATH / "scene_knowledge"
BATHROOM_PATH = SCENE_KNOWLEDGE_PATH / "bathroom"
BEDROOM_PATH = SCENE_KNOWLEDGE_PATH / "bedroom"
KITCHEN_PATH = SCENE_KNOWLEDGE_PATH / "kitchen"
LIVING_ROOM_PATH = SCENE_KNOWLEDGE_PATH / "living_room"
BAYESIAN_PATH = SCENE_KNOWLEDGE_PATH / "bayesian"

PROMPT_PATH = ASSETS_PATH / "prompts"
TASK_PATH = ASSETS_PATH / "legacy_task" / "tasks"
RESULT_PATH = ASSETS_PATH / "results"

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
    "NAVIGATE_TO",
}
DYNAMIC_ACTION_SET = {
    "WAIT",
    "MONITORING",
}
# PRIMITIVE_ACTION_DURATION = 15.0
MONITORING_DURATION = 2.33
NAV_STEP_DURATION = 0.13
REAL_NAV_DURATION = 3.31
TOGGLE_ACTION_DURATION = 11.33
GRASP_ACTION_DURATION = 11.55
PLACE_ACTION_DURATION = 8.79

REACHABLE_DISTANCE_THRESHOLD = 50.0

# Heuristic weights
ALPHA_HEURISTIC = 1.0  # Navigation cost
BETA_HEURISTIC = 10.0  # Urgency (slack) cost
GAMMA_HEURISTIC = 100.0  # Remaining work cost

# Wait action control
WAIT_TIME_UPPER_BOUND = 20.0  # 'wait' 액션의 최대 허용 시간 (초)

# ========== 베이지안 ==========
BAYESIAN_CRITERIA = 0.7

GT_INTERVAL = 100.0
INIT_PRIOR_MEAN = 140.0
INIT_PRIOR_VARIANCE = 100.0


# 지우지 마시오. 실험 돌릴동안만 쓰자구요 ㅎㅎㅎ
def set_init_prior_mean(value: float) -> None:
    """전역 INIT_PRIOR_MEAN 값을 설정합니다.

    Args:
        value (float): 새로 설정할 INIT_PRIOR_MEAN 값.
    """
    global INIT_PRIOR_MEAN
    INIT_PRIOR_MEAN = value


def set_monitoring_enabled(value: bool) -> None:
    """Sets the global MONITORING_ENABLED value."""
    global MONITORING_ENABLED
    MONITORING_ENABLED = value


# 지우지 마시오. 실험 돌릴동안만 쓰자구요 ㅎㅎㅎ
def set_init_prior_variance(value: float) -> None:
    """전역 INIT_PRIOR_VARIANCE 값을 설정합니다.

    Args:
        value (float): 새로 설정할 INIT_PRIOR_VARIANCE 값.
    """
    global INIT_PRIOR_VARIANCE
    INIT_PRIOR_VARIANCE = value


def set_alpha_heuristic(value: float) -> None:
    """Sets the global ALPHA_HEURISTIC value."""
    global ALPHA_HEURISTIC
    ALPHA_HEURISTIC = value


def set_beta_heuristic(value: float) -> None:
    """Sets the global BETA_HEURISTIC value."""
    global BETA_HEURISTIC
    BETA_HEURISTIC = value


def set_gamma_heuristic(value: float) -> None:
    """Sets the global GAMMA_HEURISTIC value."""
    global GAMMA_HEURISTIC
    GAMMA_HEURISTIC = value


def set_factor_alpha(value: float) -> None:
    """Sets the global FACTOR_ALPHA value."""
    global FACTOR_ALPHA
    FACTOR_ALPHA = value


def set_beam_width(value: int) -> None:
    """Sets the global BEAM_WIDTH value."""
    global BEAM_WIDTH
    BEAM_WIDTH = value


def set_simulation_depth(value: int) -> None:
    """Sets the global SIMULATION_DEPTH value."""
    global SIMULATION_DEPTH
    SIMULATION_DEPTH = value


FACTOR_ALPHA = 0.001
SIMILARITY_THRESHOLD = 0.7
MIN_VARIANCE = 1e-6

# Timing tolerance can be interpreted both as a ratio and an absolute cap.
# The ratio (30%) mirrors the previous behaviour, while the absolute value
# allows capping the tolerance window for large intervals.
TIMING_TOLERANCE_RATIO = 0.3
TIMING_TOLERANCE_ABS = 15.0
MONITORING_SPLIT_TOLERANCE_ABS = 15.0
# ========== 스케줄러 설정 ==========
SIMULATION_DEPTH = 3
BEAM_WIDTH = 3
EPSILON = 1e-1
LARGE_NUMBER = 1e4
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

# ========== 시간 제약 규칙 ==========
# 시간 제약이 중요한(critical) 객체 유형과 기본 Interval(초)
# 'After' 제약, Urgency: True 목록 기반
CRITICAL_OBJECT_INTERVALS = {
    "StoveBurner": INIT_PRIOR_MEAN,
    "Microwave": INIT_PRIOR_MEAN,
    "Faucet": INIT_PRIOR_MEAN,
    "Kettle": INIT_PRIOR_MEAN,
    "Laundry_Machine": INIT_PRIOR_MEAN,
    "ShowerHead": INIT_PRIOR_MEAN,
    "StoveKnob": INIT_PRIOR_MEAN,  # StoveBurner와 연관
    "Stove": INIT_PRIOR_MEAN,  # StoveBurner와 연관
    "Toilet": INIT_PRIOR_MEAN,
    "ScrubBrush": INIT_PRIOR_MEAN,
    "POT": INIT_PRIOR_MEAN,
    "Egg": INIT_PRIOR_MEAN,
    "CounterTop": INIT_PRIOR_MEAN,
    "CoffeeMachine": INIT_PRIOR_MEAN,
}

# Non-critical이지만 일관된 시간을 적용하고 싶은 객체
# 'After' 제약, Urgency: False 목록 기반
NON_CRITICAL_OBJECT_INTERVALS = {
    "Cup": INIT_PRIOR_MEAN,
    "Mug": INIT_PRIOR_MEAN,
    "Plate": INIT_PRIOR_MEAN,
    "Bread": INIT_PRIOR_MEAN,
    "Egg": INIT_PRIOR_MEAN,
    "CounterTop": INIT_PRIOR_MEAN,
}

CRITICAL_OBJECT_GROUND_TRUTH = {
    "StoveBurner": GT_INTERVAL,
    "Microwave": GT_INTERVAL,
    "Faucet": GT_INTERVAL,
    "Kettle": GT_INTERVAL,
    "Laundry_Machine": GT_INTERVAL,
    "ShowerHead": GT_INTERVAL,
    "StoveKnob": GT_INTERVAL,
    "Stove": GT_INTERVAL,
    "Toilet": GT_INTERVAL,
    "ScrubBrush": GT_INTERVAL,
    "POT": GT_INTERVAL,
    "Egg": GT_INTERVAL,
    "CounterTop": GT_INTERVAL,
    "CoffeeMachine": GT_INTERVAL,
}
#