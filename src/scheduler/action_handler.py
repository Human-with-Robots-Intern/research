import copy
import heapq
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, TypeAlias

from ithor.utils.math_utils import adjust_if_unreachable
from src.core.dataclass import ActionResult, ActionSimulationLog, SimulationNode, SchedulerState
from src.utils.common import create_module_logger
from src.utils.config import EPSILON
from src.utils.config.constants import (
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    REACHABLE_DISTANCE_THRESHOLD,
)

log = logging.getLogger(__name__)

# 타입 앨리어스 정의
Position: TypeAlias = Tuple[float, float, float]
NavGraph: TypeAlias = Dict[Position, List[Position]]  # 네비게이션 그래프 타입 정의


class ActionHandler:
    """
    액션 시퀀스를 내부 모델을 사용하여 시뮬레이션하고,
    결과 상태 및 소요 시간을 계산하는 클래스.
    네비게이션 경로 탐색 및 액션 분할 기능도 제공합니다.
    """

    def __init__(self, nav_graph: NavGraph):
        """
        ActionHandler를 초기화합니다.

        Args:
            nav_graph: 네비게이션에 사용될 그래프. {position_tuple: [neighbor_position_tuples]} 형식.
        """
        if not isinstance(nav_graph, dict):
            log.warning(f"Invalid nav_graph type: {type(nav_graph)}. Expected dict.")
            # 필요시 기본 빈 그래프 할당 또는 에러 발생
            # self.nav_graph = {}
            # raise TypeError("nav_graph must be a dictionary")
        self.nav_graph: NavGraph = nav_graph
        log.debug(
            f"ActionHandler initialized with nav_graph containing {len(nav_graph)} nodes."
        )

    def get_actions_info(
        self, current_node: SimulationNode, actions: List[str]
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

        try:
            # 내부 시뮬레이션 실행
            simulation_log = self._simulate_actions(current_node, actions)

            # 시뮬레이션 결과 확인
            if not simulation_log or not simulation_log.results:
                # 내부 시뮬레이션 함수에서 이미 오류 로깅됨
                log.error(
                    f"Action simulation failed or returned empty results for actions: {actions}. Returning None from get_actions_info."
                )
                return None

            # 성공한 경우, 마지막 액션의 결과 반환
            return simulation_log.results[-1]

        except Exception as e:
            # _simulate_actions 내부에서 처리되지 않은 예외 처리
            log.error(
                f"Unexpected error in get_actions_info while simulating actions {actions}: {e}. Returning None.",
                exc_info=True,  # 상세 오류 추적 정보 포함
            )
            return None

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

        time_elapsed = 0.0  # 이번 시뮬레이션 시퀀스에서 경과한 시간

        for i, action_str in enumerate(primitive_actions):
            log.debug(
                f"--- Simulating action {i+1}/{len(primitive_actions)}: '{action_str}' ---"
            )
            log.debug(
                f"    State before: Time={sim_state.current_time:.2f}, Held={sim_state.held_object}"
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
            new_held_object = sim_state.held_object  # 상태 변화를 반영할 변수

            try:
                agent_pos: Optional[Position] = (
                    tuple(sim_state.scene_positions.get("agent"))
                    if "agent" in sim_state.scene_positions
                    else None
                )
                if agent_pos is None:
                    raise ValueError(
                        "Agent position ('agent') missing in scene_positions."
                    )

                # 액션 타입별 헬퍼 메서드 호출
                if action_type == "NAVIGATE_TO":
                    action_duration, action_success, new_agent_pos = (
                        self._simulate_navigate(
                            agent_pos,
                            target_obj_id,
                            partial_time_str,
                            sim_state.scene_positions,
                        )
                    )
                    if action_success and new_agent_pos is not None:
                        sim_state.scene_positions["agent"] = list(new_agent_pos)
                elif action_type == "GRASP":
                    action_duration, action_success, new_held_object = (
                        self._simulate_grasp(
                            agent_pos,
                            target_obj_id,
                            sim_state.held_object,
                            sim_state.scene_positions,
                        )
                    )
                elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                    action_duration, action_success, new_held_object = (
                        self._simulate_place(
                            agent_pos,
                            target_obj_id,
                            sim_state.held_object,
                            sim_state.scene_positions,
                        )
                    )
                elif action_type in [
                    "OPEN",
                    "CLOSE",
                    "TOGGLE_ON",
                    "TOGGLE_OFF",
                    "SLICE",
                ]:
                    action_duration, action_success = self._simulate_interaction(
                        agent_pos, action_type, target_obj_id, sim_state.scene_positions
                    )
                    # TODO: 이러한 상호작용이 scene_positions 내 객체 상태를 변경시킨다면 반영 필요
                elif action_type == "WAIT":
                    action_duration, action_success = self._simulate_wait(target_obj_id)
                elif action_type == "MONITORING":
                    action_duration, action_success = self._simulate_monitoring()
                else:
                    log.warning(
                        f"Unhandled action type in internal simulation: {action_type}. Assuming default duration and failure."
                    )
                    action_duration = PRIMITIVE_ACTION_DURATION  # 기본 시간 할당 또는 0
                    action_success = False  # 처리되지 않은 액션은 실패로 간주

                # 시뮬레이션 상태 업데이트 (헬퍼 메서드에서 변경된 부분 반영)
                sim_state.held_object = new_held_object

            except (
                ValueError
            ) as ve:  # 헬퍼 함수 내에서 발생한 예측된 오류 (e.g., 타겟 없음)
                log.error(f"  Simulation error for action '{action_str}': {ve}")
                action_success = False
                action_duration = 0  # 오류 발생 시 소요 시간 0
            except Exception as e_sim:  # 예상치 못한 오류
                log.error(
                    f"  Unexpected error during simulation of action '{action_str}': {e_sim}",
                    exc_info=True,
                )
                action_success = False
                action_duration = 0

            # 경과 시간 및 누적 시간 업데이트
            time_elapsed += action_duration
            current_cumulative_time = initial_node.state.current_time + time_elapsed

            log.debug(f"    Action Result: {'SUCCESS' if action_success else 'FAILED'}")
            log.debug(f"    Duration: {action_duration:.2f}")
            log.debug(
                f"    State after : Time={current_cumulative_time:.2f}, Held={sim_state.held_object}"
            )
            log.debug(f"--- End simulation step {i+1} ---")

            # ActionResult 생성 및 로그 추가
            action_result = ActionResult(
                actions=[action_str],
                action_full_name=action_str,
                action_type=action_type,
                # time_used는 이 액션 *완료 후*의 누적 시간
                time_used=current_cumulative_time,
                action_duration=action_duration,  # 현재 액션의 소요 시간
                # 액션 실행 후의 상태를 깊은 복사하여 저장
                scene_positions=copy.deepcopy(sim_state.scene_positions),
                held_object=sim_state.held_object,  # held_object는 불변 객체(str 또는 None)이므로 복사 필요 없음
                success=action_success,
            )
            action_log.add_result(action_result)

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
        scene_positions: Dict[str, Any],
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
        try:
            log.debug(
                f"  Finding path from {agent_pos} to {target_pos} for '{target_obj_id}'"
            )
            navigate_path = self._find_shortest_path(agent_pos, target_pos)
            # _find_shortest_path는 경로 없으면 None 반환, 내부 오류 시 None 반환 또는 예외 발생 가능
        except (
            ValueError
        ) as e_path_internal:  # 경로 탐색 내부 오류 (e.g., adjust_if_unreachable)
            log.error(
                f"    Pathfinding internal error for NAVIGATE_TO '{target_obj_id}': {e_path_internal}"
            )
            # 경로 탐색 실패 시, partial이든 full이든 진행 불가
            return 0.0, False, None
        except Exception as e_path_generic:  # 예상치 못한 경로탐색 오류
            log.error(
                f"    Unexpected pathfinding error for NAVIGATE_TO '{target_obj_id}': {e_path_generic}",
                exc_info=True,
            )
            return 0.0, False, None

        # 3. 부분 시간 이동 처리
        if partial_time_str:
            log.debug(f"  Processing NAVIGATE_TO with partial time: {partial_time_str}")
            try:
                partial_duration = float(partial_time_str)
                if partial_duration < 0:
                    log.warning(
                        f"Received negative partial time {partial_duration} for NAVIGATE_TO. Using 0."
                    )
                    partial_duration = 0.0

                duration = partial_duration  # 액션 소요 시간은 주어진 부분 시간
                success = True  # 부분 시간 이동은 일단 성공으로 간주

                # 경로가 있고, 부분 시간 내 이동 가능한 스텝 계산
                if navigate_path is not None and NAV_STEP_DURATION > 0:
                    # 이동할 스텝 수 계산 (올림/내림 정책 확인 필요, 여기선 내림 사용)
                    steps_can_take = int(
                        math.floor(partial_duration / NAV_STEP_DURATION)
                    )
                    # 경로 길이 내에서만 이동 가능
                    actual_steps = min(steps_can_take, len(navigate_path))

                    if actual_steps >= 0 and actual_steps < len(navigate_path):
                        # 실제 이동 후 위치 계산
                        new_agent_pos = navigate_path[actual_steps]
                        log.debug(
                            f"    Calculated intermediate position after {duration:.2f}s ({actual_steps} steps): {new_agent_pos}"
                        )
                    elif (
                        actual_steps >= len(navigate_path) and navigate_path
                    ):  # 경로 끝까지 도달한 경우
                        new_agent_pos = navigate_path[-1]
                        log.debug(
                            f"    Reached end of path within partial time {duration:.2f}s. Pos: {new_agent_pos}"
                        )
                    else:  # 경로가 없거나 스텝 계산 오류 시
                        new_agent_pos = (
                            agent_pos  # 이동 못한 것으로 간주, 현재 위치 반환
                        )
                        log.debug(
                            f"    No path or invalid steps ({actual_steps}) for partial navigation. Remaining at {agent_pos}."
                        )
                else:
                    # 경로가 없거나 NAV_STEP_DURATION이 0이면 위치 변경 없음
                    new_agent_pos = agent_pos
                    log.debug(
                        f"    No path found or invalid NAV_STEP_DURATION. Remaining at {agent_pos} after partial time {duration:.2f}s."
                    )

            except ValueError:
                # partial_time_str 파싱 실패
                raise ValueError(
                    f"Invalid partial time string for NAVIGATE_TO: '{partial_time_str}'"
                )

        # 4. 전체 경로 이동 처리
        else:
            log.debug(f"  Processing NAVIGATE_TO for full path.")
            if navigate_path is not None:  # 경로 찾음 (빈 리스트 [] 포함)
                path_steps = len(navigate_path)  # 실제 이동 스텝 수
                duration = path_steps * NAV_STEP_DURATION
                # 경로의 마지막 위치가 새로운 에이전트 위치 (경로가 비었으면 현재 위치)
                new_agent_pos = navigate_path[-1] if navigate_path else agent_pos
                success = True
                log.debug(
                    f"    Path found with {path_steps} steps. Duration: {duration:.2f}s. Final pos: {new_agent_pos}"
                )
            else:
                # 경로 탐색 실패 (위에서 navigate_path가 None으로 설정됨)
                log.warning(
                    f"    Navigation path not found from {agent_pos} to {target_pos} for '{target_obj_id}'. Action FAILED."
                )
                success = False
                duration = 0.0
                new_agent_pos = None  # 실패 시 최종 위치는 None

        # 5. 결과 반환
        return duration, success, new_agent_pos

    def _simulate_grasp(
        self,
        agent_pos: Position,
        target_obj_id: Optional[str],
        current_held_object: Optional[str],
        scene_positions: Dict[str, Any],
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
        scene_positions: Dict[str, Any],
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
                # if current_held_object in scene_positions:
                #    scene_positions[current_held_object] = ... # 실제 위치 업데이트 로직 필요 시 추가
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
        scene_positions: Dict[str, Any],
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
            # TODO: 필요 시 scene_positions 내 객체 상태 변경 로직 추가 (e.g., isOpened=True)
            log.debug(f"  Simulated {action_type} on '{target_obj_id}'.")
            # state_changed = True/False # 실제 상태 변경 여부 로깅 가능
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

    # --------------------------------------------------------------------------
    # 경로 탐색 (_find_shortest_path)
    # --------------------------------------------------------------------------

    def _find_shortest_path(
        self, start_pos: Position, end_pos: Position
    ) -> Optional[List[Position]]:
        """
        주어진 네비게이션 그래프에서 시작 위치부터 목표 위치까지의 최단 경로를 찾습니다.
        경로 탐색은 회전 수를 최소화하는 변형된 BFS/Dijkstra 방식을 사용합니다.

        Args:
            start_pos: 시작 위치 좌표 튜플.
            end_pos: 목표 위치 좌표 튜플.

        Returns:
            경로(위치 튜플 리스트). 시작과 끝이 같으면 빈 리스트 [].
            경로를 찾을 수 없거나 그래프 오류 시 None 반환.
        """
        if not self.nav_graph:
            log.warning(
                "_find_shortest_path called with an empty or invalid nav_graph. Cannot find path."
            )
            return None

        # 그래프 내에 존재하는 가장 가까운 노드로 위치 조정
        try:
            # adjust_if_unreachable은 주어진 위치에서 그래프 내 가장 가까운 노드를 찾아 반환해야 함
            # 또는 주어진 위치가 그래프에 없으면 에러 발생시켜야 함
            adjusted_start = adjust_if_unreachable(self.nav_graph, start_pos)
            adjusted_end = adjust_if_unreachable(self.nav_graph, end_pos)
            if adjusted_start is None or adjusted_end is None:
                raise ValueError(
                    f"Start or end position could not be adjusted to a valid graph node."
                )
            start_pos = adjusted_start
            end_pos = adjusted_end
        except KeyError as e:
            log.error(
                f"Position {e} not found in nav_graph during adjustment. Cannot find path."
            )
            return None
        except Exception as e_adjust:
            log.error(
                f"Error during position adjustment from {start_pos} or {end_pos}: {e_adjust}",
                exc_info=True,
            )
            return None

        if start_pos == end_pos:
            log.debug("Start and end positions are the same. Path length is 0.")
            return []  # 이미 도착

        # 우선순위 큐: (회전 수, 현재 위치, 이전 방향, 경로 리스트)
        pq: List[
            Tuple[int, Position, Optional[Tuple[float, float]], List[Position]]
        ] = []
        # (회전 수 0, 시작점, 방향 없음, 경로 시작)
        heapq.heappush(pq, (0, start_pos, None, [start_pos]))
        # 방문 기록: {위치: 최소 회전 수}
        visited: Dict[Position, int] = {}

        # 이동 방향 계산 함수 (x, z 평면만 고려)
        def direction(pos_a: Position, pos_b: Position) -> Tuple[float, float]:
            return (pos_b[0] - pos_a[0], pos_b[2] - pos_a[2])

        while pq:
            turn_count, current_pos, current_dir, path = heapq.heappop(pq)

            # 목표 도달
            if current_pos == end_pos:
                log.debug(
                    f"Path found with {len(path)-1} steps and {turn_count} turns."
                )
                return path

            # 이미 더 적은 회전 수로 방문한 경우 건너뛰기
            if current_pos in visited and visited[current_pos] <= turn_count:
                continue
            visited[current_pos] = turn_count

            # 현재 위치의 이웃 노드 탐색
            neighbors = self.nav_graph.get(current_pos)
            if neighbors is None:
                log.warning(
                    f"Node {current_pos} exists in path/visited but not as key in nav_graph. Skipping neighbors."
                )
                continue  # 현재 노드가 그래프에 없음 (데이터 불일치 가능성)

            for next_pos in neighbors:
                # 이미 경로에 포함된 노드는 다시 방문하지 않음 (사이클 방지)
                # 주의: 이 방식은 최단 경로를 보장하지만, 특정 상황(좁은 길 왕복)에서 길을 못 찾을 수 있음.
                #      더 견고한 방식은 비용(거리+회전) 기반 Dijkstra 필요. 현재 로직 유지.
                if next_pos in path:
                    continue

                # 다음 이동 방향 계산
                next_dir = direction(current_pos, next_pos)
                # 회전 수 계산 (이전 방향이 없거나 새 방향이 같으면 회전 수 유지, 다르면 +1)
                next_turn_count = (
                    turn_count
                    if (current_dir is None or next_dir == current_dir)
                    else (turn_count + 1)
                )

                new_path = path + [next_pos]
                # 우선순위 큐에 추가 (회전 수 우선)
                heapq.heappush(pq, (next_turn_count, next_pos, next_dir, new_path))

        # 루프 종료 후에도 경로를 찾지 못한 경우
        log.warning(f"No path found from {start_pos} to {end_pos} after exploring.")
        return None  # 경로 없음

    # --------------------------------------------------------------------------
    # 액션 분할 (split_subtask_by_cutoff_time)
    # --------------------------------------------------------------------------

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: List[str],
        cutoff_time: float,
    ) -> Optional[Tuple[Optional[ActionResult], Optional[ActionResult]]]:
        """
        주어진 액션 시퀀스를 지정된 cutoff_time 기준으로 두 부분으로 나눕니다.
        내부 시뮬레이션(_simulate_actions)을 사용하여 각 액션의 완료 시간을 계산하고,
        cutoff_time을 초과하는 첫 번째 액션을 기준으로 분할합니다.
        GRASP와 PLACE 액션 쌍이 분할 경계에 걸치는 것을 방지합니다.

        Args:
            current_node: 분할을 시작할 기준 노드.
            primitive_actions: 분할 대상 액션 시퀀스.
            cutoff_time: 분할 기준 시간 (current_node.state.current_time 기준 상대 시간).

        Returns:
            분할 성공 시 (pre-cutoff 마지막 ActionResult, post-cutoff 마지막 ActionResult) 튜플.
            - 모든 액션이 cutoff_time 이전이면 (마지막 액션 결과, None).
            - 모든 액션이 cutoff_time 이후이면 (None, 마지막 액션 결과).
            - 분할 중 오류 발생 또는 GRASP/PLACE 제약 위반 시 None.
        """
        log.debug(
            f"Attempting to split actions at cutoff time: {cutoff_time:.2f} "
            f"(relative to node time {current_node.state.current_time:.2f})"
        )
        if cutoff_time < 0:
            log.warning(f"Cutoff time {cutoff_time:.2f} is negative. Using 0.")
            cutoff_time = 0.0

        # 1. 전체 시퀀스 시뮬레이션 (시간 정보 얻기 위해)
        #    _simulate_actions는 내부적으로 오류 처리 및 실패 시 중단 로직 포함
        full_simulation_log = self._simulate_actions(current_node, primitive_actions)

        # 전체 시뮬레이션 로그 유효성 검사
        if not full_simulation_log or not full_simulation_log.results:
            log.error(
                "Full internal simulation failed or produced no results. Cannot split actions."
            )
            return None  # 분할 불가

        # 시뮬레이션 마지막 액션이 실패했는지 확인 (선택적: 실패해도 분할 시도 가능)
        # if not full_simulation_log.results[-1].success:
        #     log.warning("Full simulation ended with a failed action. Split might be based on partial results.")

        # 2. 분할 지점 결정
        split_index = -1  # pre-cutoff 부분의 마지막 액션 인덱스
        for i, result in enumerate(full_simulation_log.results):
            # 현재 액션 완료까지의 *상대* 시간 계산
            action_end_time_relative = (
                result.time_used - current_node.state.current_time
            )
            # cutoff_time 이하인 마지막 액션 찾기 (부동소수점 오차 감안 EPSILON 사용)
            if action_end_time_relative <= cutoff_time + EPSILON:
                split_index = i
            else:
                # 이 액션부터 post-cutoff
                break  # 분할점 찾음

        # 3. pre-cutoff / post-cutoff 액션 리스트 생성 (디버깅/로깅용, 실제 결과는 로그에서 추출)
        pre_cutoff_action_strs = primitive_actions[: split_index + 1]
        post_cutoff_action_strs = primitive_actions[split_index + 1 :]

        log.debug(
            f"Determined split point index: {split_index}. "
            f"Pre-cutoff actions ({len(pre_cutoff_action_strs)}): {pre_cutoff_action_strs}. "
            f"Post-cutoff actions ({len(post_cutoff_action_strs)}): {post_cutoff_action_strs}."
        )

        # 4. GRASP / PLACE 제약 조건 확인
        grasped_object_at_split: Optional[str] = None
        if split_index >= 0 and split_index < len(full_simulation_log.results):
            # 분할 지점 직후의 상태 확인 (split_index 액션 완료 후 상태)
            split_point_result = full_simulation_log.results[split_index]
            if split_point_result.success:  # 성공한 액션의 결과만 유효
                grasped_object_at_split = split_point_result.held_object

        if grasped_object_at_split and post_cutoff_action_strs:
            # post-cutoff 액션 중에 PLACE 액션이 있는지 확인
            has_place_in_post = any(
                action.upper().startswith("PLACE_")
                for action in post_cutoff_action_strs
            )
            if has_place_in_post:
                log.error(
                    "Split occurs between a GRASP action (holding "
                    f"'{grasped_object_at_split}' at split point) and a subsequent "
                    "PLACE action. This split is invalid. Aborting split."
                )
                return None  # 제약 조건 위반으로 분할 실패

        # 5. 결과 추출 (재시뮬레이션 불필요)
        last_pre_result: Optional[ActionResult] = None
        last_post_result: Optional[ActionResult] = None

        # pre-cutoff 결과 설정
        if split_index >= 0:  # pre-cutoff 액션이 하나 이상 존재
            last_pre_result = full_simulation_log.results[split_index]

        # post-cutoff 결과 설정
        post_cutoff_results = full_simulation_log.results[split_index + 1 :]
        if post_cutoff_results:  # post-cutoff 액션이 하나 이상 존재
            last_post_result = post_cutoff_results[-1]

        log.debug(
            f"Split successful. Returning results: "
            f"Pre-cutoff result available: {last_pre_result is not None}, "
            f"Post-cutoff result available: {last_post_result is not None}"
        )

        return (last_pre_result, last_post_result)
