import copy

## 유사도 검사를 위한 import
import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Tuple

import requests
from dotenv import load_dotenv
from networkx import DiGraph

from core.task import Duration, Execution, Subtask, Task, TaskGraphBuilder
from scheduler.dataclass import CompletedEntry, SchedulerState
from utils.constants import (
    KNOWLEDGE_PATH,
    MONITORING_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)
from utils.task.sentence_transformer import SentenceSimilarityModel
from utils.util import create_module_logger

load_dotenv()
log = create_module_logger(__name__, module_log=True)
sentence_sim_model = SentenceSimilarityModel.get_instance()


def load_object_Ids():
    with open(KNOWLEDGE_PATH / "FloorPlan1_physics_environment.json", "r") as f:
        objectIds = json.load(f)
    return objectIds


import json
from pathlib import Path
from typing import Dict, List, Literal, Tuple, Union

# 가정: 이미 전역 상수/클래스/함수 등이 아래와 같이 정의되어 있다고 전제
# - Task, Subtask, PRIMITIVE_ACTION_SET, PRIMITIVE_ACTION_DURATION
# - KNOWLEDGE_PATH, sentence_sim_model
# - Task.parse_instruction, tasks.decompose_subtasks
# - TaskGraphBuilder

# -----------------------------------------
# 1. 유틸/헬퍼 함수
# -----------------------------------------


def _load_json_file(file_path: Path) -> dict:
    """주어진 file_path에서 JSON 데이터를 로드하여 반환한다."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_file(file_path: Path, data: dict) -> None:
    """주어진 file_path에 JSON 데이터를 저장한다."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# -----------------------------------------
# 2. Subtask 관련 함수
# -----------------------------------------


def tasks_to_subtasks(
    tasks: List["Task"], mode: Literal["all", "name"] = "all"
) -> Union[List["Subtask"], List[str]]:
    """
    Extract all subtasks (or subtask names) from the given tasks in a single list.

    :param tasks: List of Task objects
    :param mode: "all" -> return a list of Subtask objects,
                 "name" -> return a list of Subtask.name (str)
    :return: List[Subtask] or List[str]
    """
    if mode == "all":
        return [subtask for task in tasks for subtask in task.subtasks]
    elif mode == "name":
        return [subtask.name for task in tasks for subtask in task.subtasks]


def adjust_subtasks_duration(subtasks: List["Subtask"]) -> List["Subtask"]:
    """
    Adjust the duration intervals of the given subtasks based on the agent's knowledge.

    :param subtasks: List of Subtask objects
    :return: The same list of subtasks, with updated .duration.interval
    """

    def _get_action_duration(subtask: "Subtask") -> float:
        total_duration = 0.0
        for primitive_action in subtask.execution.primitive_actions:
            action_name = primitive_action.split()[0]
            if action_name not in PRIMITIVE_ACTION_SET:
                raise ValueError(
                    f"Action '{action_name}' not found in the primitive action set."
                )
            # 특정 액션(NAVIGATE_TO, MONITORING, WAIT 등)은 지속시간 계산 제외
            if action_name not in {"NAVIGATE_TO", "MONITORING", "WAIT"}:
                total_duration += PRIMITIVE_ACTION_DURATION
        return total_duration

    for subtask in subtasks:
        subtask.duration.interval = _get_action_duration(subtask)
    return subtasks


def refine_primitive_actions(tasks: List["Task"]) -> List["Task"]:
    """
    1) 모든 subtask가 첫 액션으로 NAVIGATE_TO <obj>를 가지도록 보장한다.
    2) PLACE 액션이 직전에 NAVIGATE_TO <obj>가 없는 경우, 자동으로 NAVIGATE_TO <obj>를 추가한다.
    3) PLACE 액션 대상이 Sink인데 SinkBasin이 언급되지 않은 경우, 'PLACE_INSIDE <obj>|SinkBasin'로 교정한다.
    """

    # 모든 Subtask 객체를 가져온다
    subtasks = tasks_to_subtasks(tasks, mode="all")

    for subtask in subtasks:
        actions = subtask.execution.primitive_actions
        if not actions:
            continue  # 액션이 아예 없는 경우

        # (1) 첫 액션이 정확히 'NAVIGATE_TO'인가 확인
        first_parts = actions[0].split(" ", 1)
        if first_parts[0] != "NAVIGATE_TO" and len(first_parts) == 2:
            # 첫 액션의 대상(obj)을 가져와 삽입
            _, obj = first_parts
            actions.insert(0, f"NAVIGATE_TO {obj}")

        # (2) PLACE 액션과 Sink 처리 로직
        updated_actions = []
        for i, action in enumerate(actions):
            parts = action.split(" ", 1)
            if len(parts) != 2:
                updated_actions.append(action)
                continue

            base_action, to_obj = parts

            # (a) PLACE* 액션인데 직전 액션이 'NAVIGATE_TO <same obj>'가 아니면 추가
            if (
                i > 0
                and base_action.startswith("PLACE")  # "PLACE_INSIDE", "PLACE_ON_TOP" 등
                and not actions[i - 1].startswith(f"NAVIGATE_TO {to_obj}")
            ):
                updated_actions.append(f"NAVIGATE_TO {to_obj}")

            # (b) Sink 처리: Sink인데 SinkBasin이 없으면 "PLACE_INSIDE <obj>|SinkBasin"로 교정
            if (
                base_action.startswith("PLACE")
                and "Sink" in to_obj
                and "SinkBasin" not in to_obj
            ):
                corrected_obj = f"{to_obj}|SinkBasin"
                updated_actions.append(f"PLACE_INSIDE {corrected_obj}")
            else:
                updated_actions.append(action)

        subtask.execution.primitive_actions = updated_actions

    return tasks


def check_obj_id(tasks: List["Task"]) -> List["Task"]:
    """
    Check and correct any invalid obj_id in tasks' primitive_actions using sentence similarity.
    If an obj_id doesn't match the scene's object list, pick the closest candidate by similarity.
    """

    # 1) scene 에서 사용 가능한 모든 object ID 로드
    object_ids = load_object_Ids()
    all_object_ids = {obj for key in object_ids for obj in object_ids[key]}
    all_object_ids = list(all_object_ids)

    def find_most_similar_object(target: str, candidates: List[str]) -> str:
        if not candidates:
            return target
        sim_scores = [
            sentence_sim_model.compute_cosine_similarity(target, candidate)
            for candidate in candidates
        ]
        idx, _ = max(enumerate(sim_scores), key=lambda x: x[1])
        return candidates[idx]

    def transform_action(action: str) -> str:
        parts = action.split(" ", 1)
        if len(parts) < 2:
            return action  # "ACTION"만 있는 형태 등 예외 처리
        base_action, target_obj = parts

        if base_action == "NAVIGATE_TO":
            candidates = all_object_ids
        elif base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
            candidates = object_ids["RECEPTACLE"]
        else:
            candidates = object_ids.get(base_action, [])

        # 후보에 없으면 유사도 가장 높은 후보로 교체
        if target_obj not in candidates:
            matched = find_most_similar_object(target_obj, candidates)
            return f"{base_action} {matched}"
        else:
            return action

    # 모든 Subtask에 대해 action 교정
    all_subtasks = tasks_to_subtasks(tasks, mode="all")
    for subtask in all_subtasks:
        subtask.execution.primitive_actions = [
            transform_action(a) for a in subtask.execution.primitive_actions
        ]

    return tasks


# -----------------------------------------
# 3. Critical Constraint 업데이트 헬퍼
# -----------------------------------------


def _update_critical_constraint(
    subtask: "Subtask",
    temporal_constraint,
    bayesian_load: dict,
    ground_truth_load: dict,
    similarity_threshold: float = 0.9,
) -> None:
    """
    temporal_constraint가 critical인 경우,
    1) subtask.name과 bayesian_load 키의 유사도를 비교해 가장 가까운 키를 찾는다(유사도가 threshold 이상이면).
    2) 해당 키(또는 자기 자신 subtask.name)에 대응하는 'expected_duration'을 temporal_constraint.interval에 반영한다.
    3) ground_truth_load에 항목이 없으면 기본값(10)을 추가한다.

    이 함수는 bayesian_load, ground_truth_load를 **메모리 상에서만** 수정한다.
    실제 파일 저장은 외부에서 최종적으로 수행해야 한다.
    """
    bayesian_keys = list(bayesian_load.keys())
    sim_scores = [
        sentence_sim_model.compute_cosine_similarity(subtask.name, bayesian_key)
        for bayesian_key in bayesian_keys
    ]
    idx, _ = max(enumerate(sim_scores), key=lambda x: x[1])

    # threshold 이상이면 해당 key를, 아니면 자기 자신(subtask.name)을 사용
    similar_subtask = (
        bayesian_keys[idx] if sim_scores[idx] >= similarity_threshold else subtask.name
    )

    # bayesian_load 갱신
    if similar_subtask in bayesian_load:
        temporal_constraint.interval = bayesian_load[similar_subtask][
            "expected_duration"
        ]
    else:
        # 새로 추가
        bayesian_load[subtask.name] = {
            "expected_duration": temporal_constraint.interval,
            "variance": 1.0,
        }

    # ground_truth_load 갱신
    if similar_subtask not in ground_truth_load:
        ground_truth_load[similar_subtask] = 10


# -----------------------------------------
# 4. 메인 빌드 함수
# -----------------------------------------


def build_tasks_and_constraints(
    task_data: dict, enable_decomposition: bool
) -> Tuple[List["Subtask"], Dict]:
    """
    1) Parse the tasks from raw data
    2) Check & refine actions
    3) (Optionally) decompose tasks
    4) Apply critical constraint updates
    5) Re-refine actions if needed, adjust subtask durations
    6) Build a task graph

    :param task_data: The raw task data loaded from JSON.
    :param enable_decomposition: Whether to enable subtask decomposition.
    :return: (subtasks, task_graph)
    """

    # 1) JSON 파일 로드
    bayesian_load = _load_json_file(KNOWLEDGE_PATH / "bayesian_estimate.json")
    ground_truth_load = _load_json_file(KNOWLEDGE_PATH / "bayesian_ground_truth.json")

    # 2) Task 파싱 및 초기 액션 교정
    tasks = Task.parse_instruction(task_data)

    tasks = check_obj_id(tasks)
    tasks = refine_primitive_actions(tasks)

    # 3) subtask decomposition 옵션
    if enable_decomposition:
        tasks = [task.decompose_subtasks() for task in tasks]

    # 4) critical constraint 처리
    subtasks = tasks_to_subtasks(tasks, mode="all")
    for subtask in subtasks:
        for tc in subtask.temporal_constraints:
            if tc.is_critical:
                _update_critical_constraint(
                    subtask,
                    tc,
                    bayesian_load,
                    ground_truth_load,
                )

    # 5) 파일 저장을 **한 번**에 처리 (변경 내용 반영)
    _save_json_file(KNOWLEDGE_PATH / "bayesian_estimate.json", bayesian_load)
    _save_json_file(KNOWLEDGE_PATH / "bayesian_ground_truth.json", ground_truth_load)

    # 6) 다시 한 번 액션 정제(기존 로직을 유지하되, 꼭 필요 없다면 제거 가능)
    tasks = refine_primitive_actions(tasks)
    # 서브태스크들의 지속시간 조정
    subtasks = adjust_subtasks_duration(subtasks)

    # 7) TaskGraph 빌드
    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)

    # 8) 최종 결과 반환
    return subtasks, task_graph


def get_init_state(
    subtasks: List[Subtask], constraints: DiGraph, scene_poses: dict
) -> SchedulerState:
    init_subtask = Subtask(
        task_name=None,
        name="Init",
        duration=Duration(interval=0, type="Init"),
        repetition=1,
        type="Init",
        execution=Execution(objects=[], primitive_actions=None),
        temporal_constraints=None,
    )
    init_completed = CompletedEntry(
        subtask=init_subtask,
        start_time=0.0,
        end_time=0.0,
    )

    init_state = SchedulerState(
        subtask=init_subtask,
        completed_subtasks=[init_completed],
        remaining_subtasks=subtasks,
        constraints=constraints,
        current_time=0,
        scene_positions=scene_poses,
        held_object=None,
    )
    return init_state


def make_monitoring_subtask(name: str, obj: str = None) -> Subtask:
    monitoring_action = None if obj is None else [f"MONITORING {obj}"]
    monitoring_subtask = Subtask(
        task_name=None,
        name=f"Monitoring for {name}_{uuid.uuid4().hex[:8]}",
        duration=Duration(interval=MONITORING_DURATION, type="Monitor"),
        repetition=1,
        type="Monitor",
        execution=Execution(objects=[], primitive_actions=monitoring_action),
        temporal_constraints=None,
        decomposed=True,
    )
    return monitoring_subtask
