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

        NOTE: This simulation currently relies on `_simulate_actions`, which uses
              placeholder logic and does not interact with the actual AI2THOR environment.
              The returned ActionResult (especially time_used, action_duration, success,
              and state changes) WILL BE INACCURATE until integrated with real simulation.
        """
        if not actions:
            log.warning("get_actions_info called with empty actions list.")
            return None

        # 5.1: 시뮬레이션을 위해 상태 복사본 생성
        sim_node = copy.deepcopy(current_node)
        try:
            # 시뮬레이션 함수는 복사된 노드 상태를 직접 변경함
            log_info = self._simulate_actions(sim_node, actions)
            # Check if simulation was successful and produced results
            if not log_info or not log_info.results:
                log.error(
                    f"Full simulation failed or resulted in empty log for actions: {actions}"
                )
                return None
            # --- 수정: 마지막 액션의 ActionResult 반환 확인 ---
            # log_info.results는 ActionResult 객체의 리스트임
            last_result = log_info.results[-1]
            if not isinstance(last_result, ActionResult):
                log.error(
                    f"Last simulation result is not an ActionResult object: {type(last_result)}"
                )
                return None
            return last_result
        except Exception as e:
            log.error(f"Action simulation failed: {e}", exc_info=True)
            return None

    def _simulate_actions(
        self,
        current_node: SimulationNode,  # This node's state WILL be modified
        primitive_actions: List[str],
    ) -> ActionSimulationLog:
        """
        Simulates actions sequentially, updating the state within current_node.
        Raises ValueError on critical simulation errors (e.g., unknown action, object not found).
        *** CRITICAL WARNING: Improved Internal Simulation Logic ***
        This method simulates action effects internally without calling AI2THOR directly
        to allow for fast lookahead in the scheduler. It uses:
          - Pathfinding (`_find_shortest_path`) for NAVIGATE_TO duration estimation.
          - Constants (`PRIMITIVE_ACTION_DURATION`, `MONITORING_DURATION`) for other actions.
          - Simplified state updates (agent position, held object, basic object states).
        Assumptions:
          - Reachability for interactions is simplified (or assumed).
          - Complex object state changes (e.g., cooking) are not modeled.
          - Actions generally succeed unless navigation path is not found.
        The accuracy depends on the navigation graph, constants, and the simplified models.
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
                        path = self._find_shortest_path(agent_pos, target_pos)
                        if path:
                            # 경로 길이에 기반한 시간 추정 (NAV_STEP_DURATION 사용)
                            action_duration = len(path) * NAV_STEP_DURATION
                            # 상태 업데이트: 에이전트 위치를 목표 위치로 이동
                            scene_positions["agent"] = list(path[-1])  # 리스트로 저장
                            log.debug(
                                f"Simulated NAVIGATE_TO '{target_obj_id}'. Path length: {len(path)}, Duration: {action_duration:.2f}"
                            )
                        else:
                            log.warning(
                                f"Navigation path not found from {agent_pos} to {target_pos} for '{target_obj_id}'."
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
                        # TODO: 실제 도달 가능성(거리) 확인 로직 추가?
                        held_object = target_obj_id
                        # scene_positions에서 객체 제거 (더 이상 씬에 독립적으로 존재하지 않음)
                        # del scene_positions[target_obj_id] # 실제 환경에서는 위치 정보가 남을 수 있음. 일단 유지.
                        # 대신 isPickedUp 상태 업데이트 (만약 객체 메타데이터가 있다면)
                        if target_obj_id in scene_positions and isinstance(
                            scene_positions[target_obj_id], dict
                        ):
                            scene_positions[target_obj_id]["isPickedUp"] = True
                        action_duration = PRIMITIVE_ACTION_DURATION
                        log.debug(
                            f"Simulated GRASP '{target_obj_id}'. Duration: {action_duration:.2f}"
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
                        # TODO: 실제 도달 가능성 확인 로직 추가?
                        # TODO: receptacle이 열려있는지 등 상태 확인 로직 추가?
                        # 상태 업데이트: held_object를 receptacle 근처 위치로 이동 (단순화)
                        # scene_positions에 다시 추가하고 held_object 비움
                        if held_object in scene_positions and isinstance(
                            scene_positions[held_object], dict
                        ):
                            scene_positions[held_object]["isPickedUp"] = False
                            # 위치는 receptacle 위치로 단순화 (정확한 배치는 어려움)
                            scene_positions[held_object]["position"] = scene_positions[
                                receptacle_id
                            ]["position"]
                        else:  # 만약 grasp 시 scene_positions에서 제거했다면 다시 추가
                            scene_positions[held_object] = {
                                "position": scene_positions[receptacle_id]["position"],
                                "isPickedUp": False,
                                # 다른 기본 속성 추가 필요
                            }
                        log.debug(
                            f"Simulated PLACE '{held_object}' on/in '{receptacle_id}'."
                        )
                        held_object = None
                        action_duration = PRIMITIVE_ACTION_DURATION

                elif action_type in [
                    "OPEN",
                    "CLOSE",
                    "TOGGLE_ON",
                    "TOGGLE_OFF",
                    "SLICE",
                ]:
                    # TODO: 객체 상태 업데이트 로직 구현 (scene_positions 내 객체 메타데이터 수정)
                    # 예: scene_positions[target_obj_id]['isOpen'] = True / False 등
                    # 현재는 상태 변경 없이 시간만 소요되는 것으로 처리
                    if not target_obj_id or target_obj_id not in scene_positions:
                        log.error(f"{action_type} target '{target_obj_id}' not found.")
                        action_success = False
                    else:
                        # TODO: 실제 도달 가능성 확인 로직 추가?
                        action_duration = PRIMITIVE_ACTION_DURATION
                        log.debug(
                            f"Simulated {action_type} '{target_obj_id}'. Duration: {action_duration:.2f} (State change not fully modeled)"
                        )

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

                # --- 수정 끝 ---

            except ValueError as e:  # ValueError 포함하여 예외 처리 강화
                log.error(f"Action '{prim_action}' failed during simulation: {e}")
                action_success = False
                action_duration = 0

            # Accumulate time *only if action was successful* (or partially successful for nav)
            # If action failed immediately, duration is 0, time_used doesn't increase.
            # If action took time then failed (e.g., navigation collision simulation),
            # action_duration should reflect time until failure. (Current logic uses 0 on failure).
            time_used += action_duration

            # Log the result including success status
            action_log_info.add_result(
                actions=[prim_action],  # 현재 처리된 액션 추가
                action_full_name=prim_action,
                action_type=action_type,
                time_used=time_used,  # Cumulative time
                action_duration=action_duration,  # Duration of this step
                scene_positions=copy.deepcopy(scene_positions),  # State *after* attempt
                held_object=held_object,  # State *after* attempt
                success=action_success,  # Add success flag
            )

            # --- MODIFIED: Stop processing if an action failed ---
            if not action_success:
                log.warning(
                    f"Stopping action sequence simulation because action '{prim_action}' failed."
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
    ) -> Optional[Tuple[ActionSimulationLog, ActionSimulationLog]]:  # 반환 타입 명확화
        """
        Splits a sequence of actions based on a cutoff time using optimized re-simulation.
        Handles GRASP/PLACE pairs spanning the cutoff.
        Returns a tuple of two ActionSimulationLog objects (pre-cutoff, post-cutoff) if successful.
        Returns None if the initial full simulation fails or split is invalid.

        NOTE: Relies on the improved `_simulate_actions` internal simulation. The accuracy
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
            # Use the modified _simulate_actions which handles errors
            full_log = self._simulate_actions(full_sim_node, primitive_actions)
            # Check if simulation succeeded at all
            if not full_log or not full_log.results or not full_log.results[-1].success:
                log.error(
                    f"Full simulation failed or resulted in empty/failed log for actions: {primitive_actions}. Cannot split."
                )
                return None  # 실패 시 None 반환
        except (
            ValueError,
            NotImplementedError,
        ) as e:  # 시뮬레이션 중 발생 가능한 에러 처리
            log.error(f"Full simulation failed during split preparation: {e}")
            return None  # 실패 시 None 반환

        # (2) Determine split point based on cumulative time
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
            last_pre_result = full_log.results[-1]
            if last_pre_result.success and last_pre_result.held_object:
                grasped_object_in_pre = last_pre_result.held_object

        if grasped_object_in_pre and post_cutoff_actions:
            # --- 수정: PLACE 액션 존재 여부 검사 강화 ---
            # PLACE_INSIDE, PLACE_ON_TOP 모두 확인
            place_action_exists_in_post = any(
                action.upper().startswith("PLACE_") for action in post_cutoff_actions
            )
            if place_action_exists_in_post:
                log.error(
                    f"[_split_subtask_by_cutoff_time] Split occurs between GRASP('{grasped_object_in_pre}') "
                    f"in pre-cutoff and a PLACE action in post-cutoff. This is not allowed. Split failed."
                )
                return None, None

        # (5) Re-simulate final action lists
        # --- 수정: Re-simulation 제거, 기존 full_log 활용 ---
        # full_log는 이미 전체 시뮬레이션 결과를 담고 있으므로, 이를 분할하여 사용
        final_pre_log = ActionSimulationLog(results=full_log.results[: split_index + 1])

        final_post_log = None
        # post_cutoff_actions에 해당하는 결과만 추출하여 새로운 로그 생성
        if post_cutoff_actions:
            # post_results = full_log.results[split_index + 1:] # 이게 맞음
            final_post_log = ActionSimulationLog(
                results=full_log.results[split_index + 1 :]
            )
            log.debug(
                f"Post-cutoff log created with {len(final_post_log.results)} actions."
            )
            # post 로그의 첫 액션 시간은 pre 로그의 마지막 시간과 일치해야 함 (검증용)
            # if final_pre_log.results and final_post_log.results:
            #     if not math.isclose(final_pre_log.results[-1].time_used, final_post_log.results[0].time_used - final_post_log.results[0].action_duration, abs_tol=EPSILON):
            #         log.error("Time inconsistency between pre and post split logs!")
            #         return None
        else:
            # No post actions, create empty log
            final_post_log = ActionSimulationLog()

        # --- 수정: 튜플로 반환 ---
        return (final_pre_log, final_post_log)
        # --- 수정 끝 ---
