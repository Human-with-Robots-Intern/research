import json
from typing import Any, Dict

from utils.config import SCENE_KNOWLEDGE_PATH


def load_knowledge(file_name: str = "bayesian_estimate.json") -> Dict[str, Any]:
    """
    Load the knowledge JSON file.
    파일이 존재하지 않으면 FileNotFoundError를, JSON 디코딩 실패 시 JSONDecodeError를 발생.
    """
    knowledge_file = SCENE_KNOWLEDGE_PATH / file_name

    if knowledge_file.exists():
        try:
            with knowledge_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Error decoding knowledge file: {e}", doc="", pos=0
            )
    else:
        raise FileNotFoundError(f"Knowledge file not found at {knowledge_file}.")


def save_knowledge(
    knowledge: Dict[str, Any], file_name: str = "bayesian_estimate.json"
) -> None:
    """
    Save (overwrite) the knowledge JSON file.
    """
    SCENE_KNOWLEDGE_PATH.mkdir(parents=True, exist_ok=True)
    knowledge_file = SCENE_KNOWLEDGE_PATH / file_name
    try:
        with knowledge_file.open("w", encoding="utf-8") as f:
            json.dump(knowledge, f, indent=4, ensure_ascii=False)
    except Exception as e:
        raise IOError(f"Error saving knowledge: {e}") from e
