# utils/task/task_util.py

import json
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Tuple, Union

from dotenv import load_dotenv
from networkx import DiGraph

from core.dataclass import CompletedEntry, SchedulerState
from core.task import Duration, Execution, Subtask, Task, TaskGraphBuilder

# 내부 프로젝트 모듈
from utils.common import create_module_logger
from utils.config.constants import (
    ESTIMATE_FILE_NAME,
    GROUND_TRUTH_FILE_NAME,
    MONITORING_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
    SCENE_KNOWLEDGE_PATH,
)
from utils.nlp.sentence_transformer import SentenceSimilarityModel

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
        Subtask의 primitive_actions에 사용된 obj_id가 유효한지 확인 후,
        유효하지 않다면 문장 유사도 기반으로 가장 가까운 후보로 교체한다.
        """
        # 1) scene에서 사용 가능한 모든 object ID 로드
        object_ids_map = cls._load_object_ids(scene_name)
        # 모든 object id를 flatten
        all_object_ids = {
            obj for category in object_ids_map for obj in object_ids_map[category]
        }
        all_object_ids = list(all_object_ids)

        def find_most_similar_object(target: str, candidates: List[str]) -> str:
            if not candidates:
                return target
            sim_scores = [
                cls._sentence_sim_model.compute_cosine_similarity(target, candidate)
                for candidate in candidates
            ]
            idx, _ = max(enumerate(sim_scores), key=lambda x: x[1])
            return candidates[idx]

        def transform_action(action: str) -> str:
            parts = action.split(" ", 1)
            if len(parts) < 2:
                return action  # 예: "ACTION"만 있는 형태 등
            base_action, target_obj = parts

            # 액션 종류별 후보 목록
            if base_action == "NAVIGATE_TO":
                candidates = all_object_ids
            elif base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                candidates = object_ids_map.get("RECEPTACLE", [])
            else:
                candidates = object_ids_map.get(base_action, [])

            # 후보에 없으면 유사도 가장 높은 후보로 교체
            if target_obj not in candidates:
                matched = find_most_similar_object(target_obj, candidates)
                return f"{base_action} {matched}"
            else:
                return action

        # 모든 Subtask에 대해 action 교정
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        for st in subtasks:
            st.execution.primitive_actions = [
                transform_action(a) for a in st.execution.primitive_actions
            ]

        return tasks

    @classmethod
    def _update_critical_constraint(
        cls,
        subtask: Subtask,
        temporal_constraint,
        bayesian_load: dict,
        ground_truth_load: dict,
        similarity_threshold: float = 0.9,
    ) -> None:
        """
        critical constraint인 경우,
        1) subtask.name과 bayesian_load 키들의 유사도를 비교해 가장 가까운 항목 찾기
        2) threshold 이상이면 해당 key의 expected_duration을 사용, 아니면 subtask.name 사용
        3) ground_truth_load에 항목이 없으면 기본값(10)으로 추가
        """
        bayesian_keys = list(bayesian_load.keys())
        if not bayesian_keys:
            return

        sim_scores = [
            cls._sentence_sim_model.compute_cosine_similarity(subtask.name, key)
            for key in bayesian_keys
        ]
        idx, best_score = max(enumerate(sim_scores), key=lambda x: x[1])
        similar_subtask = (
            bayesian_keys[idx].lower()
            if best_score >= similarity_threshold
            else subtask.name.lower()
        )

        # bayesian_load 갱신
        if similar_subtask in bayesian_load:
            temporal_constraint.interval = bayesian_load[similar_subtask][
                "expected_duration"
            ]
        else:
            # 새로 추가
            bayesian_load[subtask.name.lower()] = {
                "expected_duration": temporal_constraint.interval,
                "variance": 1.0,
            }

        # ground_truth_load 갱신
        if similar_subtask.lower() not in ground_truth_load:
            ground_truth_load[similar_subtask.lower()] = 10

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
        4) critical constraint 업데이트
        5) 파일(bayesian_estimate.json, bayesian_ground_truth.json) 저장
        6) 다시 액션 정제 + Subtask duration 보정
        7) TaskGraph 빌드

        :param task_data: JSON 형태(이미 파싱된 Dict)
        :param enable_decomposition: 서브태스크 분해 여부
        :return: (최종 Subtask 리스트, TaskGraph 객체)
        """
        # 1) bayesian/groundtruth 정보 로드
        bayesian_load = cls._load_json_file(SCENE_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME)
        ground_truth_load = cls._load_json_file(
            SCENE_KNOWLEDGE_PATH / GROUND_TRUTH_FILE_NAME
        )

        # 2) Task 파싱, Object ID/액션 보정
        tasks = Task.parse_instruction(task_data)
        tasks = cls.check_obj_id(scene_file_name, tasks)
        tasks = cls.refine_primitive_actions(tasks)

        # 3) enable_decomposition 옵션 처리
        if enable_decomposition:
            tasks = [t.decompose_subtasks() for t in tasks]

        # 4) critical constraint 처리
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        for st in subtasks:
            for tc in st.temporal_constraints:
                if tc.is_critical:
                    cls._update_critical_constraint(
                        st,
                        tc,
                        bayesian_load,
                        ground_truth_load,
                    )

        # 5) 변경 사항 저장
        cls._save_json_file(
            SCENE_KNOWLEDGE_PATH / "bayesian_estimate.json", bayesian_load
        )
        cls._save_json_file(
            SCENE_KNOWLEDGE_PATH / "bayesian_ground_truth.json", ground_truth_load
        )

        # 6) 액션 정제(재적용) + duration 조정
        tasks = cls.refine_primitive_actions(tasks)
        subtasks = cls.tasks_to_subtasks(tasks, mode="all")
        subtasks = cls.adjust_subtasks_duration(subtasks)

        # 7) TaskGraph 빌드
        task_graph_builder = TaskGraphBuilder()
        task_graph = task_graph_builder.build_graph(tasks)

        return subtasks, task_graph

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

    @staticmethod
    def create_monitoring_subtask(name: str, obj: str = None) -> Subtask:
        """
        MONITORING 액션을 수행하는 Subtask를 생성해 반환한다.
        """
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
