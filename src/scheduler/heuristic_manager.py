from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from src.models.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import LARGE_NUMBER, constants
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    NAV_STEP_DURATION,
    PLACE_ACTION_DURATION,
    TOGGLE_ACTION_DURATION,
)

if TYPE_CHECKING:
    from src.models.task import Subtask
    from src.scheduler.action_handler import ActionHandler

log = create_module_logger(__name__, True, logging.DEBUG)


class HeuristicManager:
    """
    Manages the calculation of heuristic costs for scheduling candidates.
    Evaluates immediate costs (navigation, urgency) and future costs (remaining workload).
    """

    def __init__(self, action_handler: "ActionHandler"):
        self.action_handler = action_handler
        self.alpha = constants.ALPHA_HEURISTIC
        self.beta = constants.BETA_HEURISTIC
        self.gamma = constants.GAMMA_HEURISTIC
        log.info(
            f"HeuristicManager initialized with weights: alpha={self.alpha}, beta={self.beta}, gamma={self.gamma}"
        )

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        all_candidates: List[Candidate],
    ) -> Tuple[int, float, float]:
        """
        Calculates the heuristic cost for a given candidate subtask.
        Returns: (risk_level, total_heuristic_cost)
        """

        # 1. Calculate Urgency & Risk
        risk_level, urgency_cost = self._calculate_candidate_risk_and_urgency(
            current_node, candidate
        )

        # 2. Calculate Future Workload Cost
        remaining_work_cost = self._calculate_remaining_work_cost(
            current_node, candidate
        )

        total_heuristic_cost = urgency_cost + remaining_work_cost

        log.info(
            f"  Heuristic for '{candidate.subtask.name}': Risk={risk_level}, "
            f"Urg({self.beta:.1f}*{urgency_cost:.2f})={self.beta * urgency_cost:.2f}, "
            f"RemWork({self.gamma:.1f}*Rem[{remaining_work_cost:.2f}])={self.gamma * remaining_work_cost:.2f}, "
        )
        log.info(
            f"  => Total Heuristic Cost for '{candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return risk_level, total_heuristic_cost

    # ========================================================================
    # Core Logic: Urgency & Risk Calculation
    # ========================================================================

    def _calculate_candidate_risk_and_urgency(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[int, float]:
        """
        Calculates risk and urgency
        """
        if not candidate.scheduling_due or candidate.scheduling_due.due_date == float(
            "inf"
        ):
            return 0, 0.0

        current_time = current_node.state.current_time
        deadline = candidate.scheduling_due.due_date

        # 1. Calculate Slack
        total_time_needed = self._estimate_total_time_needed(current_node, candidate)
        time_available = deadline - current_time
        slack = time_available - total_time_needed

        # 2. Map Slack to Base Risk & Cost
        if slack >= -constants.TIMING_TOLERANCE_ABS:
            return 0, slack
        else:
            return 2, 10000.0 + abs(slack)

    def _estimate_total_time_needed(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Estimates time needed for nav + interaction + lookahead return trip."""
        nav_time = candidate.estimated_first_nav_duration or 0.0
        chain_duration, _ = self._get_chain_info(current_node, candidate.subtask)

        # [Fix] If the deadline is for the candidate itself (Start Time Constraint),
        # we only need to arrive (Nav) by the deadline, not finish.
        is_target_self = (
            candidate.scheduling_due
            and candidate.scheduling_due.due_related_sub_name == candidate.subtask.name
        )

        if is_target_self:
            total_time = nav_time
        else:
            total_time = nav_time + chain_duration

        # Lookahead: Check if we need to return to a future critical task location
        future_crit_name = candidate.scheduling_due.due_related_sub_name
        if future_crit_name and future_crit_name != candidate.subtask.name:
            lookahead_time = self._calculate_lookahead_nav_time(
                current_node, candidate, future_crit_name
            )
            total_time += lookahead_time

        return total_time

    def _calculate_lookahead_nav_time(
        self, current_node: SimulationNode, candidate: Candidate, future_crit_name: str
    ) -> float:
        future_subtask = next(
            (
                t
                for t in current_node.state.remaining_subtasks
                if t.name == future_crit_name
            ),
            None,
        )
        if not future_subtask:
            return 0.0

        current_target_pos = self._get_task_interaction_location(
            candidate.subtask, current_node.state.scene_positions
        ) or tuple(current_node.state.scene_positions.get("agent", (0, 0, 0)))

        future_target_pos = self._get_task_interaction_location(
            future_subtask, current_node.state.scene_positions
        )

        return self._estimate_navigation_time_between_positions(
            current_target_pos, future_target_pos
        )

    # ========================================================================
    # Helper Functions - Future Workload (Volume, CP, MST)
    # ========================================================================

    def _get_chain_info(
        self, current_node: SimulationNode, start_subtask: Subtask
    ) -> Tuple[float, Set[str]]:
        """
        Calculates total duration and members of a critical chain starting from start_subtask.
        A chain is defined by consecutive tasks with Interval <= EPSILON.
        """
        total_duration = self._get_estimated_pure_interaction_time(start_subtask)
        curr_name = start_subtask.name
        chain_members = {curr_name}

        # [Added] Track current position to add navigation times within the chain
        curr_pos = self._get_task_interaction_location(
            start_subtask, current_node.state.scene_positions
        )

        while True:
            # Find immediate critical successor with zero interval
            next_name = None
            out_edges = current_node.state.constraints.out_edges(curr_name, data=True)
            for _, target, data in out_edges:
                info = data.get("info", {})
                # Check for critical chain link (IsCritical AND Interval ~ 0)
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) <= constants.EPSILON
                ):
                    next_name = target
                    break

            if next_name and next_name not in chain_members:
                chain_members.add(next_name)
                # Find the subtask object to get duration
                next_sub = next(
                    (
                        t
                        for t in current_node.state.remaining_subtasks
                        if t.name == next_name
                    ),
                    None,
                )
                if next_sub:
                    # 1. Add interaction duration
                    total_duration += self._get_estimated_pure_interaction_time(
                        next_sub
                    )

                    # 2. Add navigation duration (Chain internal travel)
                    next_pos = self._get_task_interaction_location(
                        next_sub, current_node.state.scene_positions
                    )
                    nav_time = self._estimate_navigation_time_between_positions(
                        curr_pos, next_pos
                    )
                    total_duration += nav_time

                    curr_name = next_name
                    curr_pos = next_pos  # Update position for next hop
                    continue
            break

        return total_duration, chain_members

    def _calculate_remaining_work_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Estimates cost of ALL remaining tasks after candidate."""
        chain_duration, chain_members = self._get_chain_info(
            current_node, candidate.subtask
        )

        # Simulate execution for next state
        exec_info = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )

        next_pos = tuple(exec_info.scene_positions.get("agent"))
        next_scene_pos = exec_info.scene_positions

        cp_duration = self._calculate_critical_path_interaction_duration(
            {
                t
                for t in current_node.state.remaining_subtasks
                if t.name not in chain_members
            },
            current_node.state.constraints,
            candidate.subtask,
        )

        mst_time = self._calculate_mst_navigation_time(
            next_pos, current_node.state.remaining_subtasks, next_scene_pos
        )

        return cp_duration + mst_time

    # ========================================================================
    # Helper Functions - Estimation & Graph
    # ========================================================================

    def _get_estimated_pure_interaction_time(self, subtask: Subtask) -> float:
        if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
            return 0.0
        if subtask.duration and subtask.duration.interval is not None:
            return max(0.0, subtask.duration.interval)

        duration_sum = 0.0
        if subtask.execution and subtask.execution.primitive_actions:
            for action_str in subtask.execution.primitive_actions:
                action_type = action_str.split(" ", 1)[0].upper()
                if action_type not in ["NAVIGATE_TO", "WAIT", "MONITORING"]:
                    duration_map = {
                        "GRASP": GRASP_ACTION_DURATION,
                        "PLACE_INSIDE": PLACE_ACTION_DURATION,
                        "PLACE_ON_TOP": PLACE_ACTION_DURATION,
                        "OPEN": TOGGLE_ACTION_DURATION,
                        "CLOSE": TOGGLE_ACTION_DURATION,
                        "TOGGLE_ON": TOGGLE_ACTION_DURATION,
                        "TOGGLE_OFF": TOGGLE_ACTION_DURATION,
                        "SLICE": TOGGLE_ACTION_DURATION,
                        "FILL": PLACE_ACTION_DURATION,
                    }
                    duration_sum += duration_map.get(
                        action_type, TOGGLE_ACTION_DURATION
                    )
        return duration_sum

    def _get_task_interaction_location(
        self, subtask: Subtask, scene_positions: dict[str, any]
    ) -> Optional[Tuple[float, float, float]]:
        if not subtask.execution or not subtask.execution.primitive_actions:
            return None

        # Priority: NAVIGATE target -> First Action target
        for action_str in subtask.execution.primitive_actions:
            tokens = action_str.split(" ", 2)
            if len(tokens) > 1:
                target_id = tokens[1]
                if target_id in scene_positions:
                    return tuple(scene_positions[target_id])
        return None

    def _estimate_navigation_time_between_positions(
        self,
        pos1: Optional[Tuple[float, float, float]],
        pos2: Optional[Tuple[float, float, float]],
    ) -> float:
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0
        path = self.action_handler._find_shortest_path(pos1, pos2)
        return len(path) * NAV_STEP_DURATION if path else 0.0

    def _calculate_critical_path_interaction_duration(
        self,
        remaining_tasks: Set[Subtask],
        constraints: nx.DiGraph,
        executed_subtask: Optional[Subtask],
    ) -> float:
        if not remaining_tasks:
            return 0.0

        task_names = {sub.name for sub in remaining_tasks}
        subgraph = constraints.subgraph(task_names).copy()

        # Pre-calculate durations
        durations = {
            t.name: self._get_estimated_pure_interaction_time(t)
            for t in remaining_tasks
        }

        earliest_finish = {name: 0.0 for name in task_names}

        for node in nx.topological_sort(subgraph):
            max_pred_finish = 0.0
            for pred, _, data in subgraph.in_edges(node, data=True):
                if pred in earliest_finish:
                    interval = data.get("info", {}).get("Interval", 0.0)
                    max_pred_finish = max(
                        max_pred_finish, earliest_finish[pred] + interval
                    )

            earliest_finish[node] = max_pred_finish + durations.get(node, 0.0)

        cp_duration = max(earliest_finish.values()) if earliest_finish else 0.0

        # Apply credit for starting a critical chain (Multi-hop supported)
        if executed_subtask and constraints.has_node(executed_subtask.name):
            discount = 0.0

            # BFS 탐색을 위한 큐 초기화
            queue = [executed_subtask.name]
            visited_chain = {executed_subtask.name}

            while queue:
                curr_node = queue.pop(0)

                for _, succ, data in constraints.out_edges(curr_node, data=True):
                    # 남은 작업 목록에 있고, Critical 연결인 경우만 고려
                    if succ in task_names and data.get("info", {}).get("IsCritical"):
                        interval = data.get("info", {}).get("Interval", 0.0)

                        if interval > constants.EPSILON:
                            # 유의미한 Interval(대기 시간) 발견 -> 할인 적용
                            discount += interval

                        # [Modified] Interval 유무와 상관없이 Critical Chain을 계속 탐색하여
                        # 연결된 모든 대기 시간을 할인(보상)에 포함시킵니다.
                        if succ not in visited_chain:
                            visited_chain.add(succ)
                            queue.append(succ)

            if discount > 0:
                cp_duration = max(0.0, cp_duration - discount)

        return cp_duration

    def _calculate_mst_navigation_time(
        self,
        current_agent_pos: Optional[Tuple[float, float, float]],
        remaining_tasks: Set[Subtask],
        scene_positions: dict[str, any],
    ) -> float:
        if not remaining_tasks:
            return 0.0

        locations = {current_agent_pos} if current_agent_pos else set()
        for t in remaining_tasks:
            loc = self._get_task_interaction_location(t, scene_positions)
            if loc:
                locations.add(loc)

        if len(locations) <= 1:
            return 0.0

        loc_list = list(locations)
        n = len(loc_list)
        dist_matrix = np.full((n, n), LARGE_NUMBER, dtype=float)

        for i in range(n):
            dist_matrix[i, i] = 0.0
            for j in range(i + 1, n):
                d = self._estimate_navigation_time_between_positions(
                    loc_list[i], loc_list[j]
                )
                dist_matrix[i, j] = dist_matrix[j, i] = d

        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import minimum_spanning_tree

        mst = minimum_spanning_tree(csr_matrix(dist_matrix))
        return mst.sum()
