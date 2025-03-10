from typing import List

from utils.task import Subtask, Task, TaskGraphBuilder
from utils.constants import PRIMITIVE_ACTION_DURATION, PRIMITIVE_ACTION_SET, KNOWLEDGE_PATH

## 유사도 검사를 위한 import
import json
import requests

# from utils.dataclass import CompletedEntry, SchedulerState
from pathlib import Path

# 프로젝트 루트 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_PATH = PROJECT_ROOT / Path("assets")


API_URL = (
    "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
)
api_token = "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"
headers = {"Authorization": f"Bearer {api_token}"}


def query(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()

def load_object_Ids():
    object_file = ASSETS_PATH / Path("knowledge/FloorPlan1_physics_environment.json")
    with open(object_file, "r") as f:
        objectIds = json.load(f)
    return objectIds


def tasks_to_subtasks(tasks, mode="all"):
    subtasks = []
    if mode == "all":
        for task in tasks:
            subtasks.extend(task.subtasks)
    elif mode == "name":
        for task in tasks:
            print(subtasks)
            subtasks.extend([subtask.name for subtask in task.subtasks])

    return subtasks


def adjust_subtasks_duration(subtasks: List[Subtask]) -> List[Subtask]:
    """
    Adjust the duration intervals of subtasks in the given tasks based on the agent's knowledge.

    Args:
        tasks (List[Task]): List of tasks whose subtasks' durations are to be adjusted.

    Returns:
        List[Task]: The list of tasks with adjusted subtask durations.
    """

    def _get_action_duration(subtask: Subtask) -> float:
        total_duration = 0.0
        for primitive_action in subtask.execution.primitive_actions:
            action_name = primitive_action.split()[0]
            is_valid_action = True if action_name in PRIMITIVE_ACTION_SET else False
            if not is_valid_action:
                raise ValueError(
                    f"Action '{action_name}' not found in the primitive action set."
                )
            if action_name not in {"NAVIGATE_TO", "MONITORING", "WAIT"}:
                total_duration += PRIMITIVE_ACTION_DURATION
        return total_duration

    for subtask in subtasks:

        subtask.duration.interval = _get_action_duration(subtask)
    return subtasks

## sinkbasin 이랑 navgate_to 추가
def revision_primitive_actions(tasks):
    """Check and revision if the PLACE action is followed by a NAVIGATE action."""
    for task in tasks:
        for subtask in task.subtasks:
            actions = subtask.execution.primitive_actions
            updated_actions = []
            for i, action in enumerate(actions):
                if i > 0 and "PLACE" in action and "NAVIGATE" not in actions[i - 1]:
                    to_obj = action.split(" ")[1]
                    updated_actions.append(f"NAVIGATE_TO {to_obj}")
                if "PLACE" in action and "Sink" in action and "SinkBasin" not in action:
                    to_obj = action.split(" ")[1] + "|SinkBasin"
                    updated_actions.append(f"PLACE_INSIDE {to_obj}")
                updated_actions.append(action)
            subtask.execution.primitive_actions = updated_actions
    return tasks

def check_obj_id(tasks):
    objectIds = load_object_Ids()
    all_object_ids = set()
    for key in objectIds:
        all_object_ids.update(objectIds[key])

    for task in tasks:
        for subtask in task.subtasks:
            actions = subtask.execution.primitive_actions
            for i, action in enumerate(actions):
                step = action.split(" ")[0]  ## action 이름
                to_obj = action.split(" ")[1]  ## object의 이름
                if step == "NAVIGATE_TO":
                    if to_obj not in all_object_ids:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": list(all_object_ids),
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = list(all_object_ids)[idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
                elif step in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                    if to_obj not in objectIds["RECEPTACLE"]:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": objectIds["RECEPTACLE"],
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = objectIds["RECEPTACLE"][idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
                else:
                    if to_obj not in objectIds[step]:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": objectIds[step],
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = objectIds[step][idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
    return tasks

def build_tasks_and_constraints(
    task_data: dict, enable_decomposition: bool
) -> tuple[list[Task], dict]:
    """
    Parse the tasks from data, revise primitive actions, adjust subtask duration,
    optionally decompose, and build the task graph.

    :param task_data: The raw task data loaded from JSON.
    :param enable_decomposition: Whether to enable subtask decomposition.
    :return: A tuple containing the list of Task objects and the task graph/constraints.
    """
    tasks = Task.parse_instruction(task_data)
    tasks = check_obj_id(tasks)
    tasks = revision_primitive_actions(tasks)

    if enable_decomposition:
        for task in tasks:
            task.decompose_subtasks()

    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)
    subtasks = tasks_to_subtasks(tasks)
    subtasks = adjust_subtasks_duration(subtasks)
    return subtasks, task_graph

