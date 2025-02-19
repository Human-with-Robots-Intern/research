import copy
import heapq
import math
from typing import List, Optional, Tuple

from core.task import Duration, Execution, Subtask
from ithor.utils.math_utils import adjust_if_unreachable
from scheduler.dataclass import ActionSimulationLog, SimulationNode
from utils.constants import (
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)
from utils.util import create_module_logger

log = create_module_logger(__name__, is_file_handler=True)


class ActionHandler:
    def __init__(self, nav_graph):
        self.nav_graph = nav_graph

    def simulate_actions(
        self,
        current_node: SimulationNode,
        primitive_actions: List[str],
    ) -> ActionSimulationLog:
        """
        1) 액션들을 시뮬레이션해 누적 시간(time_used)과 액션별 상태를 기록
        2) ActionSimulationLog로 반환
        """
        action_log_info = ActionSimulationLog()

        # 초기 상태 복사
        scene_positions = copy.deepcopy(current_node.state.scene_positions)
        held_object = copy.deepcopy(current_node.state.held_object)
        time_used = 0.0

        for prim_action in primitive_actions:
            tokens = prim_action.split()
            if not tokens:
                continue

            action_type = tokens[0].upper()
            target_obj_id = tokens[1] if len(tokens) > 1 else None
            partial_time_str = tokens[2] if len(tokens) > 2 else None

            # 예외: WAIT 이외 액션에서, scene_positions에 없는 오브젝트를 타겟으로 지목
            if (
                target_obj_id
                and target_obj_id not in scene_positions
                and action_type != "WAIT"
            ):
                log.error(f"Object {target_obj_id} not in scene_positions.")
                raise ValueError(f"Object {target_obj_id} not in scene_positions.")

            # 액션별 소요시간 계산
            if action_type == "NAVIGATE_TO":
                navigate_path = self._find_shortest_path(
                    scene_positions["agent"], scene_positions[target_obj_id]
                )
                if partial_time_str is None:
                    action_duration = len(navigate_path) * NAV_STEP_DURATION
                    if navigate_path:
                        scene_positions["agent"] = navigate_path[-1]
                else:
                    nav_time = float(partial_time_str)
                    steps = int(math.floor(nav_time / NAV_STEP_DURATION))
                    steps = max(0, min(steps, len(navigate_path) - 1))
                    action_duration = nav_time
                    if navigate_path:
                        scene_positions["agent"] = navigate_path[steps]

            elif action_type == "GRASP":
                if held_object is not None:
                    raise ValueError(
                        f"Already holding {held_object}, cannot grasp {target_obj_id}."
                    )
                held_object = target_obj_id
                action_duration = PRIMITIVE_ACTION_DURATION

            elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                if held_object is None:
                    raise ValueError("No object in hand to place.")
                # place 동작
                scene_positions[held_object] = scene_positions[target_obj_id]
                held_object = None
                action_duration = PRIMITIVE_ACTION_DURATION

            elif action_type == "MONITORING":
                action_duration = MONITORING_DURATION

            elif action_type == "WAIT":
                action_duration = float(target_obj_id)  # 예: WAIT 3.0

            elif action_type in PRIMITIVE_ACTION_SET:
                action_duration = PRIMITIVE_ACTION_DURATION

            else:
                log.error(f"Unknown action name: {action_type}")
                raise ValueError(f"Unknown action name: {action_type}")

            # 누적 시간 증가
            time_used += action_duration

            # 로그에 기록
            action_log_info.add_result(
                action_full_name=prim_action,
                action_type=action_type,
                time_used=time_used,
                action_duration=action_duration,
                scene_positions=copy.deepcopy(scene_positions),
                held_object=held_object,
            )

        return action_log_info

    def _find_shortest_path(
        self, start_pos: Tuple[float, float, float], end_pos: Tuple[float, float, float]
    ) -> List[Tuple[float, float, float]]:
        """
        nav_graph를 이용해 start_pos부터 end_pos까지의 최단 경로(노드 리스트) 탐색
        """
        # (사용자 정의) 예시 로직
        if start_pos == end_pos:
            return [start_pos]
        # ... 생략 ...
        return [start_pos, end_pos]  # 간단 예시

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: List[str],
        cutoff_time: float,
    ) -> Tuple[List[str], List[str]]:
        """
        B 방식 분할:
          1) time-based로 early/remain 나눈 뒤,
          2) early에 GRASP된 오브젝트의 PLACE 액션이 remain에 있다면 early로 가져옴

        Returns:
            (Subtask(early_actions), Subtask(remain_actions))
        """
        # 1) 전체 액션 시뮬레이션
        action_log_info = self.simulate_actions(current_node, primitive_actions)

        early_actions: List[str] = []
        remain_actions: List[str] = []

        # 2) time-based 분할
        for result in action_log_info.results:
            # result.time_used: 이 액션이 끝난 시점의 누적 시간
            if result.time_used <= cutoff_time:
                early_actions.append(result.action_full_name)
            else:
                remain_actions.append(result.action_full_name)

        # 3) 사후 보정: early에 GRASP가 있다면, remain에서 해당 오브젝트의 PLACE를 강제로 이동
        picked_objs_in_early: List[str] = []
        for ea in early_actions:
            e_tokens = ea.split()
            if e_tokens[0].upper() == "GRASP" and len(e_tokens) > 1:
                picked_objs_in_early.append(e_tokens[1])  # 오브젝트 ID

        # remain에서 place를 찾아 early로 이동 (cutoff time은 무시)
        for obj_id in picked_objs_in_early:
            place_idx = None
            for i, ra in enumerate(remain_actions):
                r_tokens = ra.split()
                if len(r_tokens) < 2:
                    continue
                r_base = r_tokens[0].upper()
                if r_base in ["PLACE_INSIDE", "PLACE_ON_TOP"] and r_tokens[1] == obj_id:
                    place_idx = i
                    break
            if place_idx is not None:
                # 해당 place 액션을 early로 옮긴다
                place_action = remain_actions.pop(place_idx)
                early_actions.append(place_action)
                # 만약 place 이전의 Navigate도 함께 옮기고 싶다면,
                #  navigate를 찾는 추가 로직을 넣어도 됨

        return early_subtask, remain_subtask
