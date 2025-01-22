import json
import logging
import signal
import time
from functools import wraps
from pathlib import Path

from utils.constants import KNOWLEDGE_PATH, LOG_PATH


def create_module_logger(module_name, is_file_handler=False):
    """
    Creates and returns a logger for logging statements from the module represented by @module_name

    Args:
    module_name (str): Module to create the logger for. Should be the module's `__name__` variable

    Returns:
        Logger: Created logger for the module
    """

    logger = logging.getLogger(module_name)
    if is_file_handler:
        logger.setLevel("DEBUG")
        file_handler = logging.FileHandler(
            LOG_PATH / f"{module_name}.log",
            "a",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
    return logger


# log = create_module_logger(module_name=__name__, is_file_handler=True)


class timeout:
    def __init__(self, seconds=1, error_message="Timeout"):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


def timeit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        results = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        # log.warning(f"Elapsed time: {elapsed_time:.2f} seconds")
        return results

    return wrapper


def load_navigation_times():
    with open(KNOWLEDGE_PATH / "FloorPlan1_navigation_time.json", "r") as f:
        navigation_times = json.load(f)
    return navigation_times


def tasks_to_subtasks(tasks, mode="all"):
    subtasks = []
    if mode == "all":
        for task in tasks:
            subtasks.extend(task.subtasks)
    elif mode == "name":
        for task in tasks:
            print(subtasks)
            subtasks.extend([subtask.name for subtask in task.subtasks])
    subtasks = set(subtasks)

    return subtasks


# JSON Task Plan을 Python 코드로 변환하는 함수
def json_to_code(task_plan):
    code_snippets = []

    for task in task_plan:
        task_name = task["Task"]
        code_snippets.append(f"# Task: {task_name}\n")

        for subtask in task["Subtasks"]:
            subtask_name = subtask["Name"]
            repetitions = subtask["Repetition"]
            primitive_actions = subtask["Executions"]["PrimitiveActions"]
            objects = subtask["Executions"]["Objects"]

            code_snippets.append(f"    # Subtask: {subtask_name}")
            for _ in range(repetitions):  # 반복 처리
                for action in primitive_actions:
                    action_parts = action.split()
                    action_type = action_parts[0]
                    object_name = " ".join(action_parts[1:])

                    # 객체 이름 찾기
                    if object_name in objects:
                        resolved_object = (
                            f'env.scene.object_registry("name", "{object_name}")'
                        )
                    else:
                        resolved_object = f'"{object_name}"'

                    # Action 코드 생성
                    code_snippets.append(
                        f"    controller.apply_primitive_action("
                        f"StarterSemanticActionPrimitiveSet.{action_type.upper()}, {resolved_object})"
                    )
    return "\n".join(code_snippets)
