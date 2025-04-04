### utils/task/task_io.py
import json
from pathlib import Path
from typing import Any

from utils.config.constants import KNOWLEDGE_PATH, TASK_PATH


def load_file(file_path: Path, file_type: str) -> Any:
    """
    지정된 파일 경로에서 데이터를 로딩한다.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"{file_type.capitalize()} file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        if file_type == "json":
            return json.load(f)
        else:
            return f.read()


def load_navigation_times() -> dict:
    file_path = KNOWLEDGE_PATH / "FloorPlan1_physics_navigation_time.json"
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_task_files() -> list[Path]:
    """
    TASK_PATH 디렉토리 내 JSON 파일 목록을 이름 기준으로 정렬하여 반환.
    """
    return sorted(TASK_PATH.glob("*.json"), key=lambda p: p.name)


def load_task_data_from_file(task_file_name: str) -> dict:
    """
    특정 task 파일에서 JSON 데이터를 불러옴.
    """
    target_path = TASK_PATH / task_file_name
    if not target_path.exists():
        raise FileNotFoundError(f"Task file not found: {target_path}")

    with target_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_scene_positions(file_name: str) -> dict[str, tuple[float, float, float]]:
    """
    객체별 3D 위치를 담은 JSON 파일 로드
    """
    file_path = KNOWLEDGE_PATH / file_name
    with file_path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)
    return {k: tuple(v) for k, v in raw_data.items()}


def get_natural_language_from_task_file(task_file_name: str) -> str:
    """
    주어진 task 파일 이름에 해당하는 자연어 설명을 반환
    """
    nl_path = TASK_PATH / "task_natural_languages.json"
    with nl_path.open("r", encoding="utf-8") as f:
        task_nl_dict = json.load(f)

    task_nl_dict = {k.strip(":"): v for k, v in task_nl_dict.items()}
    return task_nl_dict.get(task_file_name, None)
