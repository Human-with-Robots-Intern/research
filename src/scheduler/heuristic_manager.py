from __future__ import annotations

import copy
import logging
import math
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import networkx as nx

# from scipy.sparse import csr_matrix # MST 계산에 필요할 수 있음
# from scipy.sparse.csgraph import minimum_spanning_tree # MST 계산에 필요할 수 있음
import numpy as np  # 거리 계산 등에 사용될 수 있음

from src.core.dataclass import ActionResult, Candidate, SimulationNode
from src.utils.config import (  # INIT_PRIOR_MEAN, # 더 이상 직접 사용하지 않거나, interaction 추정에 활용
    ALPHA_HEURISTIC,
    BETA_HEURISTIC,
    EPSILON,
    GAMMA_HEURISTIC,
    LARGE_NUMBER,
)
from utils.config.constants import NAV_STEP_DURATION

# Forward declarations for type hinting
if TYPE_CHECKING:
    from src.core.agent import Agent
    from src.core.task import Subtask
    from src.scheduler.action_handler import ActionHandler
    from src.scheduler.constraint_handler import ConstraintHandler

log = logging.getLogger(__name__)


class HeuristicManager:
    """
    개선된 휴리스틱 매니저: 가상 다음 상태 기반 CP + MST 전략 사용

    비용 = alpha * 후보_네비게이션_비용
           + beta * 후보_긴급도_비용
           + gamma * (미래_CP_상호작용_시간 + 미래_MST_이동_시간)
    """

    def __init__(
        self,
        constraint_handler: "ConstraintHandler",
        action_handler: "ActionHandler",
        agent: Optional["Agent"] = None,
    ):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.agent = agent  # Agent 정보를 활용하여 상호작용 시간 등 추정 가능

        self.alpha = ALPHA_HEURISTIC
        self.beta = BETA_HEURISTIC
        self.gamma = GAMMA_HEURISTIC

    # ========================================================================
    # Helper Functions
    # ========================================================================

    def _get_estimated_interaction_time(self, subtask: Subtask) -> float:
        """
        Subtask의 순수 상호작용 시간 추정 (네비게이션 제외).
        Agent 지식 또는 기본값 사용 가능.
        """
        # TODO: Agent의 경험/지식을 바탕으로 더 정확한 추정치 제공
        # 예: self.agent.get_estimated_interaction_time(subtask)
        # 현재는 sub.duration.interval을 그대로 사용하거나, 특정 유형에 따라 조정
        if subtask.duration and subtask.duration.interval is not None:
            # 네비게이션/대기 유형은 상호작용 시간을 0으로 간주할 수 있음
            if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
                return 0.0
            return subtask.duration.interval
        else:
            log.warning(
                f"Subtask '{subtask.name}' has no duration info. Estimating interaction time as 0."
            )
            # 기본값 필요 시 설정 (e.g., PRIMITIVE_ACTION_DURATION)
            return 0.0  # 기본값 0

    def _get_task_start_location(
        self, subtask: Subtask, scene_positions: dict
    ) -> Optional[tuple]:
        """Helper to get the target location of the first relevant action (NAV or interaction target)."""
        if not subtask.execution or not subtask.execution.primitive_actions:
            return None
        first_action = subtask.execution.primitive_actions[0]
        tokens = first_action.split(" ", 2)
        action_type = tokens[0].upper()
        target_obj_id = tokens[1] if len(tokens) > 1 else None

        if action_type == "NAVIGATE_TO":
            if target_obj_id and target_obj_id in scene_positions:
                return tuple(scene_positions[target_obj_id])
            else:
                log.warning(
                    f"Navigation target '{target_obj_id}' for task '{subtask.name}' not in scene_positions."
                )
                return None
        elif target_obj_id:  # Interaction actions might have a target
            if target_obj_id in scene_positions:
                return tuple(scene_positions[target_obj_id])
            else:
                # Target for interaction not found? Need specific policy
                log.warning(
                    f"Interaction target '{target_obj_id}' for task '{subtask.name}' not in scene_positions."
                )
                return None
        else:  # Action without a specific target location (e.g., WAIT)
            return None  # Assume no specific location needed

    def _estimate_nav_time(self, pos1: tuple, pos2: tuple) -> float:
        """Estimate navigation time between two positions using ActionHandler."""
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0
        try:
            # 경로 탐색 실패 시 큰 값 반환 또는 예외 처리 필요
            path = self.action_handler._find_shortest_path(pos1, pos2)
            return len(path) * NAV_STEP_DURATION
        except ValueError:
            log.warning(
                f"Pathfinding failed between {pos1} and {pos2}. Returning large nav time."
            )
            return LARGE_NUMBER  # 경로 없음 = 이동 불가

    def _calculate_critical_path_duration(
        self, remaining_tasks: Set[Subtask], constraints: nx.DiGraph
    ) -> float:
        """
        Calculate the duration of the critical path considering interaction times and intervals.
        Uses Earliest Finish time calculation based on topological sort.
        """
        if not remaining_tasks:
            return 0.0

        task_interaction_times = {
            sub.name: self._get_estimated_interaction_time(sub)
            for sub in remaining_tasks
        }

        # Filter constraints graph to only include remaining tasks
        subgraph_nodes = {sub.name for sub in remaining_tasks}
        subgraph = constraints.subgraph(
            subgraph_nodes
        ).copy()  # Create a copy to work with

        if not nx.is_directed_acyclic_graph(subgraph):
            log.error(
                "Cycle detected in remaining task constraint subgraph! Cannot calculate CP."
            )
            # 정책: 사이클 시 매우 큰 값 반환
            return LARGE_NUMBER

        # Standard CPM Algorithm (Earliest Finish Time)
        earliest_finish = {task_name: 0.0 for task_name in subgraph_nodes}
        try:
            # Use topological sort for processing order
            for task_name in nx.topological_sort(subgraph):
                max_pred_ef = 0.0
                # Consider predecessors within the subgraph
                for pred_name, _, edge_data in subgraph.in_edges(task_name, data=True):
                    # Ensure predecessor is processed
                    if pred_name in earliest_finish:
                        interval = edge_data.get("info", {}).get("Interval", 0.0)
                        # EF(pred) + interval
                        max_pred_ef = max(
                            max_pred_ef, earliest_finish[pred_name] + interval
                        )
                    else:
                        # This case might happen if subgraph is disconnected? Handle robustly.
                        log.warning(
                            f"Predecessor '{pred_name}' not found in EF dict for task '{task_name}'. Constraint graph might be invalid or disconnected."
                        )

                # EF(task) = max(EF(preds) + interval) + interaction_time(task)
                interaction_time = task_interaction_times.get(task_name, 0.0)
                earliest_finish[task_name] = max_pred_ef + interaction_time

            # The critical path duration is the maximum EF among all tasks
            max_ef = max(earliest_finish.values()) if earliest_finish else 0.0
            log.debug(
                f"  Calculated Critical Path Duration (Interaction + Interval): {max_ef:.2f}"
            )
            return max_ef

        except nx.NetworkXUnfeasible:  # Cycle detected by topological_sort
            log.error("Cycle detected during topological sort! Cannot calculate CP.")
            return LARGE_NUMBER

    def _calculate_mst_nav_time(
        self, agent_pos: tuple, remaining_tasks: Set[Subtask], scene_positions: dict
    ) -> float:
        """Estimates total navigation time for remaining tasks using MST."""
        if not remaining_tasks:
            return 0.0

        # 1. Collect relevant locations
        locations = {agent_pos} if agent_pos else set()
        task_locations = []
        for sub in remaining_tasks:
            loc = self._get_task_start_location(sub, scene_positions)
            if loc:
                locations.add(loc)
                task_locations.append(loc)  # Keep track of task-specific locs if needed

        if len(locations) <= 1:  # Agent pos only, or agent + 1 task at same loc
            return 0.0

        location_list = list(locations)
        loc_to_index = {loc: i for i, loc in enumerate(location_list)}
        num_locations = len(location_list)
        dist_matrix = np.full((num_locations, num_locations), LARGE_NUMBER, dtype=float)
        np.fill_diagonal(dist_matrix, 0.0)  # Distance to self is 0

        # 2. Calculate pairwise navigation times (Edge weights for MST)
        # This is the most computationally expensive part
        for i in range(num_locations):
            for j in range(i + 1, num_locations):
                pos1 = location_list[i]
                pos2 = location_list[j]
                nav_time = self._estimate_nav_time(pos1, pos2)
                dist_matrix[i, j] = nav_time
                dist_matrix[j, i] = nav_time  # Symmetric graph

        # 3. Calculate MST weight
        try:
            # Using SciPy for MST calculation (requires scipy installed)
            # If SciPy is not available, need a custom Prim/Kruskal implementation
            from scipy.sparse import csr_matrix
            from scipy.sparse.csgraph import minimum_spanning_tree

            graph_sparse = csr_matrix(dist_matrix)
            mst = minimum_spanning_tree(graph_sparse)
            mst_weight = mst.sum()

            if mst_weight >= LARGE_NUMBER:
                log.warning(
                    "MST calculation resulted in a large weight, possibly due to unreachable locations."
                )
                # Return large number to indicate potential infeasibility
                return LARGE_NUMBER

            log.debug(f"  Calculated MST Navigation Time: {mst_weight:.2f}")
            return mst_weight

        except ImportError:
            log.error(
                "SciPy not found. Cannot calculate MST using SciPy. Implement Prim/Kruskal or install SciPy."
            )
            # Fallback: Approximate using sum of min distances from agent? Very rough.
            min_dist_sum = 0.0
            if agent_pos:
                for loc in task_locations:
                    min_dist_sum += self._estimate_nav_time(agent_pos, loc)
                log.warning(
                    f"Falling back to sum of min distances from agent: {min_dist_sum:.2f}"
                )
                return min_dist_sum
            else:
                return LARGE_NUMBER  # Cannot estimate without agent pos and SciPy

    # ========================================================================
    # Main Heuristic Calculation
    # ========================================================================

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> float:
        """
        Calculates the heuristic cost for selecting the candidate subtask.
        Considers candidate's nav cost, urgency, and estimated cost of remaining work.
        """
        log.debug(f"Calculating heuristic for candidate: {candidate.subtask.name}")

        # -------------------------------------------------
        # 1. Cost related to the candidate itself
        # -------------------------------------------------
        # (a) Navigation cost to start the candidate
        nav_cost_candidate = self._calculate_navigation_cost(current_node, candidate)

        # (b) Urgency cost of the candidate
        urgency_cost_candidate, slack_val = self._calculate_urgency_cost(
            current_node, candidate
        )

        # Early exit if candidate itself is infeasible
        if nav_cost_candidate >= LARGE_NUMBER or urgency_cost_candidate >= LARGE_NUMBER:
            log.warning(
                f"Candidate '{candidate.subtask.name}' deemed infeasible due to large nav ({nav_cost_candidate:.2f}) or urgency ({urgency_cost_candidate:.2f}, slack {slack_val:.2f}). Returning LARGE_NUMBER."
            )
            return LARGE_NUMBER

        # -------------------------------------------------
        # 2. Estimate cost of remaining work *after* the candidate
        # -------------------------------------------------
        # (a) Simulate candidate execution to get virtual next state info
        candidate_sim_info: Optional[ActionResult] = (
            self.action_handler.get_actions_info(
                current_node, candidate.subtask.execution.primitive_actions
            )
        )

        if not candidate_sim_info or not candidate_sim_info.success:
            log.warning(
                f"Simulation of candidate '{candidate.subtask.name}' failed. Treating remaining cost as high."
            )
            # If candidate fails, this path is likely bad
            remaining_work_cost = LARGE_NUMBER
        else:
            # Virtual state after candidate execution
            next_agent_pos = tuple(candidate_sim_info.scene_positions.get("agent"))
            next_remaining_tasks = {
                sub
                for sub in current_node.state.remaining_subtasks
                if sub.name != candidate.subtask.name
            }
            next_constraints = (
                current_node.state.constraints
            )  # Assume constraints don't change by single candidate execution for heuristic
            next_scene_positions = (
                candidate_sim_info.scene_positions
            )  # Needed for start locations

            # (b) Calculate Critical Path duration (interaction + interval) for next state
            critical_interaction_duration = self._calculate_critical_path_duration(
                next_remaining_tasks, next_constraints
            )

            # (c) Calculate MST navigation time for next state
            mst_nav_time = self._calculate_mst_nav_time(
                next_agent_pos, next_remaining_tasks, next_scene_positions
            )

            # (d) Combine remaining work cost components
            if (
                critical_interaction_duration >= LARGE_NUMBER
                or mst_nav_time >= LARGE_NUMBER
            ):
                remaining_work_cost = LARGE_NUMBER
                log.warning(
                    f"Estimated remaining work cost is large (CP={critical_interaction_duration:.2f}, MST={mst_nav_time:.2f})."
                )
            else:
                remaining_work_cost = critical_interaction_duration + mst_nav_time

        # -------------------------------------------------
        # 3. Combine all costs with weights
        # -------------------------------------------------
        total_cost = (
            self.alpha * nav_cost_candidate
            + self.beta * urgency_cost_candidate
            + self.gamma * remaining_work_cost
        )

        log.debug(
            f"  Heuristic Costs for '{candidate.subtask.name}': CandNav={nav_cost_candidate:.3f}, CandUrg={urgency_cost_candidate:.3f} (Slack={slack_val:.2f}), RemWork={remaining_work_cost:.3f}"
        )
        log.debug(
            f"  Total Weighted Cost: {total_cost:.4f} (alpha={self.alpha:.2f}, beta={self.beta:.2f}, gamma={self.gamma:.2f})"
        )

        # Final checks for sanity
        if total_cost >= LARGE_NUMBER:
            log.warning(
                f"Final total cost is LARGE_NUMBER for '{candidate.subtask.name}'."
            )
            return LARGE_NUMBER
        if total_cost < 0:
            log.error(
                f"Negative total heuristic cost ({total_cost:.4f})! Returning 0.0."
            )
            return 0.0

        return total_cost

    # ========================================================================
    # Existing Helper Functions (Potentially needing minor adjustments)
    # ========================================================================

    def _calculate_navigation_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Calculates the navigation time required to start the candidate's first action."""
        if (
            not candidate.subtask.execution
            or not candidate.subtask.execution.primitive_actions
        ):
            log.debug(
                f"  Candidate '{candidate.subtask.name}' has no actions. Nav cost: 0.0"
            )
            return 0.0

        first_action = candidate.subtask.execution.primitive_actions[0]

        # Only consider NAVIGATE_TO for direct nav cost, others assume start at current pos?
        if not first_action.startswith("NAVIGATE_TO"):
            log.debug(
                f"  First action for '{candidate.subtask.name}' is not NAVIGATE_TO ({first_action}). Treating nav cost as 0."
            )
            return 0.0

        # Simulate only the first action for nav time
        sim_result = self.action_handler.get_actions_info(current_node, [first_action])

        if sim_result and sim_result.success:
            nav_time = sim_result.action_duration
            log.debug(f"  Navigation Cost (Candidate Nav Time): {nav_time:.2f}")
            return nav_time
        else:
            log.warning(
                f"  Navigation simulation failed for first action of '{candidate.subtask.name}'. Returning LARGE_NUMBER nav cost."
            )
            return LARGE_NUMBER  # Failed navigation means infeasible

    def _calculate_urgency_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> tuple[float, float]:
        """
        Calculates urgency cost based on slack time relative to the candidate's deadline.
        Returns (urgency_cost, slack_value).
        """
        # Check for finite deadline
        if not candidate.deadline or candidate.deadline.due_date == float("inf"):
            # log.debug("  No finite deadline. Urgency Cost: 0.0, Slack: inf")
            return 0.0, float("inf")

        current_time = current_node.state.current_time
        deadline_time = candidate.deadline.due_date
        deadline_reason = candidate.deadline.subtask_name
        # log.debug(f"  Deadline detected: {deadline_time:.2f} (due to '{deadline_reason}')")

        # 1. Estimate candidate execution time
        candidate_sim_info = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )
        if not candidate_sim_info or not candidate_sim_info.success:
            log.warning(
                f"  Urgency: Candidate '{candidate.subtask.name}' simulation failed. Assigning high urgency cost."
            )
            return LARGE_NUMBER, -float(
                "inf"
            )  # Indicate failure with negative infinite slack

        candidate_exec_time = (
            candidate_sim_info.action_duration
        )  # Use action_duration for single subtask estimate? Or cumulative_time? Check action_handler logic. Let's assume cumulative_time is for the whole sequence if multiple actions.
        # Assuming get_actions_info returns cumulative for the sequence passed.
        candidate_exec_time = candidate_sim_info.cumulative_time

        # --- Slack Calculation Refinement ---
        # Slack = Time Available - Time Needed
        # Time Available = deadline_time - current_time
        # Time Needed = candidate_exec_time (assuming deadline applies directly to this candidate finishing)
        # If deadline is due to a *subsequent* task, we might need nav time to that task as well,
        # but the current Candidate object structure links deadline directly. Let's stick to that.

        time_available = deadline_time - current_time
        time_needed = candidate_exec_time
        slack_val = time_available - time_needed

        # log.debug(f"  Urgency Calc: Deadline={deadline_time:.2f}, Current={current_time:.2f}, Available={time_available:.2f}")
        # log.debug(f"    Time Needed (CandExec) = {time_needed:.2f}")
        # log.debug(f"    Calculated Slack = {slack_val:.2f}")

        # 4. Calculate urgency cost
        urgency_cost = 0.0
        if slack_val <= EPSILON:  # Includes negative slack (deadline missed)
            # log.warning(f"  Urgency Alert for '{candidate.subtask.name}': Slack {slack_val:.2f} <= {EPSILON}. High urgency cost.")
            # Use beta * LARGE_NUMBER for very high cost, but ensure consistency
            urgency_cost = (
                LARGE_NUMBER  # Assign large number directly if slack is non-positive
            )
        else:
            # Urgency is inversely proportional to slack
            urgency_term = 1.0 / (
                slack_val + EPSILON
            )  # Add EPSILON for safety near zero
            urgency_cost = urgency_term  # Let beta handle the scaling in the final sum

            # log.debug(f"  Calculated urgency term: {urgency_term:.3f}, Urgency Cost (before beta): {urgency_cost:.3f}")

        # Return cost before applying beta, and the calculated slack
        return urgency_cost, slack_val
