import copy
import heapq
import math
from typing import Dict, List, Optional, Tuple, TypeAlias

from core.dataclass import ActionResult, ActionSimulationLog, SimulationNode
from ithor.utils.math_utils import adjust_if_unreachable
from utils.common import create_module_logger
from utils.config.constants import (
    EPSILON,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    REACHABLE_DISTANCE_THRESHOLD,
    STATIC_ACTION_SET,
)

log = create_module_logger(__name__, module_log=True)

Position: TypeAlias = Tuple[float, float, float]
NavGraph: TypeAlias = Dict[Position, List[Position]]  # 네비게이션 그래프 타입 정의


class ActionHandler:
    def __init__(self, nav_graph: NavGraph):
        """
        ActionHandler를 초기화합니다.

        Args:
            nav_graph: 네비게이션에 사용될 그래프. {position_tuple: [neighbor_position_tuples]} 형식.
        """
        self.nav_graph = nav_graph

    def get_actions_info(
        self, current_node: SimulationNode, actions: list[str]
    ) -> Optional[ActionResult]:
        """
        주어진 액션 시퀀스를 시뮬레이션하고 최종 ActionResult를 반환합니다.
        시뮬레이션을 위해 노드 상태의 복사본을 생성합니다.
        액션 목록이 비어 있거나 시뮬레이션에 실패하면 None을 반환합니다.

        Args:
            current_node: 시뮬레이션을 시작할 현재 노드 상태.
            actions: 실행할 원시 액션 문자열 목록.

        Returns:
            시뮬레이션 성공 시 마지막 액션의 결과(ActionResult), 실패 시 None.
        """
        if not actions:
            log.warning(
                "get_actions_info called with empty actions list. Returning None."
            )
            return None

        action_sim_info = self._simulate_actions(current_node, actions)
        return action_sim_info.results[-1]

    # --------------------------------------------------------------------------
    # 액션 시뮬레이션 핵심 로직 (_simulate_actions 및 헬퍼 메서드)
    # --------------------------------------------------------------------------

    def _simulate_actions(
        self,
        initial_node: SimulationNode,
        primitive_actions: List[str],
    ) -> Optional[ActionSimulationLog]:
        """
        주어진 액션 시퀀스를 내부 모델을 사용하여 순차적으로 시뮬레이션합니다.
        시뮬레이션은 상태의 깊은 복사본을 사용하여 수행됩니다.
        액션 실행 중 실패가 발생하면 시뮬레이션을 중단하고 현재까지의 로그를 반환합니다.

        Args:
            initial_node: 시뮬레이션 시작 상태를 담은 노드.
            primitive_actions: 실행할 원시 액션 문자열 리스트.

        Returns:
            액션 시뮬레이션 로그(ActionSimulationLog). 시뮬레이션 시작 자체가 불가능하거나
            치명적인 오류 발생 시 None을 반환할 수 있습니다. (예: 초기 상태 오류)
        """
        if not initial_node or not initial_node.state:
            log.error(
                "Cannot simulate actions with invalid initial_node or state. Returning None."
            )
            return None

        action_log = ActionSimulationLog()
        # 시뮬레이션을 위해 상태 깊은 복사
        sim_state = copy.deepcopy(initial_node.state)
        current_scene_positions = sim_state.scene_positions
        current_held_object = sim_state.held_object
        new_held_object = None
        current_cumulative_time = 0.0
        for i, action_str in enumerate(primitive_actions):
            log.debug(
                f"--- Simulating action {i+1}/{len(primitive_actions)}: '{action_str}' ---"
            )
            log.debug(
                f"    State before: Time={current_cumulative_time:.2f}, Held={current_held_object}"
            )

            # 액션 파싱
            tokens = action_str.split()
            if not tokens:
                log.warning(f"Empty action string encountered at index {i}. Skipping.")
                continue  # 다음 액션으로

            action_type = tokens[0].upper()
            target_obj_id: Optional[str] = tokens[1] if len(tokens) > 1 else None
            # NAVIGATE_TO의 경우 부분 시간 정보 추가 파싱
            partial_time_str: Optional[str] = (
                tokens[2] if len(tokens) == 3 and action_type == "NAVIGATE_TO" else None
            )

            action_duration = 0.0
            action_success = True

            agent_pos: Optional[Position] = (
                tuple(current_scene_positions.get("agent"))
                if "agent" in current_scene_positions
                else None
            )
            if agent_pos is None:
                raise ValueError("Agent position ('agent') missing in scene_positions.")

            # 액션 타입별 헬퍼 메서드 호출
            if action_type == "NAVIGATE_TO":
                action_duration, action_success, new_agent_pos = (
                    self._simulate_navigate(
                        agent_pos,
                        target_obj_id,
                        partial_time_str,
                        current_scene_positions,
                    )
                )
                if action_success and new_agent_pos is not None:
                    current_scene_positions["agent"] = tuple(new_agent_pos)

            elif action_type == "GRASP":
                action_duration, action_success, new_held_object = self._simulate_grasp(
                    agent_pos,
                    target_obj_id,
                    current_held_object,
                    current_scene_positions,
                )

            elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                action_duration, action_success, new_held_object = self._simulate_place(
                    agent_pos,
                    target_obj_id,
                    current_held_object,
                    current_scene_positions,
                )

            elif action_type in STATIC_ACTION_SET:
                action_duration, action_success = self._simulate_interaction(
                    agent_pos, action_type, target_obj_id, current_scene_positions
                )

            elif action_type == "WAIT":
                action_duration, action_success = self._simulate_wait(target_obj_id)
            elif action_type == "MONITORING":
                action_duration, action_success = self._simulate_monitoring()
            else:
                log.warning(
                    f"Unhandled action type in internal simulation: {action_type}. Assuming default duration and failure."
                )
                action_duration = 0.0
                action_success = False

            # 시뮬레이션 상태 업데이트 (헬퍼 메서드에서 변경된 부분 반영)
            current_held_object = new_held_object

            # 경과 시간 및 누적 시간 업데이트
            current_cumulative_time += action_duration

            log.debug(f"    Action Result: {'SUCCESS' if action_success else 'FAILED'}")
            log.debug(f"    Duration: {action_duration:.2f}")
            log.debug(
                f"    State after : Time={current_cumulative_time:.2f}, Held={current_held_object}"
            )
            log.debug(f"--- End simulation step {i+1} ---")

            action_log.add_result(
                action_full_name=action_str,
                action_type=action_type,
                cumulative_time=current_cumulative_time,
                action_duration=action_duration,
                scene_positions=copy.deepcopy(current_scene_positions),
                held_object=current_held_object,
                success=action_success,
            )

            # 액션 실패 시 시뮬레이션 중단
            if not action_success:
                log.warning(
                    f"Stopping action sequence simulation at index {i} because action '{action_str}' failed."
                )
                break  # for 루프 탈출

        return action_log

    def _check_reachability(
        self,
        agent_pos: Position,
        target_pos: Position,
        action_name: str,
        target_id: Optional[str],
    ) -> bool:
        """주어진 위치에서 타겟 위치가 상호작용 가능한 거리 내에 있는지 확인합니다."""
        dist = math.dist(agent_pos, target_pos)
        if dist > REACHABLE_DISTANCE_THRESHOLD:
            log.warning(
                f"  {action_name} target '{target_id}' might be unreachable "
                f"(Distance: {dist:.2f} > {REACHABLE_DISTANCE_THRESHOLD:.2f}). Action FAILED."
            )
            return False
        return True

    def _simulate_navigate(
        self,
        agent_pos: Position,
        target_obj_id: Optional[str],
        partial_time_str: Optional[str],
        scene_positions: Dict[str, Position],
    ) -> Tuple[float, bool, Optional[Position]]:
        """
        NAVIGATE_TO 액션을 시뮬레이션합니다. 전체 경로 또는 부분 시간을 기반으로
        소요 시간, 성공 여부, 그리고 액션 후 에이전트의 최종 위치를 계산합니다.

        Args:
            agent_pos: 현재 에이전트 위치.
            target_obj_id: 목표 객체 ID.
            partial_time_str: 부분 이동 시간을 나타내는 문자열 (있는 경우).
            scene_positions: 현재 씬의 객체 위치 정보.

        Returns:
            Tuple[float, bool, Optional[Position]]:
            - 소요 시간 (float).
            - 성공 여부 (bool).
            - 액션 후 에이전트의 새로운 위치 (Optional[Position]). 부분 시간 이동 시
              정확한 최종 위치를 알 수 없으면 None일 수 있음.

        Raises:
            ValueError: 목표 객체를 찾을 수 없거나, 부분 시간 문자열이 잘못된 경우.
        """
        duration = 0.0
        success = False
        new_agent_pos: Optional[Position] = None  # 액션 완료 후의 최종 위치

        # 1. 목표 유효성 검사 및 위치 가져오기
        if not target_obj_id or target_obj_id not in scene_positions:
            raise ValueError(
                f"Navigation target '{target_obj_id}' not found in scene positions."
            )
        target_pos = tuple(scene_positions[target_obj_id])

        # 2. 경로 탐색 시도 (partial time 여부와 관계없이 일단 시도)
        navigate_path: Optional[List[Position]] = None

        log.debug(
            f"  Finding path from {agent_pos} to {target_pos} for '{target_obj_id}'"
        )
        navigate_path = self._find_shortest_path(agent_pos, target_pos)

        # 3. 부분 시간 이동 처리
        if partial_time_str:
            log.debug(f"  Processing NAVIGATE_TO with partial time: {partial_time_str}")
            partial_duration = float(partial_time_str)
            duration = partial_duration  # 액션 소요 시간은 주어진 부분 시간
            success = True  # 부분 시간 이동은 일단 성공으로 간주

            # 이동할 스텝 수 계산 (올림/내림 정책 확인 필요, 여기선 내림 사용)
            steps_can_take = int(math.floor(partial_duration / NAV_STEP_DURATION))
            # 경로 길이 내에서만 이동 가능
            actual_steps = min(steps_can_take, len(navigate_path))
            new_agent_pos = navigate_path[actual_steps - 1]

        # 4. 전체 경로 이동 처리
        else:
            log.debug(f"  Processing NAVIGATE_TO for full path.")
            path_steps = len(navigate_path)  # 실제 이동 스텝 수
            duration = path_steps * NAV_STEP_DURATION
            # 경로의 마지막 위치가 새로운 에이전트 위치 (경로가 비었으면 현재 위치)
            new_agent_pos = navigate_path[-1] if navigate_path else agent_pos
            success = True
            log.debug(
                f"    Path found with {path_steps} steps. Duration: {duration:.2f}s. Final pos: {new_agent_pos}"
            )

        # 5. 결과 반환
        return duration, success, new_agent_pos

    def _simulate_grasp(
        self,
        agent_pos: Position,
        target_obj_id: Optional[str],
        current_held_object: Optional[str],
        scene_positions: Dict[str, Position],
    ) -> Tuple[float, bool, Optional[str]]:
        """GRASP 액션을 시뮬레이션합니다."""
        duration = 0.0
        success = False
        new_held_object = current_held_object

        if not target_obj_id or target_obj_id not in scene_positions:
            raise ValueError(
                f"Grasp target '{target_obj_id}' not found in scene positions."
            )
        if current_held_object:
            log.warning(
                f"Agent already holding '{current_held_object}'. Cannot grasp '{target_obj_id}'. Action FAILED."
            )
            success = False
        else:
            target_actual_pos = tuple(scene_positions[target_obj_id])
            if self._check_reachability(
                agent_pos, target_actual_pos, "Grasp", target_obj_id
            ):
                new_held_object = target_obj_id
                duration = PRIMITIVE_ACTION_DURATION
                success = True
                log.debug(f"  Grasped '{target_obj_id}'.")
            else:
                success = False  # Unreachable

        return duration, success, new_held_object

    def _simulate_place(
        self,
        agent_pos: Position,
        receptacle_id: Optional[str],
        current_held_object: Optional[str],
        scene_positions: Dict[str, Position],
    ) -> Tuple[float, bool, Optional[str]]:
        """PLACE_INSIDE 또는 PLACE_ON_TOP 액션을 시뮬레이션합니다."""
        duration = 0.0
        success = False
        new_held_object = current_held_object

        if not current_held_object:
            log.warning(f"Agent not holding anything. Cannot place. Action FAILED.")
            success = False
        elif not receptacle_id or receptacle_id not in scene_positions:
            raise ValueError(
                f"Place target receptacle '{receptacle_id}' not found in scene positions."
            )
        else:
            receptacle_pos = tuple(scene_positions[receptacle_id])
            if self._check_reachability(
                agent_pos, receptacle_pos, "Place", receptacle_id
            ):
                log.debug(f"  Placing '{current_held_object}' on/in '{receptacle_id}'.")
                # 객체 상태 업데이트 (시뮬레이션 모델에 따라 달라짐)
                # 여기서는 단순히 손을 비우는 것으로 처리
                if current_held_object in scene_positions:
                    scene_positions[current_held_object] = scene_positions[
                        receptacle_id
                    ]
                new_held_object = None
                duration = PRIMITIVE_ACTION_DURATION
                success = True
            else:
                success = False  # Unreachable

        return duration, success, new_held_object

    def _simulate_interaction(
        self,
        agent_pos: Position,
        action_type: str,
        target_obj_id: Optional[str],
        scene_positions: Dict[str, Position],
    ) -> Tuple[float, bool]:
        """OPEN, CLOSE, TOGGLE_ON/OFF, SLICE 등 일반적인 상호작용 액션을 시뮬레이션합니다."""
        duration = 0.0
        success = False

        if not target_obj_id or target_obj_id not in scene_positions:
            raise ValueError(
                f"{action_type} target '{target_obj_id}' not found in scene positions."
            )

        target_actual_pos = tuple(scene_positions[target_obj_id])
        if self._check_reachability(
            agent_pos, target_actual_pos, action_type, target_obj_id
        ):
            duration = PRIMITIVE_ACTION_DURATION
            success = True
            log.debug(f"  Simulated {action_type} on '{target_obj_id}'.")
        else:
            success = False  # Unreachable

        return duration, success

    def _simulate_wait(self, wait_time_str: Optional[str]) -> Tuple[float, bool]:
        """WAIT 액션을 시뮬레이션합니다."""
        duration = 0.0
        success = False
        if wait_time_str is None:
            raise ValueError("WAIT action requires a duration argument.")
        try:
            wait_time = float(wait_time_str)
            if wait_time < 0:
                log.warning(f"Invalid negative wait time: {wait_time}. Using 0.")
                duration = 0.0
            else:
                duration = wait_time
            success = True
            log.debug(f"  Simulated WAIT for {duration:.2f}s.")
        except (TypeError, ValueError):
            raise ValueError(f"Invalid WAIT duration: {wait_time_str}")

        return duration, success

    def _simulate_monitoring(self) -> Tuple[float, bool]:
        """MONITORING 액션을 시뮬레이션합니다."""
        duration = MONITORING_DURATION
        success = True
        log.debug(f"  Simulated MONITORING for {duration:.2f}s.")
        return duration, success

    def _find_shortest_path(
        self, start_pos: Tuple[float, float, float], end_pos: Tuple[float, float, float]
    ) -> list[Tuple[float, float, float]]:
        start_pos = adjust_if_unreachable(self.nav_graph, start_pos)
        end_pos = adjust_if_unreachable(self.nav_graph, end_pos)
        if start_pos == end_pos:
            return []

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

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: List[str],
        cutoff_time: float,
    ) -> Tuple[ActionSimulationLog, ActionSimulationLog]:
        """
        주어진 액션 시퀀스를 지정된 cutoff_time 기준으로 두 부분으로 나눕니다.
        내부 시뮬레이션(_simulate_actions)을 한 번 사용하여 각 액션의 완료 시간과 상태를 계산하고,
        cutoff_time을 초과하는 첫 번째 액션을 기준으로 분할합니다.
        만약 분할 지점에서 객체를 들고 있다면(GRASP 이후), 이후 첫 번째 PLACE 액션까지를
        첫 번째 부분(pre-cutoff)에 포함하도록 분할 지점을 조정합니다.

        Args:
            current_node: 분할을 시작할 기준 노드.
            primitive_actions: 분할 대상 액션 시퀀스.
            cutoff_time: 분할 기준 시간 (current_node.state.current_time 기준 상대 시간).

        Returns:
            (pre-cutoff ActionSimulationLog, post-cutoff ActionSimulationLog) 튜플.
            각 로그는 해당 구간의 액션 결과 리스트를 포함합니다. 구간에 액션이 없으면 빈 로그가 반환됩니다.
        """
        log.debug(
            f"Attempting to split actions at relative cutoff time: {cutoff_time:.2f} "
            f"(Node time: {current_node.state.current_time:.2f})"
        )
        if cutoff_time < 0:
            log.warning(f"Relative cutoff time {cutoff_time:.2f} is negative. Using 0.")
            cutoff_time = 0.0

        absolute_cutoff_time = current_node.state.current_time + cutoff_time

        # 1. 전체 시퀀스 시뮬레이션 (단 한번)
        full_simulation_log = self._simulate_actions(current_node, primitive_actions)

        pre_log = ActionSimulationLog()
        post_log = ActionSimulationLog()

        # 시뮬레이션 실패 또는 결과 없음 처리
        if not full_simulation_log or not full_simulation_log.results:
            log.error(
                "Full internal simulation failed or produced no results. Returning empty logs."
            )
            return pre_log, post_log  # 빈 로그 반환

        # 2. 초기 분할 지점 결정
        split_index = -1  # pre-cutoff 부분의 마지막 액션 인덱스
        for i, result in enumerate(full_simulation_log.results):
            # 현재 액션 완료 시간 <= 절대 cutoff 시간 인 마지막 액션 찾기
            if result.cumulative_time <= absolute_cutoff_time + EPSILON:
                split_index = i
            else:
                # 이 액션부터 post-cutoff
                break

        log.debug(f"Initial split index determined: {split_index}")

        # 3. GRASP / PLACE 제약 조건 확인 및 분할 지점 조정
        # split_index가 유효하고 (-1이 아니고), 해당 액션이 성공했으며, 객체를 들고 있는 경우
        if (
            0 <= split_index < len(full_simulation_log.results)
            and full_simulation_log.results[split_index].held_object is not None
        ):
            held_object_at_split = full_simulation_log.results[split_index].held_object
            log.debug(
                f"Object '{held_object_at_split}' is held at the initial split point (index {split_index}). Checking for subsequent PLACE action."
            )

            # 분할 지점 이후의 액션들을 확인하여 첫 번째 PLACE 액션 찾기
            found_place = False
            for j, next_result in enumerate(
                full_simulation_log.results[split_index + 1 :]
            ):
                if next_result.action_type.startswith("PLACE_"):
                    # PLACE 액션을 찾으면, 이 액션까지 pre-cutoff에 포함하도록 split_index 조정
                    adjusted_split_index = split_index + 1 + j
                    log.info(
                        f"Found subsequent PLACE action '{next_result.action_full_name}' at index {adjusted_split_index}. "
                        f"Adjusting split index from {split_index} to {adjusted_split_index} to keep GRASP/PLACE together."
                    )
                    split_index = adjusted_split_index
                    found_place = True
                    break  # 첫 번째 PLACE 액션만 찾으면 됨

            if not found_place:
                log.warning(
                    f"Object '{held_object_at_split}' was held at split index {split_index}, but no subsequent PLACE action was found in the remaining sequence. Split will occur after GRASP."
                )
        elif full_simulation_log.results[split_index].held_object is None:
            log.debug(
                f"No object held or action failed at split index {split_index}. No GRASP/PLACE adjustment needed."
            )
        else:
            log.debug(
                "Split index is -1 (all actions are post-cutoff) or invalid. No adjustment needed."
            )

        # 4. 초기 로그 생성 (조정된 split_index 기준)
        pre_log.results = full_simulation_log.results[: split_index + 1]
        post_log.results = full_simulation_log.results[split_index + 1 :]

        log.debug(
            f"Final split index: {split_index}. "
            f"Pre-cutoff log contains {len(pre_log.results)} results. "
            f"Post-cutoff log contains {len(post_log.results)} results."
        )

        # 5. 결과 반환
        return pre_log, post_log
