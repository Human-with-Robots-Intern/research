from pathlib import Path

# 프로젝트 루트 경로
ROOT_PATH = Path(__file__).resolve().parent.parent.parent

# 각 경로 정의
KNOWLEDGE_PATH = ROOT_PATH / "assets" / "knowledge"
PROMPT_PATH = ROOT_PATH / "assets" / "prompts"
VIS_PATH = ROOT_PATH / "assets" / "results"
TASK_PATH = ROOT_PATH / "assets" / "tasks"
LOG_PATH = ROOT_PATH / "logs"
