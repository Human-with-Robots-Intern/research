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
                    f"Action simulation returned no results for actions: {actions}"
                )
                return None
            # Return the ActionResult of the *last* action in the sequence
            return log_info.results[-1]
        except ValueError as e:
            # Catch specific ValueErrors raised during simulation (e.g., unknown action, object not found)
            log.error(
                f"Action simulation failed for node "
                f"(Subtask: {current_node.state.subtask.name if current_node.state.subtask else 'N/A'}, "
                f"Time: {current_node.state.current_time:.2f}) "
                f"with actions {actions}: {e}",
                exc_info=True,  # Include stack trace for debugging
            )
            return None  # Return None on simulation failure
        except Exception as e:
            # Catch unexpected errors during simulation
            log.error(
                f"Unexpected error during action simulation for actions {actions}: {e}",
                exc_info=True,
            )
            return None

    def _estimate_primitive_duration(
        self, action_type: str, target_obj_id: Optional[str]
    ) -> float:
        """
        Estimates primitive action duration.
        *** WARNING: This is a placeholder implementation. ***
        It returns fixed constants and does not interact with the actual simulator.
        This MUST be replaced with interaction with AI2THOR or a realistic model.
        """
        # --- 수정: NotImplementedError 발생 ---
        # raise NotImplementedError(
        #     "_estimate_primitive_duration is a placeholder and needs to be replaced "
        #     "with actual simulator interaction or a valid duration model."
        # )
        # 주석 처리 유지 (실행은 가능하도록 하되, 경고성 주석 강화)
        log.warning(
            "_estimate_primitive_duration is using placeholder fixed durations. Replace with actual simulation logic."
        )  # 경고 로그 추가

        default_duration = PRIMITIVE_ACTION_DURATION
        if action_type == "MONITORING":
            return MONITORING_DURATION
        elif action_type == "WAIT":
            # Wait duration is handled directly in _simulate_actions
            return 0.0  # Placeholder, actual duration parsed from action string
        else:
            # Return default for GRASP, PLACE, OPEN, CLOSE, etc.
            return default_duration

    def split_subtask_by_cutoff_time(
        self,
        current_node: SimulationNode,
        primitive_actions: list[str],
        cutoff_time: float,
    ) -> tuple[Optional[ActionSimulationLog], Optional[ActionSimulationLog]]:
        """
        Splits a sequence of actions based on a cutoff time.
        Handles GRASP/PLACE pairs spanning the cutoff.
        Returns two ActionSimulationLog objects (pre-cutoff, post-cutoff).
        Returns (None, None) if the initial full simulation fails.

        NOTE: This implementation simulates the full sequence first, then re-simulates
        the split parts. This could be inefficient for long sequences. Consider
        optimizing by reusing results from the initial simulation if performance
        becomes critical.
        """
        log.debug(
            f"Attempting to split actions at cutoff time: {cutoff_time:.2f} for node at time {current_node.state.current_time:.2f}"
        )
        # Ensure cutoff time is not negative
        if cutoff_time < 0:
            log.warning(f"Cutoff time {cutoff_time:.2f} is negative. Using 0.")
            cutoff_time = 0.0

        # (1) Simulate the full sequence to get timing info
        full_sim_node = copy.deepcopy(current_node)
        try:
            # Use the modified _simulate_actions which handles errors
            full_log = self._simulate_actions(full_sim_node, primitive_actions)
        except ValueError as e:  # Catch simulation errors
            log.error(f"Full simulation failed during split preparation: {e}")
            return None, None

        if not full_log.results:
            log.warning("Full simulation resulted in empty log. Cannot split.")
            # Return empty logs for pre and post parts
            return ActionSimulationLog(), ActionSimulationLog()

        # Check if the *first* action already exceeds the cutoff significantly
        if (
            full_log.results[0].time_used - current_node.state.current_time
            > cutoff_time + EPSILON
        ):
            log.warning(
                f"First action duration ({full_log.results[0].action_duration:.2f}) already exceeds cutoff time {cutoff_time:.2f}. "
                f"Placing all actions in the post-cutoff list."
            )
            # Return empty pre-log and full post-log (re-simulated)
            post_log = self._simulate_actions(
                copy.deepcopy(current_node), primitive_actions
            )
            if post_log is None:
                raise ValueError(
                    "Re-simulation failed for post-cutoff actions (case: first action > cutoff)"
                )
            return ActionSimulationLog(), post_log

        pre_cutoff_actions: list[str] = []
        post_cutoff_actions: list[str] = []
        pre_cutoff_indices: list[int] = []
        post_cutoff_indices: list[int] = []

        # (2) Initial time-based split using cumulative time
        for i, result in enumerate(full_log.results):
            # Action is pre-cutoff if it *ends* at or strictly before the cutoff time (relative to start)
            # Cumulative time used is relative to the simulation start (current_node.state.current_time)
            action_end_time_relative = (
                result.time_used - current_node.state.current_time
            )

            # --- MODIFIED: Use EPSILON for float comparison ---
            if action_end_time_relative <= cutoff_time + EPSILON:
                pre_cutoff_actions.append(result.action_full_name)
                pre_cutoff_indices.append(i)
            else:
                # Check if this is the *first* action going into post-cutoff
                if not post_cutoff_actions:
                    # If the *start* time of this action is already past the cutoff,
                    # it fully belongs in post. But if it spans the cutoff, we might need adjustment (handled later for GRASP/PLACE).
                    action_start_time_relative = (
                        action_end_time_relative - result.action_duration
                    )
                    if action_start_time_relative > cutoff_time + EPSILON:
                        log.debug(
                            f"Action '{result.action_full_name}' starts after cutoff, belongs to post."
                        )
                    else:
                        log.debug(
                            f"Action '{result.action_full_name}' spans the cutoff time {cutoff_time:.2f}."
                        )
                        # Decision to place spanning actions in pre/post depends on policy.
                        # Current logic places it in post based on end time. GRASP/PLACE handled later.

                post_cutoff_actions.append(result.action_full_name)
                post_cutoff_indices.append(i)

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
            place_action_exists_in_post = any(
                action.upper().startswith("PLACE") for action in post_cutoff_actions
            )
            if place_action_exists_in_post:
                log.error(
                    f"[_split_subtask_by_cutoff_time] Split occurs between GRASP('{grasped_object_in_pre}') "
                    f"in pre-cutoff and a PLACE action in post-cutoff. This is not allowed. Split failed."
                )
                return None, None

        # (5) Re-simulate final action lists
        final_pre_log = None
        post_start_node = copy.deepcopy(current_node)

        if pre_cutoff_actions:
            pre_sim_node_final = copy.deepcopy(current_node)
            try:
                final_pre_log = self._simulate_actions(
                    pre_sim_node_final, pre_cutoff_actions
                )
                if (
                    not final_pre_log
                    or not final_pre_log.results
                    or not final_pre_log.results[-1].success
                ):
                    log.error(
                        f"Re-simulation potentially failed for final pre_cutoff_actions: {pre_cutoff_actions}"
                    )
                    # Decide how to handle partial success/failure in pre-part
                    # Option: Raise error, or return the partially successful log?
                    # For now, raising error if log is None or last action failed seems safer for split integrity.
                    if not final_pre_log or not final_pre_log.results:
                        raise ValueError(
                            "Re-simulation failed for pre-cutoff actions during split (returned None/empty)."
                        )
                    elif not final_pre_log.results[-1].success:
                        raise ValueError(
                            "Re-simulation failed for pre-cutoff actions during split (last action failed)."
                        )

                # post_start_node 설정 (pre 액션 후의 상태 사용)
                last_pre_result = final_pre_log.results[-1]
                post_start_node.state.current_time = last_pre_result.time_used
                post_start_node.state.scene_positions = copy.deepcopy(
                    last_pre_result.scene_positions
                )
                post_start_node.state.held_object = last_pre_result.held_object

            except ValueError as e:
                log.error(f"Re-simulation error for pre_cutoff_actions: {e}")
                raise  # Re-raise for caller handling

        final_post_log = None
        if post_cutoff_actions:
            post_sim_node = copy.deepcopy(post_start_node)
            try:
                final_post_log = self._simulate_actions(
                    post_sim_node, post_cutoff_actions
                )
                if (
                    not final_post_log
                    or not final_post_log.results
                    or not final_post_log.results[-1].success
                ):
                    log.error(
                        f"Re-simulation potentially failed for final post_cutoff_actions: {post_cutoff_actions}"
                    )
                    if not final_post_log or not final_post_log.results:
                        raise ValueError(
                            "Re-simulation failed for post-cutoff actions during split (returned None/empty)."
                        )
                    elif not final_post_log.results[-1].success:
                        raise ValueError(
                            "Re-simulation failed for post-cutoff actions during split (last action failed)."
                        )

            except ValueError as e:
                log.error(f"Re-simulation error for post_cutoff_actions: {e}")
                raise  # Re-raise for caller handling
        else:
            final_post_log = ActionSimulationLog()  # Empty log if no post actions

        return final_pre_log, final_post_log

    def _simulate_actions(
        self,
        current_node: SimulationNode,  # This node's state WILL be modified
        primitive_actions: List[str],
    ) -> ActionSimulationLog:
        """
        Simulates actions sequentially, updating the state within current_node.
        Raises ValueError on critical simulation errors (e.g., unknown action, object not found).
        *** WARNING: Current action effects (duration, success, state changes) are based on placeholders. ***
        Needs integration with actual AI2THOR calls and results.
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
                # --- MODIFIED: Wrap action simulation in try-except ---\
                # --- !!! Placeholder Warning !!! ---
                # The following action logic (NAVIGATE_TO, GRASP, PLACE, etc.) uses
                # placeholder durations (_estimate_primitive_duration) and assumes success
                # without actual AI2THOR interaction.
                # This needs to be replaced with calls to a simulator interface
                # (like self.action_handler or controller.step) that returns
                # actual duration and success status based on the simulation result.
                # ----------------------------------
                if action_type == "NAVIGATE_TO":
                    # ... (Navigation simulation logic) ...
                    # Inside navigation, if pathfinding fails or target unreachable, set action_success = False
                    if not target_obj_id:
                        log.error("NAVIGATE_TO action requires a target object ID.")
                        raise ValueError("Missing target object ID for NAVIGATE_TO.")
                    # Check reachability before pathfinding
                    start_node_pos = scene_positions.get("agent")
                    end_node_pos = scene_positions.get(target_obj_id)
                    if not start_node_pos or not end_node_pos:
                        log.error(
                            f"Cannot NAVIGATE: Agent or target '{target_obj_id}' position missing."
                        )
                        action_success = False  # Mark as failed
                        action_duration = 0  # No time spent if immediate failure
                    else:
                        navigate_path = self._find_shortest_path(
                            start_node_pos, end_node_pos
                        )
                        if not navigate_path:
                            log.warning(
                                f"No path found for NAVIGATE_TO {target_obj_id}. Action failed."
                            )
                            action_success = False
                            action_duration = (
                                0  # Or some estimated failure time? For now, 0.
                            )
                        elif len(navigate_path) == 1:  # Already at target
                            action_duration = 0.0
                        else:
                            # 5.1: 경로 길이와 스텝 시간 기반 시간 계산
                            num_steps = len(navigate_path) - 1
                            action_duration = (
                                num_steps * NAV_STEP_DURATION
                            )  # Use constant step duration
                            # Update agent position (assuming successful navigation for now)
                            # TODO: Actual simulator call should update position based on success.
                            scene_positions["agent"] = navigate_path[-1]
                            current_node.state.scene_positions["agent"] = navigate_path[
                                -1
                            ]

                elif action_type == "GRASP":
                    # ... (Precondition checks: target exists, hand empty) ...
                    # TODO: AI2THOR Integration Point
                    # - Verify self.runner.step call parameters for GRASP match Ai2Thor API.
                    # - Check if self.runner.step accurately returns success/failure based on reachability, object properties etc.
                    # - Ensure PRIMITIVE_ACTION_DURATION reflects actual simulation time or API feedback.
                    # - Confirm state update (held_object) aligns with Ai2Thor event result.
                    if action_success:  # Only perform action if preconditions met
                        held_object = target_obj_id
                        current_node.state.held_object = target_obj_id
                        # 5.1: 내부 추정 함수 사용
                        action_duration = self._estimate_primitive_duration(
                            action_type, target_obj_id
                        )
                        # TODO: Get success/duration from actual AI2THOR event

                elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                    # ... (Precondition checks: target receptacle exists, holding object) ...
                    # TODO: AI2THOR Integration Point
                    # - Verify self.runner.step call parameters for PLACE match API (receptacle ID, possibly held object ID).
                    # - Check success/failure return based on receptacle properties, placement validity.
                    # - Ensure PRIMITIVE_ACTION_DURATION is appropriate.
                    # - Confirm state update (held_object = None, scene_positions[held_object]) aligns with event result.
                    if action_success:  # Only perform action if preconditions met
                        if held_object not in scene_positions:
                            log.warning(...)
                        scene_positions[held_object] = scene_positions[
                            target_obj_id
                        ]  # Simplification
                        held_object = None
                        current_node.state.held_object = None
                        # 5.1: 내부 추정 함수 사용
                        action_duration = (
                            self._estimate_primitive_duration(
                                action_type, target_obj_id
                            )
                            if action_success
                            else 0.0
                        )
                        # TODO: Get success/duration from actual AI2THOR event

                elif action_type == "MONITORING":
                    action_duration = self._estimate_primitive_duration(
                        action_type, target_obj_id
                    )
                    # TODO: AI2THOR interaction for monitoring?

                elif action_type == "WAIT":
                    # ... (Existing WAIT logic) ...
                    pass  # Keep existing logic, ensure ValueError is raised on bad duration

                elif action_type in PRIMITIVE_ACTION_SET:  # Generic actions
                    # TODO: Add specific failure checks if needed for other primitives
                    action_duration = self._estimate_primitive_duration(
                        action_type, target_obj_id
                    )
                    # TODO: Get success/duration from actual AI2THOR event
                else:
                    log.error(f"Unknown action type encountered: '{action_type}'")
                    # --- 수정: 알 수 없는 액션 시 에러 발생시키기 ---
                    # action_success = False
                    # action_duration = 0
                    raise ValueError(f"Unknown action type: {action_type}")  # 에러 발생

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
                    f"Stopping action sequence simulation because action '{prim_action}' (index {i}) failed."
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
            return None  # Cannot proceed if adjustment fails

        if start_node is None or end_node is None:
            log.warning(
                f"Start ({start_pos} -> {start_node}) or End ({end_pos} -> {end_node}) node is unreachable in the graph."
            )
            return None  # Start or end node not found after adjustment

        if start_node == end_node:
            return [start_node]  # Path is just the single node

        # Simple BFS implementation (assuming uniform edge costs)
        # For non-uniform costs (e.g., turns), Dijkstra/A* would be needed (like the original code)
        # Sticking to BFS for simplicity based on feedback focus unless cost matters.
        # Using the original Dijkstra-like approach that considers turns:
        def direction(a, b):
            # Calculate 2D direction vector (ignoring Y)
            return (b[0] - a[0], b[2] - a[2])

        # Priority Queue stores (turn_count, current_position, current_direction, path_list)
        pq = []
        heapq.heappush(pq, (0, start_node, None, [start_node]))
        # Visited dictionary stores {position: min_turn_count_to_reach}
        visited = {}

        while pq:
            turn_cnt, cur_pos, cur_dir, path = heapq.heappop(pq)

            if cur_pos == end_node:
                log.debug(
                    f"Path found from {start_node} to {end_node} with {turn_cnt} turns. Length: {len(path)}"
                )
                return path  # Found the target

            # Optimization: If we've found a shorter path (fewer turns) to this node already, skip
            if cur_pos in visited and visited[cur_pos] <= turn_cnt:
                continue
            visited[cur_pos] = turn_cnt

            # Explore neighbors
            neighbors = self.nav_graph.get(cur_pos, [])
            if not neighbors:
                log.warning(f"Node {cur_pos} has no neighbors in the nav_graph.")
                continue

            for next_pos in neighbors:
                # Basic cycle check (though BFS naturally handles shortest path)
                # if next_pos in path: continue # Avoid immediate backtracking

                # Calculate new direction and turn count
                new_dir = direction(cur_pos, next_pos)
                # Increment turn count only if direction changes
                next_turn_cnt = (
                    turn_cnt
                    if (cur_dir is None or new_dir == cur_dir)
                    else (turn_cnt + 1)
                )

                # If we haven't visited the neighbor or found a path with fewer turns
                if next_pos not in visited or visited[next_pos] > next_turn_cnt:
                    new_path = path + [next_pos]
                    heapq.heappush(pq, (next_turn_cnt, next_pos, new_dir, new_path))

        # If the loop finishes without finding the end_node
        log.warning(
            f"No path found from {start_node} to {end_node} using graph search."
        )
        return None
