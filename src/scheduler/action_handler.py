import copy
import heapq
import logging
import math
from typing import List, Optional, Tuple

from ithor.utils.math_utils import adjust_if_unreachable
from src.core.dataclass import ActionResult, ActionSimulationLog, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import EPSILON
from src.utils.config.constants import (
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
    REACHABLE_DISTANCE_THRESHOLD,
)

log = logging.getLogger(__name__)


class ActionHandler:
    def __init__(self, nav_graph: Optional[dict]):
        # Add check for invalid nav_graph
        if not nav_graph:  # Handles None or empty dict {}
            log.warning(
                "Navigation graph provided to ActionHandler is empty or None. Navigation actions will fail."
            )
            # Initialize with an empty dict to avoid errors in .get() calls,
            # but navigation itself won't work.
            self.nav_graph = {}
        else:
            self.nav_graph = nav_graph

    def get_actions_info(
        self, current_node: SimulationNode, actions: list[str]
    ) -> Optional[ActionResult]:
        """
        Simulates the given action sequence and returns the final ActionResult.
        Creates a copy of the node state for simulation.
        Returns None if simulation fails or the action list is empty.

        CRITICAL NOTE: This simulation relies on `_simulate_actions`, which uses
              placeholder logic and INTERNAL ESTIMATES (pathfinding, constants) without
              calling the actual AI2THOR environment. The returned ActionResult
              (time_used, action_duration, success, state changes) IS AN ESTIMATE
              and may differ significantly from real execution. Accuracy depends
              heavily on the nav_graph quality, constants, and simplified models.
        """
        if not actions:
            log.warning("get_actions_info called with empty actions list.")
            return None

        # 5.1: 시뮬레이션을 위해 상태 복사본 생성
        sim_node = copy.deepcopy(current_node)
        log.debug(
            f"Starting internal simulation for actions: {actions} from time {sim_node.state.current_time:.2f}"
        )
        try:
            # 시뮬레이션 함수는 복사된 노드 상태를 직접 변경함
            log_info = self._simulate_actions(sim_node, actions)
            # Check if simulation was successful and produced results
            if not log_info or not log_info.results:
                log.error(
                    f"Internal simulation failed or resulted in empty log for actions: {actions}. Returning None."
                )
                return None

            # --- 수정: 마지막 액션의 ActionResult 반환 확인 및 성공 여부 로깅 ---
            # log_info.results는 ActionResult 객체의 리스트임
            last_result = log_info.results[-1]
            if not isinstance(last_result, ActionResult):
                log.error(
                    f"Last simulation result is not an ActionResult object: {type(last_result)}. Returning None."
                )
                return None

            log.debug(
                f"Internal simulation finished. Last action success: {last_result.success}. Final estimated time: {last_result.time_used:.2f}"
            )
            return last_result
            # --- 수정 끝 ---\
        except Exception as e:
            # _simulate_actions 내부에서 발생한 예외 (ValueError 등) 처리
            log.error(
                f"Internal action simulation failed for actions {actions}: {e}. Returning None.",
                exc_info=True,
            )
            return None

    def _simulate_actions(
        self,
        current_node: SimulationNode,  # This node's state WILL be modified
        primitive_actions: List[str],
    ) -> ActionSimulationLog:
        """
        Simulates actions sequentially using INTERNAL MODELS, updating the state within current_node.
        Raises ValueError on critical simulation errors (e.g., unknown action, object not found).

        *** CRITICAL WARNING: INTERNAL SIMULATION LOGIC ***
        This method simulates action effects internally without calling AI2THOR.
        Uses:
          - Pathfinding (`_find_shortest_path`) for NAVIGATE_TO duration.
          - Constants (`PRIMITIVE_ACTION_DURATION`, `MONITORING_DURATION`) for others.
          - Simplified state updates (agent position, held object, basic object properties).
        Assumptions & Limitations:
          - Reachability for interactions is CHECKED SIMPLISTICALLY via distance threshold.
          - Complex object state changes (cooking, cleaning state) are NOT modeled.
          - Collision detection during navigation is NOT modeled.
          - Actions succeed unless path not found, target missing, or basic checks fail.
        Accuracy depends heavily on nav_graph, constants, REACHABLE_DISTANCE_THRESHOLD, and simplified models.
        This is **NOT** a replacement for real execution via `runner_ai2thor.py`.
        """
        action_log_info = ActionSimulationLog()

        # Modify state directly on the passed node (or its copy)
        scene_positions = (
            current_node.state.scene_positions
        )  # Direct reference if copy was made outside
        held_object = current_node.state.held_object
        time_used = current_node.state.current_time  # Start from node's current time

        initial_time = time_used  # For calculating duration of each step

        for i, prim_action in enumerate(primitive_actions):  # Get index for logging
            tokens = prim_action.split()
            if not tokens:
                log.warning(f"Empty action string encountered at index {i}. Skipping.")
                continue

            action_type = tokens[0].upper()
            target_obj_id = tokens[1] if len(tokens) > 1 else None
            partial_time_str = tokens[2] if len(tokens) > 2 else None

            # Basic validation: Check if target object exists (if applicable)
            if (
                target_obj_id
                and action_type != "WAIT"  # WAIT action uses target_obj_id for duration
                and action_type != "MONITORING"  # MONITORING might use it differently
                and target_obj_id not in scene_positions
                and target_obj_id != held_object  # Allow placing the held object
            ):
                log.error(
                    f"Action '{prim_action}': Target object '{target_obj_id}' not found in scene_positions {list(scene_positions.keys())} and is not held."
                )
                raise ValueError(
                    f"Target object '{target_obj_id}' not found for action '{prim_action}'."
                )

            action_duration = 0.0
            action_success = True  # Assume success initially
            # --- 추가: 액션 시작 시점의 상태 로깅 (디버깅용) ---
            log.debug(
                f"Simulating action {i+1}/{len(primitive_actions)}: '{prim_action}' | Time: {time_used:.2f} | Held: {held_object}"
            )
            # --- 추가 끝 ---

            try:
                # --- 수정: 액션 타입별 시뮬레이션 로직 개선 ---
                agent_pos_tuple = scene_positions.get("agent")
                if not agent_pos_tuple:
                    log.error(
                        "Agent position not found in scene_positions. Cannot simulate action."
                    )
                    raise ValueError("Agent position missing")
                agent_pos = tuple(agent_pos_tuple)  # 튜플로 변환 보장

                if action_type == "NAVIGATE_TO":
                    if not target_obj_id or target_obj_id not in scene_positions:
                        log.error(
                            f"Navigation target '{target_obj_id}' not found in scene positions."
                        )
                        action_success = False
                    else:
                        target_pos = tuple(
                            scene_positions[target_obj_id]["position"]
                        )  # 객체 위치 사용
                        # --- 수정: 경로 탐색 실패 시 에러 로깅 강화 ---
                        try:
                            path = self._find_shortest_path(agent_pos, target_pos)
                        except Exception as e_path:
                            log.error(
                                f"Pathfinding error during NAVIGATE_TO {target_obj_id}: {e_path}",
                                exc_info=True,
                            )
                            path = None  # 경로 탐색 실패 처리

                        if path:
                            # 경로 길이에 기반한 시간 추정 (NAV_STEP_DURATION 사용)
                            action_duration = len(path) * NAV_STEP_DURATION
                            # 상태 업데이트: 에이전트 위치를 목표 위치로 이동
                            scene_positions["agent"] = list(path[-1])  # 리스트로 저장
                            log.debug(
                                f"  Simulated NAVIGATE_TO '{target_obj_id}'. Path length: {len(path)}, Est. Duration: {action_duration:.2f}. New agent pos: {scene_positions['agent']}"
                            )
                        else:
                            log.warning(
                                f"  Navigation path not found from {agent_pos} to {target_pos} for '{target_obj_id}'. Action FAILED."
                            )
                            action_success = False
                            action_duration = 0  # 실패 시 시간 0

                elif action_type == "GRASP":
                    if not target_obj_id or target_obj_id not in scene_positions:
                        log.error(f"Grasp target '{target_obj_id}' not found.")
                        action_success = False
                    elif held_object:
                        log.warning(
                            f"Agent already holding '{held_object}'. Cannot grasp '{target_obj_id}'."
                        )
                        action_success = False
                    else:
                        # --- 수정: 도달 가능성 확인 로직 추가 ---
                        target_actual_pos = tuple(
                            scene_positions[target_obj_id]["position"]
                        )
                        dist = math.sqrt(
                            sum(
                                [
                                    (a - b) ** 2
                                    for a, b in zip(agent_pos, target_actual_pos)
                                ]
                            )
                        )
                        if dist > REACHABLE_DISTANCE_THRESHOLD:  # 예: 1.5m
                            log.warning(
                                f"  Grasp target '{target_obj_id}' might be unreachable (Distance: {dist:.2f} > {REACHABLE_DISTANCE_THRESHOLD}). Action FAILED."
                            )
                            action_success = False
                        # --- 수정 끝 ---
                        if action_success:  # 도달 가능하면 상태 업데이트
                            held_object = target_obj_id
                            # scene_positions 내 객체 상태 업데이트 (isPickedUp)
                            if target_obj_id in scene_positions and isinstance(
                                scene_positions[target_obj_id], dict
                            ):
                                scene_positions[target_obj_id]["isPickedUp"] = True
                            action_duration = PRIMITIVE_ACTION_DURATION
                            log.debug(
                                f"  Simulated GRASP '{target_obj_id}'. Duration: {action_duration:.2f}. Agent now holds: {held_object}"
                            )

                elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                    receptacle_id = target_obj_id
                    if not held_object:
                        log.warning(f"Agent not holding anything. Cannot place.")
                        action_success = False
                    elif not receptacle_id or receptacle_id not in scene_positions:
                        log.error(
                            f"Place target receptacle '{receptacle_id}' not found."
                        )
                        action_success = False
                    else:
                        # --- 수정: 도달 가능성 확인 로직 추가 ---
                        receptacle_pos = tuple(
                            scene_positions[receptacle_id]["position"]
                        )
                        dist = math.sqrt(
                            sum(
                                [
                                    (a - b) ** 2
                                    for a, b in zip(agent_pos, receptacle_pos)
                                ]
                            )
                        )
                        if dist > REACHABLE_DISTANCE_THRESHOLD:
                            log.warning(
                                f"  Place target receptacle '{receptacle_id}' might be unreachable (Distance: {dist:.2f} > {REACHABLE_DISTANCE_THRESHOLD}). Action FAILED."
                            )
                            action_success = False
                        # --- 수정 끝 ---

                        # --- 수정: receptacle 상태 확인 로직 추가 (openable이고 PLACE_INSIDE 경우) ---
                        if action_success and action_type == "PLACE_INSIDE":
                            receptacle_meta = scene_positions.get(receptacle_id)
                            if (
                                isinstance(receptacle_meta, dict)
                                and receptacle_meta.get("openable")
                                and not receptacle_meta.get("isOpen")
                            ):
                                log.warning(
                                    f"  Cannot place inside closed receptacle '{receptacle_id}'. Action FAILED."
                                )
                                action_success = False
                        # --- 수정 끝 ---

                        if action_success:  # 도달 가능하고 상태가 맞으면 진행
                            # 상태 업데이트: held_object 상태 변경 및 scene_positions 업데이트
                            log.debug(
                                f"  Simulating PLACE '{held_object}' on/in '{receptacle_id}'."
                            )
                            if held_object in scene_positions and isinstance(
                                scene_positions[held_object], dict
                            ):
                                scene_positions[held_object]["isPickedUp"] = False
                                # 위치는 receptacle 위치로 단순화 (정확한 배치는 어려움)
                                scene_positions[held_object]["position"] = (
                                    scene_positions[receptacle_id]["position"]
                                )
                                log.debug(
                                    f"    Updated state for '{held_object}': isPickedUp=False, pos={scene_positions[held_object]['position']}"
                                )
                            else:  # 만약 grasp 시 scene_positions에서 제거했다면 다시 추가 (이 경우는 없어야 함)
                                log.warning(
                                    f"    Held object '{held_object}' not found in scene_positions during PLACE. Re-adding with receptacle position."
                                )
                                scene_positions[held_object] = {
                                    "position": scene_positions[receptacle_id][
                                        "position"
                                    ],
                                    "isPickedUp": False,
                                    # TODO: 다른 기본 속성 추가 필요 (e.g., openable, toggleable...)
                                }
                            held_object = None  # 손 비우기
                            action_duration = PRIMITIVE_ACTION_DURATION
                            log.debug(
                                f"    PLACE successful. Duration: {action_duration:.2f}. Agent now holds: {held_object}"
                            )

                elif action_type in [
                    "OPEN",
                    "CLOSE",
                    "TOGGLE_ON",
                    "TOGGLE_OFF",
                    "SLICE",
                ]:
                    # --- TODO: 객체 상태 업데이트 로직 구현 (scene_positions 내 객체 메타데이터 수정) --- \
                    # 예: scene_positions[target_obj_id]['isOpen'] = True / False 등
                    # 현재는 상태 변경 없이 시간만 소요되는 것으로 처리
                    if not target_obj_id or target_obj_id not in scene_positions:
                        log.error(f"{action_type} target '{target_obj_id}' not found.")
                        action_success = False
                    else:
                        # --- 수정: 도달 가능성 확인 로직 추가 ---
                        target_actual_pos = tuple(
                            scene_positions[target_obj_id]["position"]
                        )
                        dist = math.sqrt(
                            sum(
                                [
                                    (a - b) ** 2
                                    for a, b in zip(agent_pos, target_actual_pos)
                                ]
                            )
                        )
                        if dist > REACHABLE_DISTANCE_THRESHOLD:
                            log.warning(
                                f"  {action_type} target '{target_obj_id}' might be unreachable (Distance: {dist:.2f} > {REACHABLE_DISTANCE_THRESHOLD}). Action FAILED."
                            )
                            action_success = False
                        # --- 수정 끝 ---

                        if action_success:
                            target_meta = scene_positions.get(target_obj_id)
                            state_changed = False
                            if isinstance(target_meta, dict):
                                if action_type == "OPEN" and target_meta.get(
                                    "openable"
                                ):
                                    if not target_meta.get(
                                        "isOpen", False
                                    ):  # 이미 열려있지 않으면 변경
                                        target_meta["isOpen"] = True
                                        state_changed = True
                                        log.debug(
                                            f"    Simulated OPEN for '{target_obj_id}'. New state: isOpen=True"
                                        )
                                elif action_type == "CLOSE" and target_meta.get(
                                    "openable"
                                ):
                                    if target_meta.get(
                                        "isOpen", False
                                    ):  # 이미 닫혀있지 않으면 변경
                                        target_meta["isOpen"] = False
                                        state_changed = True
                                        log.debug(
                                            f"    Simulated CLOSE for '{target_obj_id}'. New state: isOpen=False"
                                        )
                                # --- TODO: 다른 상태 변경 액션 (TOGGLE, SLICE 등)에 대한 로직 추가 ---
                                # elif action_type == "TOGGLE_ON" and ...
                            else:
                                log.warning(
                                    f"  Metadata not found or not a dict for '{target_obj_id}'. Cannot simulate state change for {action_type}."
                                )
                                action_success = (
                                    False  # 상태 변경 불가 시 실패 처리 고려
                                )

                            if action_success:
                                action_duration = PRIMITIVE_ACTION_DURATION
                                log.debug(
                                    f"  Simulated {action_type} '{target_obj_id}'. Duration: {action_duration:.2f}. State changed: {state_changed}"
                                )
                            # else: 실패 로그는 위에서 처리됨

                elif action_type == "WAIT":
                    try:
                        wait_time = float(target_obj_id)  # WAIT 액션의 target은 시간
                        if wait_time < 0:
                            log.warning(
                                f"Invalid negative wait time: {wait_time}. Using 0."
                            )
                            wait_time = 0.0
                        action_duration = wait_time
                        log.debug(f"Simulated WAIT. Duration: {action_duration:.2f}")
                    except (TypeError, ValueError):
                        log.error(f"Invalid WAIT duration: {target_obj_id}")
                        action_success = False

                elif action_type == "MONITORING":
                    action_duration = MONITORING_DURATION
                    log.debug(f"Simulated MONITORING. Duration: {action_duration:.2f}")

                else:
                    log.warning(
                        f"Unhandled action type in internal simulation: {action_type}"
                    )
                    action_duration = (
                        PRIMITIVE_ACTION_DURATION  # 기본 시간 부여 또는 실패 처리
                    )
                    # action_success = False # 필요시 실패 처리

                # --- 수정: 실패 시에도 소요 시간 반영 고려 (주석 처리) ---
                # 실패가 즉시 발생하지 않고 시간이 소요된 경우 (예: 네비게이션 중 충돌 감지 - 현재 미구현)
                # action_duration_before_failure = ... # 실패까지 걸린 시간
                # if not action_success and action_duration_before_failure > 0:
                #     time_used += action_duration_before_failure
                #     log.debug(f"  Action FAILED after {action_duration_before_failure:.2f}s.")
                # else: # 즉시 실패 또는 성공
                #     time_used += action_duration
                #     log.debug(f"  Action {'SUCCESS' if action_success else 'FAILED (Immediate)'}. Duration: {action_duration:.2f}. Cumulative time: {time_used:.2f}")
                # --- 현재 로직: 실패 시 duration 0, 성공 시 duration 더함 ---
                time_used += action_duration
                log.debug(
                    f"  Action {'SUCCESS' if action_success else 'FAILED'}. Duration: {action_duration:.2f}. Cumulative time: {time_used:.2f}"
                )
                # --- 수정 끝 ---

                # Log the result including success status
                # --- 수정: 상태 복사 시점 명확화 및 로그 레벨 조정 ---
                action_result = ActionResult(
                    actions=[prim_action],  # 현재 처리된 액션
                    action_full_name=prim_action,
                    action_type=action_type,
                    time_used=time_used,  # 누적 시간 (현재 액션 완료 또는 실패 시점)
                    action_duration=action_duration,  # 현재 액션의 소요 시간 (실패 시 0 또는 실패까지 시간)
                    scene_positions=copy.deepcopy(
                        scene_positions
                    ),  # 액션 시도 *후*의 상태
                    held_object=held_object,  # 액션 시도 *후*의 상태
                    success=action_success,  # 성공 여부
                )
                action_log_info.add_result(action_result)
                # log.debug(f"    Logged ActionResult: Success={action_success}, Time={time_used:.2f}, Held={held_object}") # 상세 로그 필요 시 사용
                # --- 수정 끝 ---

            except ValueError as e:  # ValueError 포함하여 예외 처리 강화
                log.error(f"  Action '{prim_action}' simulation CRASHED: {e}")
                action_success = False
                action_duration = 0
            except Exception as e_generic:  # 예상치 못한 다른 오류
                log.error(
                    f"  Unexpected error during simulation of action '{prim_action}': {e_generic}",
                    exc_info=True,
                )
                action_success = False
                action_duration = 0

            # Accumulate time *only if action was successful* (or partially successful for nav)
            # If action failed immediately, duration is 0, time_used doesn't increase.
            # If action took time then failed (e.g., navigation collision simulation),
            # action_duration should reflect time until failure. (Current logic uses 0 on failure).
            # --- TODO: 실패 시에도 소요 시간 반영 고려 --- \
            # if not action_success and action_duration_before_failure > 0:
            #    time_used += action_duration_before_failure
            # else:
            #    time_used += action_duration
            # --- TODO 끝 ---
            time_used += action_duration

            # --- MODIFIED: Stop processing if an action failed ---
            if not action_success:
                log.warning(
                    f"Stopping action sequence simulation at index {i} because action '{prim_action}' failed."
                )
                break  # Exit the loop

        # Return the log, which now includes success info and stops at failure
        return action_log_info

    def _find_shortest_path(
        self, start_pos: tuple[float, float, float], end_pos: tuple[float, float, float]
    ) -> Optional[list[tuple[float, float, float]]]:
        """Finds the shortest path using BFS/Dijkstra variant on the nav_graph."""
        # Check if graph is valid before proceeding
        if not self.nav_graph:
            log.warning(
                "_find_shortest_path called with an empty or invalid nav_graph."
            )
            return None

        # Adjust positions to ensure they exist in the graph (handle potential float inaccuracies)
        try:
            start_node = adjust_if_unreachable(self.nav_graph, start_pos)
            end_node = adjust_if_unreachable(self.nav_graph, end_pos)
        except Exception as e:
            log.error(
                f"Error during adjust_if_unreachable from {start_pos} or {end_pos}: {e}",
                exc_info=True,
            )
            return None

        if start_node is None or end_node is None:
            log.warning(f"Start or end node not found in the graph.")
            return None

        # ... (rest of the pathfinding logic) ...

        return path

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: list[str],
        cutoff_time: float,
    ) -> Optional[
        Tuple[ActionResult, ActionResult]
    ]:  # 반환 타입을 각 로그의 마지막 ActionResult 튜플로 변경 (Scheduler 요구사항 확인 필요)
        # 또는 (ActionSimulationLog, ActionSimulationLog) 유지
        """
        Splits a sequence of actions based on a cutoff time using optimized re-simulation.
        Handles GRASP/PLACE pairs spanning the cutoff.
        Returns a tuple of two ActionResult objects (last result of pre-cutoff, last result of post-cutoff)
        if successful, otherwise None.
        Returns (last_pre_result, None) if all actions are pre-cutoff.
        Returns (None, last_post_result) if all actions are post-cutoff (cutoff_time <= 0).

        NOTE: Relies on the INTERNAL simulation `_simulate_actions`. The accuracy
              of the split point depends on the accuracy of this internal model.
        """
        log.debug(
            f"Attempting to split actions at cutoff time: {cutoff_time:.2f} for node at time {current_node.state.current_time:.2f}"
        )
        if cutoff_time < 0:
            log.warning(f"Cutoff time {cutoff_time:.2f} is negative. Using 0.")
            cutoff_time = 0.0

        # (1) Simulate the full sequence to get timing info
        full_log: Optional[ActionSimulationLog] = None
        full_sim_node = copy.deepcopy(current_node)
        try:
            # Use the modified _simulate_actions which handles errors and stops on failure
            full_log = self._simulate_actions(full_sim_node, primitive_actions)
            # Check if simulation succeeded at all (at least one successful action)
            if not full_log or not full_log.results or not full_log.results[-1].success:
                log.error(
                    f"Full internal simulation failed or resulted in empty/failed log for actions: {primitive_actions}. Cannot split."
                )
                return None  # 실패 시 None 반환
        except (
            ValueError,
            NotImplementedError,
        ) as e:  # 시뮬레이션 중 발생 가능한 에러 처리
            log.error(
                f"Full internal simulation failed during split preparation: {e}. Cannot split."
            )
            return None  # 실패 시 None 반환
        except Exception as e_full_sim:
            log.error(
                f"Unexpected error during full internal simulation for split: {e_full_sim}",
                exc_info=True,
            )
            return None

        # (2) Determine split point based on cumulative time in the successful simulation log
        pre_cutoff_actions: list[str] = []
        post_cutoff_actions: list[str] = []
        split_index = -1  # The index of the last action in the pre-cutoff part

        for i, result in enumerate(full_log.results):
            action_end_time_relative = (
                result.time_used - current_node.state.current_time
            )
            if action_end_time_relative <= cutoff_time + EPSILON:
                split_index = i
            else:
                # First action exceeding cutoff marks the start of post-cutoff
                post_cutoff_actions = primitive_actions[i:]
                break  # Found the split point
        else:
            # Loop completed without break, all actions are pre-cutoff
            split_index = len(primitive_actions) - 1
            post_cutoff_actions = []

        pre_cutoff_actions = primitive_actions[: split_index + 1]

        log.debug(
            f"Initial split at time {cutoff_time:.2f}: Pre={pre_cutoff_actions}, Post={post_cutoff_actions}"
        )

        # 5.2: GRASP/PLACE 쌍 분할 방지 로직 추가
        grasped_object_in_pre = None
        if pre_cutoff_actions and post_cutoff_actions:
            # --- 수정: 분할 시점(split_index)의 상태 확인 --- \
            # last_pre_result = full_log.results[-1]
            if split_index >= 0 and split_index < len(full_log.results):
                split_point_result = full_log.results[split_index]
                if split_point_result.success and split_point_result.held_object:
                    grasped_object_in_pre = split_point_result.held_object
            # --- 수정 끝 ---

        if grasped_object_in_pre and post_cutoff_actions:
            # --- 수정: PLACE 액션 존재 여부 검사 강화 ---\
            # PLACE_INSIDE, PLACE_ON_TOP 모두 확인
            place_action_exists_in_post = any(
                action.upper().startswith("PLACE_") for action in post_cutoff_actions
            )
            if place_action_exists_in_post:
                log.error(
                    f"[_split_subtask_by_cutoff_time] Split occurs between GRASP('{grasped_object_in_pre}') "
                    f"in pre-cutoff and a PLACE action in post-cutoff. This is not allowed. Split failed."
                )
                # --- 수정: 반환 타입 일치 (단일 None 반환) ---\
                # return None, None
                return None
                # --- 수정 끝 ---

        # (5) Extract results from the existing full_log (No re-simulation)
        # --- 수정: ActionResult 튜플 반환 로직 ---
        last_pre_result: Optional[ActionResult] = None
        last_post_result: Optional[ActionResult] = None

        if pre_cutoff_actions:
            # split_index는 pre_cutoff의 마지막 액션 인덱스
            if split_index >= 0:
                last_pre_result = full_log.results[split_index]
            else:  # pre_cutoff_actions가 비어있는 경우는 없어야 함 (split_index = -1 이면 pre는 빈 리스트)
                log.error(
                    "Inconsistent state: pre_cutoff_actions exist but split_index < 0."
                )
                return None

        if post_cutoff_actions:
            # post_cutoff_actions는 split_index + 1 부터 시작
            post_results = full_log.results[split_index + 1 :]
            if post_results:
                last_post_result = post_results[-1]
            else:  # post_cutoff_actions가 있으나 결과가 없는 경우 (오류)
                log.error(
                    "Inconsistent state: post_cutoff_actions exist but no corresponding results found."
                )
                return None

        log.debug(
            f"Split successful. Returning last results: Pre={last_pre_result is not None}, Post={last_post_result is not None}"
        )
        # pre만 있거나, post만 있거나, 둘 다 있거나, 둘 다 없는(오류) 경우 처리 가능
        return (last_pre_result, last_post_result)
        # --- 수정 끝 ---
