from pathlib import Path

# * 프로젝트 경로
ROOT_PATH = Path(__file__).resolve().parent.parent.parent

KNOWLEDGE_PATH = ROOT_PATH / "assets" / "knowledge"
PROMPT_PATH = ROOT_PATH / "assets" / "prompts"
VIS_PATH = ROOT_PATH / "assets" / "results"
TASK_PATH = ROOT_PATH / "assets" / "tasks"
LOG_PATH = ROOT_PATH / "logs"

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


# * 스케쥴러 관련
SIMULATION_DEPTH = 1
BEAM_WIDTH = 1

EPSILON = 1e-3
LARGE_NUMBER = 1e3

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
