from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

import networkx as nx
import numpy as np  # 거리 계산 등에 사용될 수 있음

from src.models.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import (  # INIT_PRIOR_MEAN, # 더 이상 직접 사용하지 않거나, interaction 추정에 활용
    LARGE_NUMBER,
    constants,
)
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    NAV_STEP_DURATION,
    PLACE_ACTION_DURATION,
    TOGGLE_ACTION_DURATION,
)

# Forward declarations for type hinting
if TYPE_CHECKING:
    from src.models.task import Subtask
    from src.scheduler.action_handler import ActionHandler
log = create_module_logger(__name__, True, logging.DEBUG)


class HeuristicManager:
    """
    Manages the calculation of heuristic costs for scheduling candidates.

    This class evaluates the cost of selecting a particular subtask candidate
    at a given state. The cost is a weighted sum of various factors designed
    to guide the scheduler towards an optimal solution. It considers immediate
    costs (like navigation) and estimates future costs (like the total time to
    complete remaining tasks).

    The heuristic formula is:
    Cost = alpha * Navigation_Cost
           + beta * Urgency_Cost
           + gamma * Remaining_Work_Cost

    """

    def __init__(
        self,
        action_handler: "ActionHandler",
    ):
        """
        Initializes the HeuristicManager.

        Args:
            action_handler: An instance of ActionHandler used for simulating
                            actions and estimating durations.
        """
        self.action_handler = action_handler

        self.alpha = constants.ALPHA_HEURISTIC
        self.beta = constants.BETA_HEURISTIC
        self.gamma = constants.GAMMA_HEURISTIC
        log.info(
            f"HeuristicManager initialized with weights: alpha={self.alpha}, beta={self.beta}, gamma={self.gamma}"
        )

    # ========================================================================
    # Helper Functions - 시간 및 위치 추정
    # ========================================================================

    def _get_estimated_pure_interaction_time(self, subtask: Subtask) -> float:
        """
        Estimates the pure interaction time of a subtask, excluding navigation and waiting.

        It assumes that `subtask.duration.interval` represents the pure interaction time.
        If not available, it falls back to estimating based on primitive actions.

        Args:
            subtask: The subtask to evaluate.

        Returns:
            The estimated pure interaction time in seconds.
        """
        if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
            return 0.0

        if subtask.duration and subtask.duration.interval is not None:
            # `subtask.duration.interval` is considered pure interaction time.
            return max(0.0, subtask.duration.interval)

        # Fallback: estimate based on primitive actions if duration is not specified.
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
        """
        Returns the primary interaction location for a subtask.

        It uses the target of the first NAVIGATE_TO action or, failing that,
        the target of the first interaction-like primitive action.

        Args:
            subtask: The subtask to evaluate.
            scene_positions: A dictionary of current object positions in the scene.

        Returns:
            A tuple (x, y, z) representing the interaction location, or None if
            no specific location is required (e.g., for a WAIT task).
        """
        if not subtask.execution or not subtask.execution.primitive_actions:
            return None

        for action_str in subtask.execution.primitive_actions:
            tokens = action_str.split(" ", 2)
            action_type = tokens[0].upper()
            target_obj_id = tokens[1] if len(tokens) > 1 else None

            if target_obj_id and target_obj_id in scene_positions:
                if action_type == "NAVIGATE_TO":
                    # The navigation target is the most likely interaction point.
                    return tuple(scene_positions[target_obj_id])
                # If no NAV, the first interaction target is the next best guess.
                return tuple(scene_positions[target_obj_id])

        return None

    def _estimate_navigation_time_between_positions(
        self,
        pos1: Optional[Tuple[float, float, float]],
        pos2: Optional[Tuple[float, float, float]],
    ) -> float:
        """Estimates navigation time between two positions via the action_handler."""
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0

        path = self.action_handler._find_shortest_path(pos1, pos2)
        return len(path) * NAV_STEP_DURATION if path else 0.0

    # ========================================================================
    # Helper Functions - CP 및 MST 계산
    # ========================================================================

    def _calculate_critical_path_interaction_duration(
        self,
        remaining_tasks: Set[Subtask],
        constraints: nx.DiGraph,
        executed_subtask: Optional[Subtask],
    ) -> float:
        """
        Calculates the total "pure interaction + interval" time along the critical path
        of the remaining tasks. (Navigation time is handled separately by MST).

        If an executed_subtask is provided, it applies a discount to the critical
        path duration for initiating a critical chain.
        """
        if not remaining_tasks:
            return 0.0

        task_names_set = {sub.name for sub in remaining_tasks}
        subgraph = constraints.subgraph(task_names_set).copy()

        task_pure_interaction_times = {
            sub.name: self._get_estimated_pure_interaction_time(sub)
            for sub in remaining_tasks
        }

        earliest_finish_times = {task_name: 0.0 for task_name in task_names_set}

        for task_name in nx.topological_sort(subgraph):
            max_earliest_finish_of_predecessors = 0.0
            for pred_name, _, edge_data in subgraph.in_edges(task_name, data=True):
                if pred_name in earliest_finish_times:
                    interval = edge_data.get("info", {}).get("Interval", 0.0)
                    log.debug(
                        f"  CP Edge: {pred_name} (eft: {earliest_finish_times[pred_name]:.2f}) -> {task_name} "
                        f"with interval {interval:.2f}"
                    )
                    max_earliest_finish_of_predecessors = max(
                        max_earliest_finish_of_predecessors,
                        earliest_finish_times[pred_name] + interval,
                    )

            interaction_time = task_pure_interaction_times.get(task_name, 0.0)
            earliest_finish_times[task_name] = (
                max_earliest_finish_of_predecessors + interaction_time
            )

        cp_duration = (
            max(earliest_finish_times.values()) if earliest_finish_times else 0.0
        )

        # Apply benefit for starting a critical chain
        if executed_subtask and constraints.has_node(executed_subtask.name):
            discount = 0.0
            for _, succ, data in constraints.out_edges(
                executed_subtask.name, data=True
            ):
                if succ in task_names_set and data.get("info", {}).get("IsCritical"):
                    discount += data.get("info", {}).get("Interval", 0.0)

            if discount > 0:
                log.info(
                    f"  Applying critical start benefit from '{executed_subtask.name}'. Discount: {discount:.2f}"
                )
                cp_duration = max(0.0, cp_duration - discount)

        return cp_duration

    def _calculate_mst_navigation_time(
        self,
        current_agent_pos: Optional[Tuple[float, float, float]],
        remaining_tasks: Set[Subtask],
        scene_positions: dict[str, any],
    ) -> float:
        """
        Estimates the total navigation time to visit all remaining task locations
        using a Minimum Spanning Tree (MST) as an approximation.
        """
        if not remaining_tasks:
            return 0.0

        locations_to_visit = set()
        if current_agent_pos:
            locations_to_visit.add(current_agent_pos)

        for subtask in remaining_tasks:
            loc = self._get_task_interaction_location(subtask, scene_positions)
            if loc:
                locations_to_visit.add(loc)

        if len(locations_to_visit) <= 1:
            return 0.0

        location_list = list(locations_to_visit)
        num_locations = len(location_list)

        dist_matrix = np.full((num_locations, num_locations), LARGE_NUMBER, dtype=float)
        for i in range(num_locations):
            dist_matrix[i, i] = 0.0
            for j in range(i + 1, num_locations):
                pos1 = location_list[i]
                pos2 = location_list[j]
                nav_time = self._estimate_navigation_time_between_positions(pos1, pos2)
                dist_matrix[i, j] = nav_time
                dist_matrix[j, i] = nav_time

        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import minimum_spanning_tree

        graph_sparse = csr_matrix(dist_matrix)
        mst = minimum_spanning_tree(graph_sparse)
        mst_total_nav_time = mst.sum()

        return mst_total_nav_time

    # ========================================================================
    # Main Heuristic Calculation Method
    # ========================================================================

    def _calculate_remaining_work_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, float, float]:
        """
        Estimates the cost of completing all tasks remaining *after* the candidate is executed.

        This simulates the candidate's execution to predict the next state and then
        calculates the Critical Path (CP) and Minimum Spanning Tree (MST) costs
        for the subsequent remaining tasks.

        Args:
            current_node: The current simulation node.
            candidate: The candidate subtask to evaluate.

        Returns:
            A tuple containing:
            - total_remaining_cost (float): The sum of CP and MST costs.
            - cp_duration (float): The calculated critical path duration.
            - mst_time (float): The calculated MST navigation time.
        """

        # For synthetic candidates, determine which task name to exclude from the future workload calculation.
        task_to_exclude = candidate.subtask.name
        if task_to_exclude.startswith("Wait for "):
            # Wait action doesn't consume a task, so no task is excluded.
            task_to_exclude = None
        elif task_to_exclude.startswith("MONITORING_FOR_"):
            # A monitoring action, for planning purposes, effectively "completes" the
            # task it is monitoring from the perspective of future workload.
            task_to_exclude = task_to_exclude.replace("MONITORING_FOR_", "", 1)

        exec_info = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )

        next_pos = tuple(exec_info.scene_positions.get("agent"))
        next_tasks = {
            t
            for t in current_node.state.remaining_subtasks
            if t.name != task_to_exclude
        }
        next_constraints = current_node.state.constraints
        next_scene_pos = exec_info.scene_positions

        cp_duration = self._calculate_critical_path_interaction_duration(
            next_tasks, next_constraints, candidate.subtask
        )
        sum_interaction_time = sum(
            self._get_estimated_pure_interaction_time(t) for t in next_tasks
        )

        mst_time = self._calculate_mst_navigation_time(
            next_pos, next_tasks, next_scene_pos
        )

        # [Modified] Use max(CP, Sum) to account for single-agent sequential execution constraint
        # CP handles dependency chains (depth), Sum handles total volume of work (breadth)
        base_work_time = max(cp_duration, sum_interaction_time)
        total_cost = base_work_time + mst_time

        log.info(
            f"    RemainingWorkCost for '{candidate.subtask.name}': CP={cp_duration:.2f}, "
            f"Sum={sum_interaction_time:.2f}, MST={mst_time:.2f} -> Total={total_cost:.2f}"
        )
        return total_cost, cp_duration, mst_time

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
    ) -> float:
        """
        Calculates the heuristic cost for a given candidate subtask.

        The cost is a weighted sum of immediate costs (navigation, urgency) and
        estimated future costs (remaining workload), plus penalties.

        If the candidate is a 'Wait' action, it uses a specialized cost
        function `_calculate_wait_heuristic`.

        Args:
            current_node: The current simulation node.
            candidate: The candidate subtask to evaluate.
            not_yet_candidates: A list of candidates that require waiting.


        Returns:
            The calculated heuristic cost (lower is better).
        """

        # --- Check for Wait Candidate ---
        if candidate.subtask.name.startswith("Wait for"):
            return self._calculate_wait_heuristic(
                current_node, candidate, not_yet_candidates
            )

        # --- 1. Immediate Costs & Penalties ---
        nav_cost_for_candidate = candidate.estimated_first_nav_duration or 0.0

        urgency_cost, slack = self._calculate_candidate_urgency_cost(
            current_node, candidate
        )

        # --- 2. Future Workload Cost ---
        remaining_work_cost, cp_dur, mst_time = self._calculate_remaining_work_cost(
            current_node, candidate
        )

        # --- 3. Final Weighted Sum ---
        total_heuristic_cost = (
            self.alpha * nav_cost_for_candidate
            + self.beta * urgency_cost
            + self.gamma * remaining_work_cost
        )

        log.info(
            f"  Heuristic for '{candidate.subtask.name}': "
            f"CandNav({self.alpha:.1f}*{nav_cost_for_candidate:.2f})={self.alpha * nav_cost_for_candidate:.2f}, "
            f"Urg({self.beta:.1f}*{urgency_cost:.2f})={self.beta * urgency_cost:.2f} (Slack={slack:.2f}), "
            f"RemWork({self.gamma:.1f}*Rem[{cp_dur:.2f}+{mst_time:.2f}])={self.gamma * remaining_work_cost:.2f}"
        )
        log.info(
            f"  => Total Heuristic Cost for '{candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return total_heuristic_cost

    def _calculate_wait_heuristic(
        self,
        current_node: SimulationNode,
        wait_candidate: Candidate,
        not_yet_candidates: List[Candidate],
    ) -> float:
        """
        Calculates a specialized heuristic cost for a 'Wait' action.

        The cost of waiting includes a slack-based urgency score and the cost of
        all work remaining after the wait. A 'Wait' action fully consumes the
        available slack, making its slack value 0.

        Args:
            current_node: The current simulation node.
            wait_candidate: A synthetic candidate representing the 'Wait' action.
            not_yet_candidates: A list of candidates that require waiting.

        Returns:
            The calculated heuristic cost for waiting.
        """
        # For a wait action, the urgency should be based on the task being waited for.
        target_task_name = wait_candidate.subtask.name.replace("Wait for ", "")
        target_candidate = next(
            (
                cand
                for cand in not_yet_candidates
                if cand.subtask.name == target_task_name
            ),
            None,
        )

        if target_candidate:
            wait_urgency_cost, _ = self._calculate_candidate_urgency_cost(
                current_node, target_candidate
            )
        else:
            # Fallback if the target candidate is not found (should not happen in normal flow)
            wait_urgency_cost = 0.0

        # PENALTY: Add the cost of work remaining *after* the wait. This prevents
        # waiting from appearing deceptively "cheap".
        remaining_work_cost, cp_dur, mst_time = self._calculate_remaining_work_cost(
            current_node, wait_candidate
        )

        # --- Final Weighted Sum for Waiting ---
        total_heuristic_cost = (
            self.beta * wait_urgency_cost + self.gamma * remaining_work_cost
        )

        log.info(
            f"  Heuristic for '{wait_candidate.subtask.name}': "
            f"WaitUrgency({self.beta:.1f}*{wait_urgency_cost:.2f})={self.beta * wait_urgency_cost:.2f}, "
            f"RemWorkAfterWait({self.gamma:.1f}*Rem[{cp_dur:.2f}+{mst_time:.2f}])={self.gamma * remaining_work_cost:.2f}, "
        )
        log.info(
            f"  => Total Heuristic Cost for '{wait_candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return total_heuristic_cost

    def _calculate_candidate_urgency_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, float]:
        """
        Calculates the urgency cost for a candidate based on its slack time.

        Target: Slack should be close to 0 (Just-in-Time Scheduling).
        - We use 'abs(slack)' as cost.
        - Both being too early (positive slack) and too late (negative slack) are penalized.
        - Larger deviations from 0 result in higher costs.

        Args:
            current_node: The current simulation node.
            candidate: The candidate subtask to evaluate.

        Returns:
            A tuple containing:
            - urgency_cost (float): The calculated urgency cost (abs(slack)).
            - slack (float): The calculated slack time.
        """
        if not candidate.scheduling_due or candidate.scheduling_due.due_date == float(
            "inf"
        ):
            # For non-critical tasks that do not have a deadline from a critical task.
            return 0.0, 0.0

        current_time = current_node.state.current_time
        deadline = candidate.scheduling_due.due_date

        time_needed_for_nav = candidate.estimated_first_nav_duration or 0.0

        time_needed_for_interaction = self._get_estimated_pure_interaction_time(
            candidate.subtask
        )
        total_time_needed = time_needed_for_nav + time_needed_for_interaction
        time_available = deadline - current_time
        slack = time_available - total_time_needed

        log.info(
            f"  Urgency for '{candidate.subtask.name}': Due={deadline:.2f}, CurrT={current_time:.2f}, "
            f"AvailT={time_available:.2f}, NeedNavT={time_needed_for_nav:.2f}, NeedInteractT={time_needed_for_interaction:.2f}, "
            f"TotalNeedT={total_time_needed:.2f} => Slack={slack:.2f}"
        )

        # [Modified] Asymmetric Urgency Cost
        # If Slack < 0 (Late): Heavy penalty to enforce critical timing.
        # If Slack >= 0 (Early): Extremely low penalty (0.001) to prioritize urgent tasks (EDD)
        # but NOT punish early execution heavily.
        if slack < 0:
            urgency_cost = abs(slack) * 10.0
        else:
            urgency_cost = slack * 0.001

        return urgency_cost, slack
