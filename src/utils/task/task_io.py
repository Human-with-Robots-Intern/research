import json
from pathlib import Path

from utils.config import KNOWLEDGE_PATH, ROOT_PATH, TASK_PATH
from utils.task.task_generator import TaskGenerator


def load_navigation_times():
    with open(
        KNOWLEDGE_PATH / "FloorPlan1_physics_navigation_time.json",
        "r",
        encoding="utf-8",
    ) as f:
        navigation_times = json.load(f)
    return navigation_times


def list_task_files() -> list[Path]:
    """
    List all JSON task files in the TASK_PATH directory, sorted by file name.

    :return: List of Path objects pointing to JSON files.
    """
    return sorted(TASK_PATH.glob("*.json"), key=lambda p: p.name)


def get_user_task_choice(
    task_files: list[Path], choice: int = None, is_rag=False
) -> str:
    """
    Prompt the user to select a task file by index or choose to create a new instruction.

    :param task_files: List of available task files.
    :return: The selected or newly generated task file name.
    """
    print("Select a file from the list below:")
    print("0. new instruction")
    for idx, file_path in enumerate(task_files, start=1):
        print(f"{idx}. {file_path.name}")

    while True:
        try:
            if not choice:
                choice = int(input("Enter the number of your choice: "))

            if choice == 0:
                user_input = input("Enter your instruction: ")
                return TaskGenerator(is_rag).generate_task(user_input)
            elif 1 <= choice <= len(task_files):
                return task_files[choice - 1].name
            else:
                print(
                    f"Invalid choice. Please select a number between 0 and {len(task_files)}."
                )
        except ValueError as exc:
            print(f"Invalid input. Please enter a number. Error: {exc}")
        choice = None


def load_task_data_from_file(task_file_name: str) -> dict:
    """
    Load task data from a JSON file.

    :param task_file_name: Name of the task file to load.
    :return: Dictionary containing the loaded task data.
    """
    target_task_path = TASK_PATH / task_file_name
    if not target_task_path.exists():
        raise FileNotFoundError(f"Task file not found: {target_task_path}")

    with open(target_task_path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_scene_positions(
    file_name: str,
) -> dict[str, tuple[float, float, float]]:
    """
    Load scene positions from a JSON file.

    :param file_path: Path to the JSON file containing scene positions.
    :return: Dictionary containing scene positions.
    """
    file_path = KNOWLEDGE_PATH / file_name
    with open(file_path, "r", encoding="utf-8") as f:
        scene_positions = json.load(f)
    for key, value in scene_positions.items():
        scene_positions[key] = tuple(value)
    return scene_positions


def get_natural_language_from_task_file(
    task_file_name: int, task_json_path=None
) -> str:
    """
    task_file_name에 해당하는 자연어 설명을 반환한다.
    기본 경로는 root/assets/tasks/task_natural_languages.json

    Args:
        task_file_name (int): task 번호 (예: 1, 2, ...)
        task_json_path (str or Path, optional): JSON 파일 경로

    Returns:
        str: 해당 task에 대한 자연어 설명
    """
    if task_json_path is None:

        task_json_path = ROOT_PATH / "assets" / "tasks" / "task_natural_languages.json"
    else:
        task_json_path = Path(task_json_path)

    with open(task_json_path, "r", encoding="utf-8") as f:
        task_nl_map = json.load(f)

    # int 키를 문자열로 변환하여 검색
    key = str(task_file_name)
    return task_nl_map.get(key, "[Unknown Task]")
