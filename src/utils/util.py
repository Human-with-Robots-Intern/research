import signal
import time
from functools import wraps


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
        func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Time taken for {func.__name__}: {elapsed_time:.2f} seconds")
        return elapsed_time

    return wrapper


import json


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
