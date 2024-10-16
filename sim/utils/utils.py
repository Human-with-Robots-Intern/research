import datetime
import json
from pathlib import Path

from sim.utils.constants import OBJECTS_INFO_PATH


def save_the_agent_knowledge(scene_name: str, agent_knowledge: dict):
    # 현재 시간을 파일명으로 사용
    time_index = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    # 저장할 디렉토리 경로
    data_dir = Path(".") / OBJECTS_INFO_PATH
    data_dir.mkdir(parents=True, exist_ok=True)  # 경로가 없으면 생성

    # 파일 저장 경로
    file_path = data_dir / f"{scene_name}.json"

    # 파일 저장
    with file_path.open("w") as f:
        json.dump(agent_knowledge, f)


def load_agent_knowledge(scene_name: str):
    # 파일이 저장된 디렉토리 경로
    file_path = Path.cwd().joinpath(OBJECTS_INFO_PATH) / f"{scene_name}.json"
    try:
        with file_path.open("r") as f:
            agent_knowledge = json.load(f)
    except FileNotFoundError:
        agent_knowledge = {}

    return agent_knowledge


# 사용 예시
# agent_knowledge = {"example_key": "example_value"}
# save_the_agent_knowledge(agent_knowledge)
# recent_knowledge = load_recent_agent_knowledge()
# print(recent_knowledge)
