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

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: list[str],
        cutoff_time: float,
    ) -> tuple[list[str], list[str], float, float]:
        """
        1) time-based 분할 -> (early_actions, remain_actions)
        2) 사후 보정: early에 GRASP한 오브젝트가 remain에서 Place되어야 하면 가져옴
        3) 두 최종 리스트를 각각 재시뮬레이션하여 total duration 계산
        4) (early_actions, remain_actions, early_duration, remain_duration) 반환
        """

        # (1) 전체 시퀀스 시뮬레이션
        full_log = self.simulate_actions(current_node, primitive_actions)

        early_actions: list[str] = []
        remain_actions: list[str] = []

        # time-based 분할
        for result in full_log.results:
            if result.time_used <= cutoff_time:
                early_actions.append(result.action_full_name)
            else:
                remain_actions.append(result.action_full_name)

        # (2) 사후 보정: early에서 pick된 오브젝트가 place 안 된 경우 → remain에서 place 가져오기
        picked_objs_early = []
        placed_objs_early = set()
        for ea in early_actions:
            ea_tokens = ea.split()
            if not ea_tokens:
                continue
            if ea_tokens[0].upper() == "GRASP" and len(ea_tokens) >= 2:
                picked_objs_early.append(ea_tokens[1])
            elif (
                ea_tokens[0].upper() in ["PLACE_INSIDE", "PLACE_ON_TOP"]
                and len(ea_tokens) >= 2
            ):
                placed_objs_early.add(ea_tokens[1])

        # unplaced_objs = pick했지만 place되지 않은 오브젝트 목록
        unplaced_objs = [
            obj for obj in picked_objs_early if obj not in placed_objs_early
        ]

        # remain에서 Place를 찾으면, 해당 직전 Navigate도 함께 early로 옮긴다 (예시)
        if unplaced_objs:
            i = 0
            while i < len(remain_actions):
                ra = remain_actions[i]
                r_tokens = ra.split()
                if len(r_tokens) < 2:
                    i += 1
                    continue
                base_action = r_tokens[0].upper()
                obj_id = r_tokens[1]

                if (
                    base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"]
                    and obj_id in unplaced_objs
                ):
                    # 직전 navigate까지 옮기기
                    if i - 1 >= 0:
                        prev_act = remain_actions[i - 1]
                        p_tokens = prev_act.split()
                        if p_tokens and p_tokens[0].upper() == "NAVIGATE_TO":
                            early_actions.append(prev_act)
                            remain_actions.pop(i - 1)
                            i -= 1

                    early_actions.append(ra)
                    remain_actions.pop(i)

                    # 이제 obj_id는 place 완료
                    unplaced_objs.remove(obj_id)
                    continue
                i += 1

        # (3) 재시뮬레이션으로 각각의 total_duration 계산
        early_duration = self._simulate_actions_for_duration(
            current_node, early_actions
        )
        remain_duration = self._simulate_actions_for_duration(
            current_node, remain_actions
        )

        # (4) 반환
        return early_actions, remain_actions, early_duration, remain_duration

    def _simulate_actions_for_duration(
        self, current_node: SimulationNode, actions: list[str]
    ) -> float:
        """
        (단순 버전) 주어진 액션 시퀀스를
        '초기 상태'(current_node)에서 시뮬레이션 → 최종 누적 시간을 반환
        """
        if not actions:
            return 0.0

        # node 복사
        sim_node = copy.deepcopy(current_node)
        log_info = self.simulate_actions(sim_node, actions)
        if not log_info.results:
            return 0.0
        return log_info.results[-1].time_used

    def _find_shortest_path(
        self, start_pos: Tuple[float, float, float], end_pos: Tuple[float, float, float]
    ) -> list[Tuple[float, float, float]]:
        start_pos = adjust_if_unreachable(self.nav_graph, start_pos)
        end_pos = adjust_if_unreachable(self.nav_graph, end_pos)
        if start_pos == end_pos:
            return [start_pos]

        def direction(a, b):
            return (b[0] - a[0], b[2] - a[2])

        pq = []
        heapq.heappush(pq, (0, start_pos, None, [start_pos]))
        visited = {}

        while pq:
            turn_cnt, cur_pos, cur_dir, path = heapq.heappop(pq)
            if cur_pos == end_pos:
                return path
            if cur_pos in visited and visited[cur_pos] <= turn_cnt:
                continue
            visited[cur_pos] = turn_cnt
            for nxt in self.nav_graph.get(cur_pos, []):
                if nxt in path:
                    continue
                new_dir = direction(cur_pos, nxt)
                nxt_turn = (
                    turn_cnt
                    if (cur_dir is None or new_dir == cur_dir)
                    else (turn_cnt + 1)
                )
                new_path = path + [nxt]
                heapq.heappush(pq, (nxt_turn, nxt, new_dir, new_path))

        raise ValueError(f"No path found from {start_pos} to {end_pos}.")
