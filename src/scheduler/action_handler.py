import copy
import heapq
import math
from typing import List, Optional, Tuple

from ithor.utils.math_utils import adjust_if_unreachable
from src.core.dataclass import ActionResult, ActionSimulationLog, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config.constants import (
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)

log = create_module_logger(__name__, module_log=True)


class ActionHandler:
    def __init__(self, nav_graph):
        self.nav_graph = nav_graph

    def get_actions_info(
        self, current_node: SimulationNode, actions: list[str]
    ) -> ActionResult:
        """
        주어진 액션 시퀀스를 시뮬레이션해 마지막 액션에 대하여 누적 시간, scene 상태를 반환
        """
        if not actions:
            return None

        sim_node = copy.deepcopy(current_node)
        log_info = self._simulate_actions(sim_node, actions)
        if not log_info.results:
            return None
        return log_info.results[-1]

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: list[str],
        cutoff_time: float,
    ) -> tuple[Optional[ActionSimulationLog], Optional[ActionSimulationLog]]:
        """
        Splits a subtask's actions based on a cutoff time.
        [수정됨] Handles potential GRASP/PLACE pairs spanning the cutoff more robustly.

        1) Simulate the full sequence to get timing info.
        2) Perform initial split based on cutoff_time.
        3. Check for GRASP actions in the pre-cutoff part whose corresponding PLACE
           is in the post-cutoff part.
        4. If such pairs exist, move actions from post-cutoff to pre-cutoff up to
           the *last* required PLACE action.
        5) Re-simulate the final pre- and post-cutoff action lists.
        6) Return the simulation logs for both parts.
        """
        if not primitive_actions:
            return None, None

        # (1) Simulate the full sequence to get action timings
        full_log = self._simulate_actions(current_node, primitive_actions)
        if not full_log or not full_log.results:
            log.warning("Full simulation failed during split. Cannot proceed.")
            # Decide how to handle this - maybe return None, None or raise error
            return None, None  # Or potentially return full_log, None?

        pre_cutoff_actions: list[str] = []
        post_cutoff_actions: list[str] = []
        pre_cutoff_indices: list[int] = []
        post_cutoff_indices: list[int] = []

        # (2) Initial time-based split
        for i, result in enumerate(full_log.results):
            # If the action *ends* at or before the cutoff
            if result.time_used <= cutoff_time + 1e-6:  # Add tolerance
                pre_cutoff_actions.append(result.action_full_name)
                pre_cutoff_indices.append(i)
            else:
                post_cutoff_actions.append(result.action_full_name)
                post_cutoff_indices.append(i)

        log.debug(
            f"Initial split: pre={pre_cutoff_actions}, post={post_cutoff_actions}"
        )

        # (3) Check for GRASP/PLACE spanning the cutoff
        # Simulate pre-cutoff to find held object at the cutoff point
        temp_pre_log = self._simulate_actions(current_node, pre_cutoff_actions)
        object_held_at_cutoff = (
            temp_pre_log.results[-1].held_object
            if temp_pre_log and temp_pre_log.results
            else None
        )

        if object_held_at_cutoff:
            log.debug(
                f"Object '{object_held_at_cutoff}' is held at cutoff. Checking for PLACE in post-actions."
            )
            required_place_idx = -1
            # Find the index of the corresponding PLACE action in the *original* sequence
            for post_idx in post_cutoff_indices:
                action = primitive_actions[post_idx]
                tokens = action.split()
                action_type = tokens[0].upper() if tokens else ""
                # Check if this action places the object held at cutoff
                if action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"] and len(tokens) >= 2:
                    # Simplification: Assume the next PLACE is for the held object.
                    # A more robust check would involve tracking which object is placed.
                    # For now, we assume the first PLACE found is the one we need.
                    log.debug(
                        f"Found PLACE action '{action}' at original index {post_idx} for held object '{object_held_at_cutoff}'."
                    )
                    required_place_idx = post_idx
                    break  # Found the first relevant PLACE

            # (4) Move actions up to the required PLACE if found
            if required_place_idx != -1:
                log.debug(
                    f"Moving actions up to index {required_place_idx} from post to pre."
                )
                actions_to_move = []
                remaining_post_actions = []
                original_post_indices_to_move = []

                for i, post_idx in enumerate(post_cutoff_indices):
                    if post_idx <= required_place_idx:
                        actions_to_move.append(post_cutoff_actions[i])
                        original_post_indices_to_move.append(post_idx)
                    else:
                        remaining_post_actions.append(post_cutoff_actions[i])

                if actions_to_move:
                    pre_cutoff_actions.extend(actions_to_move)
                    post_cutoff_actions = remaining_post_actions  # Update post actions
                    # Update indices if needed, though less critical now
                    pre_cutoff_indices.extend(original_post_indices_to_move)
                    post_cutoff_indices = [
                        idx for idx in post_cutoff_indices if idx > required_place_idx
                    ]

                    log.debug(
                        f"After move: pre={pre_cutoff_actions}, post={post_cutoff_actions}"
                    )

        # (5) Re-simulate final action lists
        final_pre_log = (
            self._simulate_actions(current_node, pre_cutoff_actions)
            if pre_cutoff_actions
            else None
        )
        final_post_log = (
            self._simulate_actions(current_node, post_cutoff_actions)
            if post_cutoff_actions
            else None
        )

        # Handle cases where simulation might fail after splitting
        if pre_cutoff_actions and not final_pre_log:
            log.error(
                f"Re-simulation failed for final pre_cutoff_actions: {pre_cutoff_actions}"
            )
            # Decide recovery strategy: maybe return original split? or raise error?
        if post_cutoff_actions and not final_post_log:
            log.error(
                f"Re-simulation failed for final post_cutoff_actions: {post_cutoff_actions}"
            )

        # (6) Return results
        return final_pre_log, final_post_log

    def _simulate_actions(
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
                if target_obj_id not in scene_positions:
                    log.error(
                        f"Navigation target {target_obj_id} not in scene_positions."
                    )
                    raise ValueError(
                        f"Navigation target {target_obj_id} not in scene_positions."
                    )

                start_node_pos = scene_positions["agent"]
                end_node_pos = scene_positions[target_obj_id]
                navigate_path = self._find_shortest_path(start_node_pos, end_node_pos)

                if (
                    not navigate_path
                ):  # 경로가 없는 경우 (혹은 find_shortest_path가 None 반환 시)
                    log.warning(
                        f"No path found for NAVIGATE_TO {target_obj_id}. Duration=0."
                    )
                    action_duration = 0.0
                    # 위치는 변경되지 않음
                elif len(navigate_path) == 1:  # 시작과 끝이 같은 경우
                    action_duration = 0.0
                    # 위치는 변경되지 않음 (이미 navigate_path[0] == start_node_pos)
                elif partial_time_str is None:  # 전체 경로 이동
                    # [수정됨] 경로 길이는 (노드 수 - 1) * 스텝 시간
                    action_duration = (len(navigate_path) - 1) * NAV_STEP_DURATION
                    scene_positions["agent"] = navigate_path[-1]  # 최종 위치로 업데이트
                else:  # 부분 시간 이동
                    try:
                        nav_time = float(partial_time_str)
                        if nav_time < 0:
                            nav_time = 0  # 음수 시간 방지

                        # 이동할 최대 스텝 수 계산 (경로 길이 - 1 이 최대 이동 가능 횟수)
                        max_steps = len(navigate_path) - 1
                        # 요청된 시간 내 이동 가능한 스텝 수
                        requested_steps = int(math.floor(nav_time / NAV_STEP_DURATION))
                        # 실제 이동할 스텝 수 (0과 최대 스텝 수 사이로 제한)
                        steps = max(0, min(requested_steps, max_steps))

                        # [수정됨] 실제 이동한 스텝 수에 따른 시간으로 action_duration 설정
                        action_duration = steps * NAV_STEP_DURATION
                        # [수정됨] 유효한 스텝인 경우에만 위치 업데이트
                        if steps >= 0 and steps < len(navigate_path):
                            scene_positions["agent"] = navigate_path[steps]
                        else:  # 예상치 못한 경우 (steps 계산 오류 등)
                            log.error(
                                f"Invalid step index {steps} calculated for partial navigation. Position not updated."
                            )

                    except ValueError:
                        log.error(
                            f"Invalid partial time '{partial_time_str}' for NAVIGATE_TO. Assuming full navigation."
                        )
                        # Fallback to full navigation? Or treat as error? Let's do full nav for now.
                        action_duration = (len(navigate_path) - 1) * NAV_STEP_DURATION
                        scene_positions["agent"] = navigate_path[-1]

            elif action_type == "GRASP":
                if held_object is not None:
                    log.warning(f"Object {held_object} already in hand.")
                    raise ValueError(f"Object {held_object} already in hand.")
                held_object = target_obj_id
                action_duration = PRIMITIVE_ACTION_DURATION

            elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                if held_object is None:
                    log.warning("No object in hand to place.")
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
