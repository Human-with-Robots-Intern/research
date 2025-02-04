from pathlib import Path

# 프로젝트 루트 경로
ROOT_PATH = Path(__file__).resolve().parent.parent.parent

# 각 경로 정의
KNOWLEDGE_PATH = ROOT_PATH / "assets" / "knowledge"
PROMPT_PATH = ROOT_PATH / "assets" / "prompts"
VIS_PATH = ROOT_PATH / "assets" / "results"
TASK_PATH = ROOT_PATH / "assets" / "tasks"
LOG_PATH = ROOT_PATH / "logs"

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
}

PRIMITIVE_ACTION_DURATION = 0.1
MONITORING_DURATION = 0.1

# SIMULATION_DEPTH = 2
# BEAM_WIDTH = 3

SIMULATION_DEPTH = 1
BEAM_WIDTH = 1

BAYESIAN_CRITERIA = 0.7

# ANSI 이스케이프 코드 정의
LOG_ROUND = 3
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
WHITE = "\x1b[37m"

RESET = "\x1b[0m"
