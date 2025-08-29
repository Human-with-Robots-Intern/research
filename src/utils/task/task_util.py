# utils/task/task_util.py
from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Literal, Tuple, Union

from dotenv import load_dotenv
from networkx import DiGraph

from src.models.dataclass import CompletedEntry, SchedulerState
from src.models.task import Duration, Execution, Subtask, Task, TemporalConstraint

# 내부 프로젝트 모듈
from src.utils.common import create_module_logger
from src.utils.config.constants import (  # 분산 값도 상수로 사용하기 위해 추가
    AGENT_KNOWLEDGE_PATH,
    CRITICAL_OBJECT_INTERVALS,
    EPSILON,
    ESTIMATE_FILE_NAME,
    GT_INTERVAL,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
    MONITORING_DURATION,
    NON_CRITICAL_OBJECT_INTERVALS,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
    SCENE_KNOWLEDGE_PATH,
)
from src.utils.nlp.sentence_transformer import SentenceSimilarityModel

load_dotenv()
log = create_module_logger(__name__, module_log=True)


class TaskUtil:
    """
    Task(혹은 Subtask) 처리와 관련된 유틸리티 메서드들을 제공하는 클래스.
    """

    # Sentence Transformer 인스턴스(싱글톤) 로드
    _sentence_sim_model = SentenceSimilarityModel.get_instance()

    @staticmethod
    def _load_json_file(file_path: Path) -> dict:
        """
        주어진 file_path에서 JSON 데이터를 로드하여 반환한다.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save_json_file(file_path: Path, data: dict) -> None:
        """
        주어진 file_path에 JSON 데이터를 저장한다.
        """
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def _load_object_ids(scene_file_name: str) -> Dict[str, List[str]]:
        """
        scene_name_physics.json  파일에서 object ID 정보를 로드한다.
        """
        room_type_dirs = list(SCENE_KNOWLEDGE_PATH.glob("*"))
        for room_type_dir in room_type_dirs:
            file_path = room_type_dir / "environment" / f"{scene_file_name}"
            if file_path.exists():
                return TaskUtil._load_json_file(file_path)
        # If the loop completes without finding the file, raise an error.
        raise FileNotFoundError(
            f"Physics file for scene '{scene_file_name}' not found in any subdirectories of {file_path}"
        )

    @staticmethod
    def tasks_to_subtasks(
        tasks: List[Task],
        mode: Literal["all", "name"] = "all",
    ) -> Union[List[Subtask], List[str]]:
        """
        주어진 Task 리스트에서 모든 Subtask(혹은 subtask name)만 추출하여 반환한다.

        :param tasks: List of Task
        :param mode:
          - "all": Subtask 객체 리스트
          - "name": Subtask의 name(str) 리스트
        :return: Subtask 리스트 or Subtask name 리스트
        """
        if mode == "all":
            return [subtask for task in tasks for subtask in task.subtasks]
        elif mode == "name":
            return [subtask.name for task in tasks for subtask in task.subtasks]
        else:
            raise ValueError("mode must be either 'all' or 'name'.")

    @staticmethod
    def adjust_subtasks_duration(subtasks: List[Subtask]) -> List[Subtask]:
        """
        Subtask들의 duration.interval 값을, 에이전트의 사전 지식을 기반으로 보정한다.
        (PRIMITIVE_ACTION_DURATION 등을 참조)

        :param subtasks: Subtask 리스트
        :return: 동일 Subtask 리스트(단, duration.interval만 업데이트)
        """

        def _get_action_duration(st: Subtask) -> float:
            total_duration = 0.0
            for primitive_action in st.execution.primitive_actions:
                action_name = primitive_action.split()[0]
                if action_name not in PRIMITIVE_ACTION_SET:
                    raise ValueError(
                        f"Action '{action_name}' not found in the primitive action set."
                    )
                # NAVIGATE_TO, MONITORING, WAIT 등은 지속시간 계산 제외
                if action_name not in {"NAVIGATE_TO", "MONITORING", "WAIT"}:
                    total_duration += PRIMITIVE_ACTION_DURATION
            return total_duration

        for subtask in subtasks:
            subtask.duration.interval = _get_action_duration(subtask)
        return subtasks

    @staticmethod
    def refine_primitive_actions(tasks: List[Task]) -> List[Task]:
        """
        1) 모든 subtask가 첫 액션으로 'NAVIGATE_TO <obj>'를 가지도록 보장
        2) PLACE 액션이 직전에 'NAVIGATE_TO <obj>'가 없는 경우, 자동으로 NAVIGATE_TO <obj> 추가
        3) Sink 처리: Sink인데 SinkBasin이 언급되지 않은 경우, 'PLACE_INSIDE <obj>|SinkBasin'로 교정
        """
        subtasks = TaskUtil.tasks_to_subtasks(tasks, mode="all")

        for st in subtasks:
            actions = st.execution.primitive_actions
            if not actions:
                continue

            # (1) 첫 액션이 'NAVIGATE_TO'인지 확인, 아니면 삽입
            first_parts = actions[0].split(" ", 1)
            if first_parts[0] != "NAVIGATE_TO" and len(first_parts) == 2:
                _, obj = first_parts
                actions.insert(0, f"NAVIGATE_TO {obj}")

            # (2), (3) PLACE 액션 보정 + SinkBasin 처리
            updated_actions = []
            for i, action in enumerate(actions):
                parts = action.split(" ", 1)
                if len(parts) != 2:
                    updated_actions.append(action)
                    continue

                base_action, to_obj = parts

                # PLACE 계열인데 직전 액션이 NAVIGATE_TO <same obj>가 아닌 경우
                if (
                    i > 0
                    and base_action.startswith("PLACE")
                    and not actions[i - 1].startswith(f"NAVIGATE_TO {to_obj}")
                ):
                    updated_actions.append(f"NAVIGATE_TO {to_obj}")

                # Sink → SinkBasin 교정
                if (
                    base_action.startswith("PLACE")
                    and "Sink" in to_obj
                    and "SinkBasin" not in to_obj
                ):
                    corrected_obj = f"{to_obj}|SinkBasin"
                    updated_actions.append(f"PLACE_INSIDE {corrected_obj}")
                else:
                    updated_actions.append(action)

            st.execution.primitive_actions = updated_actions

        return tasks

    @classmethod
    def check_obj_id(cls, scene_name: str, tasks: List[Task]) -> List[Task]:
        """
        scene_name 은 physics_environment.json 으로 끝남
        Subtask의 primitive_actions에 사용된 obj_id가 유효한지 확인 후,
        유효하지 않다면 문장 유사도 기반으로 가장 가까운 후보로 교체한다.
        """
        from src.utils.io_utils.task_io import load_scene_positions

        # 1) Load all available object IDs and their categories for the scene
        object_categories = cls._load_object_ids(scene_name)
        scene_positions = load_scene_positions(scene_name)
        all_object_ids_in_scene = list(scene_positions.keys())

        # Create a reverse map from object type to a list of full object IDs in the scene
        object_map_in_scene = {}
        for category, object_types in object_categories.items():
            for obj_type in object_types:
                # Find all instances of this object type in the current scene
                matching_instances = [
                    full_id
                    for full_id in all_object_ids_in_scene
                    if full_id.startswith(obj_type)
                ]
                if matching_instances:
                    if category not in object_map_in_scene:
                        object_map_in_scene[category] = []
                    object_map_in_scene[category].extend(matching_instances)

        def transform_action(action: str) -> str:
            parts = action.split(" ", 1)
            if len(parts) < 2:
                return action  # e.g., "ACTION" only

            base_action, target_obj = parts

            # If the target object is already valid in the scene, no change needed
            if target_obj in all_object_ids_in_scene:
                return action

            # Determine the candidate list based on the action type
            if base_action == "NAVIGATE_TO":
                candidates = all_object_ids_in_scene
            elif base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                candidates = object_map_in_scene.get("RECEPTACLE", [])
                split_obj = target_obj.split(" ", 1)
                if len(split_obj) > 1:
                    obj1, obj2 = split_obj
                    obj1_type = obj1.split("|")[0]
                    obj2_type = obj2.split("|")[0]

                    receptacle_types = object_categories.get("RECEPTACLE", [])
                    recepacles = set()
                    for receptacle_type in receptacle_types:
                        receptacle_type = receptacle_type.split("|")[0]
                        recepacles.add(receptacle_type)

                    is_obj1_receptacle = obj1_type in recepacles
                    is_obj2_receptacle = obj2_type in recepacles

                    if is_obj2_receptacle:
                        target_obj = obj2
                    elif is_obj1_receptacle:
                        target_obj = obj1
                    else:
                        raise ValueError(
                            f"For action '{action}', neither '{obj1}' nor '{obj2}' is a valid receptacle."
                        )
                else:
                    # When only one object is specified for a PLACE action, it's assumed to be the receptacle.
                    target_obj = target_obj
            else:
                # Fallback for other actions, get candidates of the same type
                target_obj_type = target_obj.split("|")[0]
                candidates = [
                    obj_id
                    for obj_id in all_object_ids_in_scene
                    if obj_id.startswith(target_obj_type)
                ]
                # If no candidates of the same type, use all objects as a last resort
                if not candidates:
                    candidates = all_object_ids_in_scene

            # If there are no candidates, we cannot correct the action
            if not candidates:
                log.warning(f"Could not find any candidates for action: {action}")
                return action

            # Find the most similar valid object and replace it
            matched = cls._sentence_sim_model.get_similar_ref(target_obj, candidates)
            log.debug(
                f"Correcting object in action '{action}': replaced '{target_obj}' with '{matched}'"
            )
            return f"{base_action} {matched}"

        # Correct actions for all subtasks
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        for st in subtasks:
            st.execution.primitive_actions = [
                transform_action(a) for a in st.execution.primitive_actions
            ]

        return tasks

    @classmethod
    def _update_constraint_belief(
        cls,
        predecessor_name: str,
        temporal_constraint: "TemporalConstraint",
        bayesian_load: dict,
    ) -> None:
        """
        주어진 객체 유형을 key로 하여, interval과 초기 Belief를 INIT_PRIOR_MEAN으로 통일한다.
        """
        belief_value = INIT_PRIOR_MEAN if temporal_constraint.interval != 0.0 else 0.0
        temporal_constraint.interval = belief_value
        # 인자를 명확히 변경

        if predecessor_name not in bayesian_load:
            log.info(
                f"Setting initial belief for '{predecessor_name}' to {belief_value:.2f}"
            )
            bayesian_load[predecessor_name] = {
                "expected_duration": belief_value,
                "variance": INIT_PRIOR_VARIANCE,
            }

    @classmethod
    def _update_critical_constraint(
        cls, st: Subtask, tc: Duration, bayesian_load: dict
    ) -> None:
        """
        Critical constraint의 interval을 INIT_PRIOR_MEAN으로 통일하고,
        Belief를 업데이트한다.
        """
        tc.interval = INIT_PRIOR_MEAN
        obj_type = st.name.split("|")[0] if "|" in st.name else st.name
        cls._update_constraint_belief(obj_type, tc, bayesian_load)

    @classmethod
    def _update_non_critical_constraint(cls, tc: Duration, bayesian_load: dict) -> None:
        """
        Non-critical constraint의 interval을 규칙 기반 값으로 통일하고,
        Belief를 업데이트한다.
        """
        forced_interval = None
        for obj_type in tc.objects:
            if obj_type in NON_CRITICAL_OBJECT_INTERVALS:
                forced_interval = NON_CRITICAL_OBJECT_INTERVALS[obj_type]
                break
        if forced_interval is not None:
            tc.interval = forced_interval

        # Belief 저장을 위한 key는 선행 subtask 이름
        # (에이전트가 Monitor할 때 subtask 이름을 보기 때문)
        key_for_belief = (
            tc.objects[0].split("|")[0] if "|" in tc.objects[0] else tc.objects[0]
        )
        cls._update_constraint_belief(key_for_belief, tc, bayesian_load)

    @classmethod
    def build_tasks_and_constraints(
        cls,
        task_data: dict,
        scene_file_name: str,
        enable_decomposition: bool = True,
    ) -> Tuple[List[Subtask], DiGraph]:
        """
        1) JSON 형태의 raw task_data를 Task로 파싱
        2) Object ID 검사 + 액션 정제(check_obj_id, refine_primitive_actions)
        3) 필요 시 enable_decomposition=True → 서브태스크 분해
        4) critical/non-critical constraint의 interval 값을 규칙 기반으로 설정하고, belief 딕셔너리 생성
        5) 생성된 belief 딕셔너리를 파일(bayesian_estimate.json)에 저장 (디버깅용)
        6) 다시 액션 정제 + Subtask duration 보정
        7) TaskGraph 빌드

        :param task_data: JSON 형태(이미 파싱된 Dict)
        :param enable_decomposition: 서브태스크 분해 여부
        :return: (최종 Subtask 리스트, TaskGraph 객체)
        """
        from src.models.task import Task, TaskGraphBuilder

        # 재현 가능한 실험을 위해 시드 고정
        random.seed(42)

        # 1) 빈 belief 딕셔너리 생성 (파일 로드 제거)
        bayesian_load = {}

        # 2) Task 파싱, Object ID/액션 보정
        tasks = Task.parse_instruction(task_data)
        tasks = cls.check_obj_id(scene_file_name, tasks)
        tasks = cls.refine_primitive_actions(tasks)

        # 3) enable_decomposition 옵션 처리
        if enable_decomposition:
            tasks = [t.decompose_subtasks() for t in tasks]

        # 4) temporal constraint 처리 (규칙 기반 Interval 설정 포함)
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        for st in subtasks:
            involved_object_types = set()
            if st.execution and st.execution.objects:
                for obj_name in st.execution.objects.keys():
                    involved_object_types.add(obj_name.split("|")[0])

            for tc in st.temporal_constraints:
                triggering_obj_type = None
                for obj_type in involved_object_types:
                    if (
                        obj_type in CRITICAL_OBJECT_INTERVALS
                        or obj_type in NON_CRITICAL_OBJECT_INTERVALS
                    ):
                        triggering_obj_type = obj_type
                        break

                # 규칙 기반 객체가 있거나, LLM이 critical로 지정한 경우
                if triggering_obj_type or tc.is_critical:
                    # Key는 발견된 객체 유형을 최우선으로 사용
                    # 객체가 규칙에 없는데 critical인 경우, subtask 이름을 key로 사용
                    key_for_belief = (
                        triggering_obj_type if triggering_obj_type else st.name
                    )
                    print(f"key_for_belief: {key_for_belief}")
                    cls._update_constraint_belief(key_for_belief, tc, bayesian_load)

        # 5) 생성된 belief 딕셔너리를 디버깅용으로 저장
        # cls._save_json_file(AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME, bayesian_load)

        # 6) 액션 정제(재적용) + duration 조정
        tasks = cls.refine_primitive_actions(tasks)
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        subtasks = cls.adjust_subtasks_duration(subtasks)

        # 7) TaskGraph 빌드
        task_graph_builder = TaskGraphBuilder()
        task_graph = task_graph_builder.build_graph(tasks)

        return subtasks, task_graph, bayesian_load

    @staticmethod
    def get_init_state(
        subtasks: List[Subtask],
        constraints: DiGraph,
        scene_poses: dict,
    ) -> SchedulerState:
        """
        Init Subtask 및 SchedulerState를 구성한다.
        """
        init_subtask = Subtask(
            task_name=None,
            name="Init",
            duration=Duration(interval=0, type="Init"),
            repetition=1,
            subtask_type="Init",
            execution=Execution(objects=[], primitive_actions=None),
            temporal_constraints=None,
        )
        init_completed = CompletedEntry(
            subtask=init_subtask,
        )

        init_state = SchedulerState(
            subtask=init_subtask,
            completed_entries=[init_completed],
            remaining_subtasks=subtasks,
            constraints=constraints,
            current_time=0,
            scene_positions=scene_poses,
            held_object=None,
        )
        return init_state

    @staticmethod
    def create_monitoring_subtask(name: str, obj: str = None) -> Subtask:
        """
        MONITORING 액션을 수행하는 Subtask를 생성해 반환한다.
        """
        monitoring_action = None if obj is None else [f"MONITORING {obj}"]
        monitoring_subtask = Subtask(
            task_name=None,
            name=f"Monitoring for {name}_{uuid.uuid4().hex[:8]}",
            duration=Duration(
                interval=MONITORING_DURATION,
                type="Monitor",
                total_time=MONITORING_DURATION,
            ),
            repetition=1,
            subtask_type="Monitor",
            execution=Execution(objects=[obj], primitive_actions=monitoring_action),
            temporal_constraints=None,
            decomposed=True,
        )
        return monitoring_subtask
