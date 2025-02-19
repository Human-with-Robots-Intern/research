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
    ) -> Tuple[Subtask, Subtask]:
        """
        1) simulate_actions()로 모든 액션에 대한 time_used를 구한다.
        2) time_used <= cutoff_time → early, 그 외 → remain
        3) 사후보정:
        - early에 GRASP <obj>가 있는데, place가 안 끝난 경우
            → remain에서 'NAVIGATE_TO ~' (장소) + 'PLACE_XXX <obj>' 등을
            순서대로 가져와 early에 붙인다.
        - 최종적으로 early 구간의 끝에서 held_object가 없도록 보장
        """
        # (1) 전체 액션 시뮬레이션
        action_log_info = self.simulate_actions(current_node, primitive_actions)

        # (2) time-based 분할
        early_actions: list[str] = []
        remain_actions: list[str] = []

        for result in action_log_info.results:
            if result.time_used <= cutoff_time:
                early_actions.append(result.action_full_name)
            else:
                remain_actions.append(result.action_full_name)

        # (3) 사후 보정
        #  3-1) early에서 grasp된 오브젝트를 찾는다
        grasped_objs_in_early = []
        placed_objs_in_early = set()
        for ea in early_actions:
            tokens = ea.split()
            if not tokens:
                continue
            base_action = tokens[0].upper()
            if base_action == "GRASP" and len(tokens) >= 2:
                obj_id = tokens[1]
                grasped_objs_in_early.append(obj_id)
            elif base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"] and len(tokens) >= 2:
                placed_objs_in_early.add(tokens[1])  # 이미 place 된 오브젝트

        # 결국 early에서 grasp한 오브젝트 중 place가 안 된 것만 다시 확인
        # (Pick 했는데 아직 Place 안 된 오브젝트 목록)
        unplaced_objs = [
            obj for obj in grasped_objs_in_early if obj not in placed_objs_in_early
        ]

        if not unplaced_objs:
            # 만약 전부 early에서 pick~place가 끝났다면 추가 보정 없이 종료
            return early_actions, remain_actions

        #  3-2) remain_actions에서, 해당 오브젝트들에 대한 Navigate + Place를 순서대로 찾아서 early로 이동
        #       (단순히 "PLACE_XXX <obj>" 직전의 "NAVIGATE_TO" 1개만 가져오는 로직 예시)
        i = 0
        while i < len(remain_actions):
            ra = remain_actions[i]
            tokens = ra.split()
            if len(tokens) < 2:
                i += 1
                continue

            base_action = tokens[0].upper()
            obj_id = tokens[1]

            # (A) 만약 PLACE_XXX이고, obj_id가 unplaced_objs에 있으면,
            #     → 이 Place 액션과 바로 직전 Navigate를 early로 옮긴다.
            if (
                base_action in ["PLACE_INSIDE", "PLACE_ON_TOP"]
                and obj_id in unplaced_objs
            ):
                # 1) Place 직전 Navigate가 있다면, 그것도 함께 이동 (OPTIONAL)
                #    즉, (i-1)에 "NAVIGATE_TO ~"가 있으면 같이 옮긴다.
                if i - 1 >= 0:
                    prev_action = remain_actions[i - 1]
                    prev_tokens = prev_action.split()
                    if prev_tokens and prev_tokens[0].upper() == "NAVIGATE_TO":
                        # early로 이동
                        early_actions.append(prev_action)
                        remain_actions.pop(i - 1)
                        # pop 했으니 인덱스 조정
                        i -= 1

                # 2) Place 액션도 early로 옮긴다
                early_actions.append(ra)
                remain_actions.pop(i)

                # 이제 obj_id는 place가 완료되었으므로, unplaced_objs에서 제거
                if obj_id in unplaced_objs:
                    unplaced_objs.remove(obj_id)
                # i는 remain_actions.pop(i)로 인해 앞으로 당겨졌으니, 그대로
                continue

            i += 1

        # 이 시점에서, unplaced_objs가 비어 있지 않다면
        # "remain에 해당 오브젝트의 place가 아예 없는" 경우이거나,
        # "place를 위해 navigate가 다른 여러 개"인 복잡한 상황이 될 수 있음.
        # 아래처럼 경고를 찍거나, 추가 로직을 넣을 수 있음.
        for leftover_obj in unplaced_objs:
            log.warning(
                f"Object '{leftover_obj}' was grasped in early but not placed in remain."
            )

        # 최종적으로 early 구간의 끝에서, pick~place가 완료되지 않은 오브젝트가 있어도
        # "정책에 따라" 어떻게 처리할지 결정:
        # - 여기서는 단순히 경고만 남김

        return early_actions, remain_actions

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
