from __future__ import annotations

import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, List, Optional

import numpy as np
from scipy.stats import norm

from src.models.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
)
from src.models.task import Duration, Execution, Subtask
from src.utils.common import create_module_logger
from src.utils.common.decorators import time_logger
from src.utils.config import (
    EPSILON,
    MONITORING_DURATION,
    RED,
    RESET,
    TIMING_TOLERANCE_ABS,
)
from src.utils.config.constants import (
    BAYESIAN_THRESHOLD_PROBABILITY,
    BEAM_WIDTH,
    INIT_PRIOR_VARIANCE,
    MONITORING_ENABLED,
    SIMULATION_DEPTH,
)
from src.utils.task import TaskUtil

if TYPE_CHECKING:
    from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager

log = create_module_logger(module_name=__name__, module_log=True)


class Scheduler:
    """
    Beam Search based Scheduler with n-step lookahead.
    Given a current state, it attempts to find the best next subtask to execute
    by simulating expansions of feasible (or soon-to-be-feasible) subtasks.

    Attributes:
        search_width (int): Beam width (number of top expansions to keep).
        simulation_depth (int): Maximum search depth for lookahead.
        nav_graph (dict): Navigation graph for path planning.

        action_handler (ActionHandler): Handles action duration calculations.
        constraint_handler (ConstraintHandler): Checks subtask feasibility.
        cost_calculator (HeuristicManager): Calculates heuristic cost of expansions.
        _counter (itertools.count): A counter to break ties in the priority queue.
    """

    def __init__(
        self,
        action_handler: ActionHandler,
        constraint_handler: ConstraintHandler,
        heuristic_manager: HeuristicManager,
        beam_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):

        self.search_width = beam_width
        self.simulation_depth = simulation_depth
        log.info(
            f"{RED}[Scheduler Init] search_width={beam_width}, simulation_depth={simulation_depth}{RESET}"
        )
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.cost_calculator = heuristic_manager
        self._counter = itertools.count()

    # ======================
    # Public method
    # ======================
    @time_logger
    def get_next_state(self, parent_state: SchedulerState) -> Optional[SchedulerState]:
        """
        Public method to retrieve the immediate next state (1-step ahead in time)
        from the given parent_state.

        Args:
            parent_state (SchedulerState): The current scheduling state.

        Returns:
            Optional[SchedulerState]: The next state after scheduling one subtask,
            or None if no feasible solution is found.
        """
        child_node = self._simulate_search(parent_state)
        if child_node is None:
            log.error("[get_next_state] No child_state found => No feasible solution.")
            return None

        new_state = self._extract_state(child_node)
        if new_state is None:
            log.error("[get_next_state] child_state found, but state is None.")
            return None

        log.debug(
            f"[get_next_state] => subtask={new_state.subtask.name}, "
            f"time={round(new_state.current_time,2)}"
        )
        return new_state

    # ======================
    # Core beam search
    # ======================
    def _simulate_search(self, init_state: SchedulerState) -> Optional[SimulationNode]:
        """
        Conducts a beam search up to self.simulation_depth from the init_state.
        - Each node expansion checks feasible and not-yet-feasible candidates.
        - If no feasible expansions exist, that branch try wait expansion.
        - A queue (PriorityQueue) is used to keep track of expansions by ascending cost.
        - We collect "best solutions" (i.e., states in which all tasks are done
          or we have reached the search depth) and return the least-cost one.

        Args:
            init_state (SchedulerState): The root state to start the simulation.

        Returns:
            Optional[SimulationNode]: The best goal node (lowest cost) among expansions
            that reach depth or complete all subtasks. None if no solution is found.
        """
        queue = PriorityQueue()

        init_node = SimulationNode(
            parent_node=None,
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=next(self._counter),
            state=init_state,
            risk_level=0,
        )
        queue.put(init_node)

        best_solutions: List[SimulationNode] = []

        while not queue.empty():
            curr_node = queue.get()
            curr_state = curr_node.state
            curr_depth = curr_node.depth

            # (1) Termination condition
            if not curr_state.remaining_subtasks or (
                curr_depth >= self.simulation_depth
            ):
                best_solutions.append(curr_node)
                continue

            # (2) Get feasible and not-yet-feasible subtask candidates
            feasible_candidates, not_yet_candidates = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )
            log.debug(
                f"[_simulate_search] Expanding {len(feasible_candidates)} feasible candidates "
                f"and {len(not_yet_candidates)} not-yet-feasible candidates.\n"
            )
            if not feasible_candidates and not not_yet_candidates:
                # No expansions possible => infeasible branch
                log.debug("[_simulate_search] No expansions => branch ends.")
                continue

            feasible_names = [c.subtask.name for c in feasible_candidates]
            not_yet_names = [c.subtask.name for c in not_yet_candidates]

            log.debug(
                f"\n=== [Simulation Step] Depth {curr_depth} -> {curr_depth + 1} | Time: {curr_state.current_time:.2f} ===\n"
                f"  • Completed : {[ce.subtask.name for ce in curr_state.completed_entries]}\n"
                f"  • Remaining : {[r.name for r in curr_state.remaining_subtasks]}\n"
                f"  • Feasible  : {feasible_names}\n"
                f"  • Not Yet   : {not_yet_names}\n"
                f"============================================================"
            )

            # Expand current node
            expanded_nodes = self._expand_candidates(
                curr_node, feasible_candidates, not_yet_candidates
            )
            # Sort by (Risk Level, Makespan Cost)
            # Primary: risk_level (Ascending - 0 is best)
            # Secondary: heuristic_cost (Ascending - lower cost is best)
            expanded_nodes = sorted(
                filter(lambda nd: nd.risk_level == 0, expanded_nodes),
                key=lambda nd: nd.heuristic_cost,
            )

            # (3) Local Beam Pruning: Keep only the top-K expansions
            log.debug(f"--- Top Candidates (Depth {curr_depth}) ---")
            for i, nd in enumerate(expanded_nodes):
                if i < self.search_width:
                    log.debug(
                        f"  [{i+1}] {nd.state.subtask.name:<40} | Cost: {nd.heuristic_cost:.2f} | Risk: {nd.risk_level} | EndTime: {nd.state.current_time:.2f}"
                    )
                    queue.put(nd)
                else:
                    break

        if not best_solutions:
            log.error("[_simulate_search] best_solutions empty => no feasible path")
            return None

        # Return the best solution (lowest cost)
        # Sort by (Risk Level, Heuristic Cost)
        best_solutions = sorted(
            best_solutions,
            key=lambda nd: (nd.risk_level, nd.heuristic_cost),
        )

        log.debug(
            f"\n--- Best Solutions Evaluation ({len(best_solutions)} candidates) ---"
        )
        for i, nd in enumerate(best_solutions):
            rank_str = "WINNER" if i == 0 else f"Rank {i+1}"
            log.debug(
                f"  [{rank_str:<8}] {nd.state.subtask.name:<30} | Risk: {nd.risk_level} | Cost: {nd.heuristic_cost:.2f} | Depth: {nd.depth}"
            )

        winner = best_solutions[0]
        log.debug(
            f"[_simulate_search] Final Decision: '{winner.state.subtask.name}' selected. (Risk={winner.risk_level}, Cost={winner.heuristic_cost:.2f})\n"
        )
        return winner

    def _extract_state(
        self, child_node: Optional[SimulationNode]
    ) -> Optional[SchedulerState]:
        """
        Traces from a terminal node (child_node) back to the root (init_state),
        and returns the **state at depth=1** in that path. This effectively
        picks the next immediate step in the best path found.

        Args:
            child_node (SimulationNode): The best solution node from the beam search.

        Returns:
            Optional[SchedulerState]: The state corresponding to the next step
            (depth=1). If only the root is found, returns the root state.
        """
        if child_node is None:
            log.error("[_extract_state] child_node is None")
            return None

        # Build path from child back to root
        path = []
        cur = child_node
        while cur:
            path.append(cur)
            cur = cur.parent_node
        path.reverse()

        # If only the root (depth=0) is present
        if len(path) < 2:
            log.debug("[_extract_state] Only root node in path. Returning root state.")
            return path[0].state if path else None

        # Return the state at the first step beyond root (depth=1)
        log.debug("[_extract_state] Returning state at depth=1 in the best path.")
        return path[1].state

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """
        Expands candidates based on a unified policy to prioritize critical tasks.

        Policy Hierarchy:
        1. Urgent Critical Tasks (Unified):
           - If any critical task is ready to start (within tolerance) or overdue,
             expand ONLY these tasks. This combines On-time, Closing, and Missed policies.
        2. Standard Expansion:
           - If no urgent tasks, expand all feasible tasks and valid 'WAIT' options.
        """
        expansions: List[SimulationNode] = []

        # --- Policy 1 (Unified): Urgent Critical Tasks ---
        urgent_candidates = self._get_urgent_critical_candidates(
            curr_node, feasible_candidates, not_yet_candidates
        )

        if urgent_candidates:
            log.debug(
                f"Policy 1 (Urgent): Expanding {len(urgent_candidates)} urgent candidate(s)."
            )
            for candidate in urgent_candidates:
                child_node = self._expand_single_subtask(
                    curr_node, candidate, not_yet_candidates, feasible_candidates
                )
                if child_node:
                    expansions.append(child_node)

            if expansions:
                return expansions
            else:
                log.debug(
                    "All urgent candidates failed to expand. Falling back to standard expansion."
                )

        # --- Policy 2: Standard Expansion (other feasible + all waits) ---
        log.debug("Policy 2: No urgent criticals. Performing standard expansion.")
        for candidate in feasible_candidates:
            child_node = self._expand_single_subtask(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
            if child_node:
                expansions.append(child_node)

        # [Unified Wait Expansion 251216]
        # Instead of iterating over ALL not_yet_candidates to create redundant Wait actions,
        # we pick ONE representative candidate to trigger the wait logic.
        # Since _expand_single_wait (and _expand_wait_wo_monitoring) now uses
        # global_earliest_deadline to cap the wait duration, any candidate will result
        # in the same "Wait until next event" behavior.
        # We pick the one with the earliest 'actual_interaction_start_time' or logical start time.

        if not_yet_candidates:
            # Sort to find the earliest target
            sorted_wait_targets = sorted(
                not_yet_candidates,
                key=lambda c: (
                    c.actual_interaction_start_time
                    if c.actual_interaction_start_time is not None
                    else (
                        c.logical_interaction_start_time
                        if c.logical_interaction_start_time is not None
                        else float("inf")
                    )
                ),
            )

            # Pick the best candidate (e.g., earliest start time)
            # If multiple candidates exist, just picking the first one is sufficient
            # because the Safe Wait Splitting logic considers GLOBAL deadlines anyway.
            representative_wait_candidate = sorted_wait_targets[0]

            log.debug(
                f"[_expand_candidates] Unified Wait: Selected representative '{representative_wait_candidate.subtask.name}' from {len(not_yet_candidates)} options."
            )

            wait_node = self._expand_single_wait(
                curr_node,
                representative_wait_candidate,
                not_yet_candidates,
                feasible_candidates=feasible_candidates,
            )
            if wait_node:
                expansions.append(wait_node)

        return expansions

    def _get_urgent_critical_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[Candidate]:
        """
        Identifies critical candidates that are 'Urgent'.
        Urgent means the task's physical earliest start time is greater than or equal to
        its logical start time (minus tolerance).
        This covers both 'On-time' (within tolerance) and 'Missed' (overdue) cases.
        Also checks not_yet_candidates for urgent but blocked tasks, prioritizing their feasible predecessors.
        """
        urgent_list = []
        for candidate in feasible_candidates:
            if not candidate.is_critical:
                continue

            if candidate.logical_interaction_start_time is None:
                continue

            physical_earliest_start = (
                curr_node.state.current_time + candidate.estimated_first_nav_duration
            )

            # Check urgency: Are we at or past the time we should start?
            # We use a tolerance to allow starting slightly early (On-time).
            if (
                physical_earliest_start
                >= candidate.logical_interaction_start_time - TIMING_TOLERANCE_ABS
            ):
                # Update actual interaction start time
                # We start as soon as physically possible (ASAP)
                candidate.actual_interaction_start_time = physical_earliest_start

                log.debug(
                    f"Found URGENT CRITICAL candidate: {candidate.subtask.name} "
                    f"(Physical: {physical_earliest_start:.2f} >= Logical: {candidate.logical_interaction_start_time:.2f} - Tol)"
                )
                urgent_list.append(candidate)

        # [Added 251215] Check blocked urgent tasks and prioritize predecessors
        feasible_map = {c.subtask.name: c for c in feasible_candidates}
        constraints = curr_node.state.constraints
        visited = set()

        def find_feasible_ancestor(target_name: str) -> None:
            """Recursively trace predecessors to find feasible ancestors."""
            if target_name in visited:
                return
            visited.add(target_name)

            if not constraints.has_node(target_name):
                return

            preds = list(constraints.predecessors(target_name))
            for pred_name in preds:
                if pred_name in feasible_map:
                    pred_cand = feasible_map[pred_name]
                    if pred_cand not in urgent_list:
                        log.debug(
                            f"Prioritizing feasible ancestor '{pred_name}' to unblock urgent task chain targeting '{candidate.subtask.name}'."
                        )
                        urgent_list.append(pred_cand)
                else:
                    # Recursive search for ancestors
                    find_feasible_ancestor(pred_name)

        for candidate in not_yet_candidates:
            if not candidate.is_critical or candidate.subtask.decomposed:
                continue

            # Check urgency using critical_context
            crit_ctx = candidate.critical_context
            if not crit_ctx or crit_ctx.source_end_time is None:
                continue

            logical_start = crit_ctx.source_end_time + crit_ctx.interval
            physical_start = (
                curr_node.state.current_time + candidate.estimated_first_nav_duration
            )

            if physical_start >= logical_start:
                # Urgent but blocked! Find feasible predecessors recursively.
                log.debug(
                    f"Found BLOCKED URGENT task: {candidate.subtask.name} "
                    f"(Physical: {physical_start:.2f} >= Logical: {logical_start:.2f} - Tol). Tracing ancestors."
                )

                len_before = len(urgent_list)
                find_feasible_ancestor(candidate.subtask.name)

                if len(urgent_list) == len_before:
                    log.debug(
                        f"No feasible ancestors found for {candidate.subtask.name}. "
                        f"Adding the task itself as it is time-ready/urgent."
                    )
                    candidate.actual_interaction_start_time = physical_start
                    urgent_list.append(candidate)

        return urgent_list

    def _extract_monitoring_target(self, candidate: Candidate) -> Optional[str]:
        if (
            candidate.subtask.execution
            and candidate.subtask.execution.primitive_actions
        ):
            # Typically, the target of the first action is what we monitor.
            return candidate.subtask.execution.primitive_actions[0].split()[1]
        return None

    # ==========================================================================
    #           SUBTASK EXPANSION: Single Subtask or Wait
    # ==========================================================================
    def _expand_single_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands the given candidate subtask by deciding whether to split it
        into a monitoring subtask or not.

        Args:
            curr_node (SimulationNode): The current node in the search tree.
            candidate (Candidate): The subtask candidate to expand.

        Returns:
            Optional[SimulationNode]: The resulting child node if successful,
            otherwise None.
        """
        log.debug(
            f"[_expand_single_subtask] Checking expansion for subtask: {candidate.subtask.name}."
        )

        # 모니터링 필요?
        need_monitor, due_info = self._should_subtask_split_with_monitoring(
            curr_node, candidate
        )
        if need_monitor and MONITORING_ENABLED:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} requires monitoring-based splitting."
            )
            candidate.scheduling_due = due_info
            return self._expand_subtask_with_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        else:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} will be executed without monitoring."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

    def _expand_single_wait(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands the wait subtask by deciding whether to split it
        into a monitoring subtask or not.

        Args:
            curr_node (SimulationNode): The current node in the search tree.
            candidate (Candidate): The subtask candidate will be expand.

        Returns:
            Optional[SimulationNode]: The resulting child node if successful,
            otherwise None.
        """

        log.debug(
            f"[_expand_single_wait] Checking wait-based expansion for subtask: {candidate.subtask.name}."
        )

        target_obj_id = candidate.subtask.execution.primitive_actions[0].split()[1]
        nav_time = self.action_handler.get_actions_info(
            curr_node,
            [f"NAVIGATE_TO {target_obj_id}"],
        ).action_duration
        log.debug(
            f"[_expand_single_wait] Subtask {candidate.subtask.name}'s navigation time: {nav_time}. ({target_obj_id})"
        )

        # Check if monitoring is needed before waiting, using the same Bayesian logic as standard subtasks.
        need_monitor, due_info = self._should_subtask_split_with_monitoring(
            curr_node, candidate
        )

        # Rule 3: Split only if an active critical interval exists.
        active_intervals = []
        graph = curr_node.state.constraints
        completed_entries_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_entries
        }

        for start_name, end_name, data in graph.edges(data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval") > EPSILON:
                if (
                    start_name in completed_entries_map
                    and end_name not in completed_entries_map
                ):
                    start_entry = completed_entries_map[start_name]
                    if start_entry.subtask.subtask_type != "Monitor":
                        interval = info.get("Interval", 0.0)
                        variance = info.get("Variance", INIT_PRIOR_VARIANCE)
                        due_date = start_entry.schedule_end_time + interval
                        # if due_date > curr_node.state.current_time:
                        active_intervals.append(
                            (
                                variance,
                                SchedulingDue(
                                    due_date=due_date, due_related_sub_name=end_name
                                ),
                            )
                        )

        if active_intervals and MONITORING_ENABLED:
            return self._expand_wait_with_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_time,
                feasible_candidates=feasible_candidates,
            )
        else:
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_time,
                feasible_candidates=feasible_candidates,
            )

    # ======================
    # Helper: 모니터링 필요한지
    # ======================
    def _should_subtask_split_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> tuple[bool, Optional[SchedulingDue]]:
        """
        Determines if a task should be split for monitoring based on three rules.



        Args:
            curr_node: The current simulation node.
            candidate: The candidate subtask to evaluate.

        Returns:
            True if the candidate should be split for monitoring, False otherwise.
        """

        # Rule 1: Don't re-split tasks.
        if candidate.subtask.decomposed:
            log.debug(
                f"[_should_subtask_split_with_monitoring] Subtask {candidate.subtask.name} is already handled/decomposed. No split."
            )
            return False, None

        # Rule 2: Don't split if an immediate critical predecessor exists.
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        for slot in in_slots:
            if slot.is_critical and slot.interval < EPSILON:
                log.debug(
                    f"[_should_subtask_split_with_monitoring] Subtask {candidate.subtask.name} has an immediate critical predecessor ({slot.related_subtask_name}). Monitoring is disallowed."
                )
                return False, None

        # Rule 3: Split only if an active critical interval exists.
        active_intervals = []
        graph = curr_node.state.constraints
        completed_entries_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_entries
        }

        for start_name, end_name, data in graph.edges(data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval") > EPSILON:
                if (
                    start_name in completed_entries_map
                    and end_name not in completed_entries_map
                ):
                    start_entry = completed_entries_map[start_name]
                    if start_entry.subtask.subtask_type != "Monitor":
                        interval = info.get("Interval", 0.0)
                        variance = info.get("Variance", INIT_PRIOR_VARIANCE)
                        due_date = start_entry.schedule_end_time + interval
                        # if due_date > curr_node.state.current_time:
                        active_intervals.append(
                            (
                                variance,
                                SchedulingDue(
                                    due_date=due_date, due_related_sub_name=end_name
                                ),
                            )
                        )

        if not active_intervals:
            log.debug(
                f"[_should_subtask_split_with_monitoring] No active critical intervals found. No monitoring for {candidate.subtask.name}."
            )
            return False, None

        # If an active interval exists, a split is necessary.
        # Assign the most urgent due date based on VARIANCE (Uncertainty).
        # We prioritize the interval with the HIGHEST variance to reduce uncertainty first.
        # Tie-breaker: If variances are equal, prioritize the one with the EARLIEST due date (smallest due_date).
        best_variance, high_variance_due = max(
            active_intervals, key=lambda item: (item[0], -item[1].due_date)
        )

        # [Safety Latch 251215]
        # We want to monitor the high-variance task, BUT if the candidate already has a TIGHTER deadline,
        # we cannot afford to go monitoring something else that is less urgent.
        original_due = candidate.scheduling_due
        final_due = high_variance_due

        if (
            original_due
            and original_due.due_date != float("inf")
            and original_due.due_date < high_variance_due.due_date
        ):
            # The candidate is MORE URGENT than the monitoring target.
            # Check if there is an active interval for the urgent task itself.
            urgent_interval_pair = next(
                (
                    item
                    for item in active_intervals
                    if item[1].due_related_sub_name == original_due.due_related_sub_name
                ),
                None,
            )

            if urgent_interval_pair:
                # If the urgent task itself can be monitored, do that instead.
                final_due = urgent_interval_pair[1]
                best_variance = urgent_interval_pair[0]
                log.debug(
                    f"[_should_subtask_split_with_monitoring] Overriding high variance target with URGENT target '{final_due.due_related_sub_name}' "
                    f"(due: {final_due.due_date:.2f})."
                )
            else:
                # The urgent task is not monitorable (or not in active list).
                # Skipping monitoring completely to focus on the deadline.
                log.debug(
                    f"[_should_subtask_split_with_monitoring] Skipping monitoring split. Candidate has urgent deadline ({original_due.due_date:.2f}) "
                    f"which is tighter than high variance target ({high_variance_due.due_date:.2f})."
                )
                return False, None

        candidate.scheduling_due = final_due
        log.debug(
            f"[_should_subtask_split_with_monitoring] Active interval found targeting '{final_due.due_related_sub_name}' "
            f"(due: {final_due.due_date:.2f}, var: {best_variance:.2f}). Splitting {candidate.subtask.name}."
        )

        return True, final_due

    # -----------------------------------------------------
    # (A) 서브태스크 (no monitoring)
    # -----------------------------------------------------
    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands a non-monitoring subtask. The subtask is executed fully at once.
        Navigation (if any, as first_nav_duration) + Interaction are performed.
        """

        curr_state = curr_node.state

        curr_depth = curr_node.depth
        original_task_name = candidate.subtask.name
        log.debug(
            f"[_expand_subtask_wo_monitoring] Attempting to expand {original_task_name} (wo_monitoring)."
        )

        planned_nav_start_time = curr_state.current_time
        planned_interaction_start_time = candidate.actual_interaction_start_time
        sub_actions = candidate.subtask.execution.primitive_actions

        if not sub_actions:
            log.warning(
                f"Subtask {original_task_name} has no primitive actions. Cannot expand."
            )
            return None

        try:
            executed_action_info: Optional[ActionResult] = (
                self.action_handler.get_actions_info(curr_node, sub_actions)
            )
            if executed_action_info is None or not executed_action_info.success:
                log.warning(
                    f"Action simulation failed for {original_task_name}. Cannot expand."
                )
                return None
        except ValueError as e:
            log.error(f"Error during action simulation for {original_task_name}: {e}")
            return None

        total_subtask_duration_from_sim = executed_action_info.cumulative_time
        planned_subtask_completion_time = (
            planned_nav_start_time + total_subtask_duration_from_sim
        )

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.total_time = total_subtask_duration_from_sim

        sim_success_status = (
            executed_action_info.success if executed_action_info else False
        )

        completed_entry = CompletedEntry(
            subtask=copied_sub,
            schedule_start_time=planned_nav_start_time,
            schedule_end_time=planned_subtask_completion_time,
            schedule_nav_time=executed_action_info.first_nav_duration,
            execution_status=sim_success_status,
        )
        new_completed = curr_state.completed_entries + [completed_entry]
        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]

        new_scene_positions = executed_action_info.scene_positions
        new_held_obj = executed_action_info.held_object

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_entries=new_completed,
            remaining_subtasks=new_remain,
            constraints=curr_state.constraints,
            current_time=planned_subtask_completion_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # Global Risk Check을 위해 feasible_candidates도 포함하여 전달
        all_candidates = not_yet_candidates
        if feasible_candidates:
            all_candidates = feasible_candidates + not_yet_candidates

        step_risk, pure_h_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, all_candidates
        )

        new_cost = pure_h_cost + curr_node.heuristic_cost

        # Accumulate max risk level along the path
        new_risk = max(curr_node.risk_level, step_risk)

        log.info(
            f"  [Action] {candidate.subtask.name}\n"
            f"    └─ Time : {planned_nav_start_time:.2f} (Nav) -> {planned_interaction_start_time:.2f} (Start) -> {planned_subtask_completion_time:.2f} (End)\n"
            f"    └─ Cost : {pure_h_cost:.2f} (H) + {0:.2f} (G) = {new_cost:.2f} | Risk: {new_risk} | Depth: {curr_depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )

    def _fallback_insert_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        monitoring_target_obj: Optional[str],
        not_yet_candidates: List[Candidate],
        *,
        critical_start_sub_name: Optional[str] = None,
        critical_start_sub_end_time: Optional[float] = None,
        critical_end_sub_name: Optional[str] = None,
        critical_interval_duration: Optional[float] = None,
        monitoring_target_sub_name: Optional[str] = None,
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """Insert a monitoring-only subtask before retrying the original candidate."""

        if not monitoring_target_obj:
            log.warning(
                "[_fallback_insert_monitoring] Missing monitoring target. Falling back to direct execution."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        curr_state = curr_node.state
        target_start_time = (
            candidate.actual_interaction_start_time or curr_state.current_time
        )

        inserted_node = self._insert_monitoring_step(
            curr_node=curr_node,
            candidate=candidate,
            monitoring_target_obj=monitoring_target_obj,
            predecessor_name=curr_state.subtask.name,
            target_actual_start_time=target_start_time,
            critical_start_sub_name=critical_start_sub_name,
            critical_start_sub_end_time=critical_start_sub_end_time,
            critical_end_sub_name=critical_end_sub_name,
            critical_interval_duration=critical_interval_duration,
            monitoring_target_sub_name=monitoring_target_sub_name,
            not_yet_candidates=not_yet_candidates,
        )

        if inserted_node is None:
            log.warning(
                "[_fallback_insert_monitoring] Monitoring execution failed. Falling back to direct execution."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        log.debug(
            f"[_fallback_insert_monitoring] Inserted monitoring before retrying {candidate.subtask.name}."
        )

        return inserted_node

    def _insert_monitoring_step(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        monitoring_target_obj: Optional[str],
        predecessor_name: str,
        target_actual_start_time: float,
        not_yet_candidates: List[Candidate],
        *,
        critical_start_sub_name: Optional[str] = None,
        critical_start_sub_end_time: Optional[float] = None,
        critical_end_sub_name: Optional[str] = None,
        critical_interval_duration: Optional[float] = None,
        monitoring_target_sub_name: Optional[str] = None,
    ) -> Optional[SimulationNode]:
        """Execute monitoring immediately and update state/constraints for a follow-up `candidate`."""

        if not monitoring_target_obj:
            return None

        monitor_base_name = (
            monitoring_target_sub_name
            if monitoring_target_sub_name
            else candidate.subtask.name
        )
        monitor_sub = TaskUtil.create_monitoring_subtask(
            name=monitor_base_name, obj=monitoring_target_obj
        )
        monitor_sub.decomposed = True

        monitor_candidate = Candidate(
            subtask=monitor_sub,
            is_critical=True,
            actual_interaction_start_time=curr_node.state.current_time,
            logical_interaction_start_time=curr_node.state.current_time,
        )

        monitor_node = self._expand_subtask_wo_monitoring(
            curr_node, monitor_candidate, not_yet_candidates
        )
        if monitor_node is None:
            return None

        monitor_state = monitor_node.state
        monitor_start_time = curr_node.state.current_time
        monitor_finish_time = monitor_state.current_time

        final_remaining_subtasks = list(monitor_state.remaining_subtasks)
        # Ensure candidate is in remaining (if it wasn't already)
        if candidate.subtask.name not in [r.name for r in final_remaining_subtasks]:
            final_remaining_subtasks.append(copy.deepcopy(candidate.subtask))

        new_constraints = copy.deepcopy(monitor_state.constraints)
        if not new_constraints.has_node(monitor_sub.name):
            new_constraints.add_node(monitor_sub.name)
        if not new_constraints.has_node(candidate.subtask.name):
            new_constraints.add_node(candidate.subtask.name)

        predecessor_edge_info = {"Interval": 0.0, "IsCritical": True}
        if not new_constraints.has_edge(predecessor_name, monitor_sub.name):
            new_constraints.add_edge(
                predecessor_name,
                monitor_sub.name,
                info=predecessor_edge_info,
            )
        else:
            new_constraints.edges[predecessor_name, monitor_sub.name][
                "info"
            ] = predecessor_edge_info

        remaining_slack = max(
            0.0, target_actual_start_time - monitor_state.current_time
        )
        candidate_edge_info = {"Interval": remaining_slack, "IsCritical": True}

        if not new_constraints.has_edge(monitor_sub.name, candidate.subtask.name):
            new_constraints.add_edge(
                monitor_sub.name,
                candidate.subtask.name,
                info=candidate_edge_info,
            )
        else:
            new_constraints.edges[monitor_sub.name, candidate.subtask.name][
                "info"
            ] = candidate_edge_info

        updated_state = SchedulerState(
            subtask=monitor_state.subtask,
            completed_entries=monitor_state.completed_entries,
            remaining_subtasks=final_remaining_subtasks,
            constraints=new_constraints,
            current_time=monitor_state.current_time,
            scene_positions=monitor_state.scene_positions,
            held_object=monitor_state.held_object,
        )

        if (
            critical_start_sub_name
            and critical_end_sub_name
            and critical_start_sub_end_time is not None
            and critical_interval_duration is not None
        ):
            constraints_with_critical = copy.deepcopy(updated_state.constraints)

            for node_name in (
                critical_start_sub_name,
                critical_end_sub_name,
                monitor_sub.name,
            ):
                if not constraints_with_critical.has_node(node_name):
                    constraints_with_critical.add_node(node_name)

            interval_start_to_mon = max(
                0.0, monitor_start_time - critical_start_sub_end_time
            )
            edge_info_start = {"Interval": interval_start_to_mon, "IsCritical": True}
            if not constraints_with_critical.has_edge(
                critical_start_sub_name, monitor_sub.name
            ):
                constraints_with_critical.add_edge(
                    critical_start_sub_name, monitor_sub.name, info=edge_info_start
                )
            else:
                constraints_with_critical.edges[
                    critical_start_sub_name, monitor_sub.name
                ]["info"] = edge_info_start

            critical_deadline = critical_start_sub_end_time + critical_interval_duration
            interval_mon_to_end = max(0.0, critical_deadline - monitor_finish_time)
            edge_info_end = {"Interval": interval_mon_to_end, "IsCritical": True}

            # [DEBUG LOG] Check Interval Update in _insert_monitoring_step
            prev_interval = "N/A"
            if constraints_with_critical.has_edge(
                monitor_sub.name, critical_end_sub_name
            ):
                prev_interval = (
                    constraints_with_critical.edges[
                        monitor_sub.name, critical_end_sub_name
                    ]
                    .get("info", {})
                    .get("Interval", "N/A")
                )

            log.debug(
                f"[DEBUG _insert_monitoring_step] Updating Edge '{monitor_sub.name}' -> '{critical_end_sub_name}'\n"
                f"  - CriticalDeadline: {critical_deadline:.2f} (StartEnd: {critical_start_sub_end_time:.2f} + Interval: {critical_interval_duration:.2f})\n"
                f"  - MonitorFinish: {monitor_finish_time:.2f}\n"
                f"  - Calc Interval: {interval_mon_to_end:.2f} (Prev: {prev_interval})"
            )

            if not constraints_with_critical.has_edge(
                monitor_sub.name, critical_end_sub_name
            ):
                constraints_with_critical.add_edge(
                    monitor_sub.name, critical_end_sub_name, info=edge_info_end
                )
            else:
                constraints_with_critical.edges[
                    monitor_sub.name, critical_end_sub_name
                ]["info"] = edge_info_end

            # Verify update
            check_interval = constraints_with_critical.edges[
                monitor_sub.name, critical_end_sub_name
            ]["info"]["Interval"]
            log.debug(f"  -> Update Verified: {check_interval:.2f}")

            updated_state = updated_state._replace(
                constraints=constraints_with_critical
            )

        return monitor_node._replace(state=updated_state)

    # -----------------------------------------------------
    # (B) 서브태스크 (with monitoring) - 정책 2 적용
    # -----------------------------------------------------
    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        curr_state = curr_node.state
        original_task_name = candidate.subtask.name

        log.debug(
            f"[_expand_subtask_with_monitoring - Policy 2] Attempting to split {original_task_name} for monitoring."
        )

        # Determine the critical interval that triggers this monitoring split
        scheduling_due = candidate.scheduling_due
        if not (
            scheduling_due
            and scheduling_due.due_date != float("inf")
            and scheduling_due.due_related_sub_name
        ):
            log.debug(
                f"Candidate {original_task_name} has no valid scheduling_due. Fallback to non-monitoring."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        critical_end_sub_name = scheduling_due.due_related_sub_name

        # Find the start of the critical interval
        incoming_constraints_to_crit_end = self.constraint_handler.get_time_slots(
            critical_end_sub_name, curr_state.constraints, "in"
        )
        critical_incoming_slots = [
            s for s in incoming_constraints_to_crit_end if s.is_critical
        ]
        if not critical_incoming_slots:
            log.debug(
                f"No incoming critical constraints for '{critical_end_sub_name}'. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        target_critical_slot = max(critical_incoming_slots, key=lambda s: s.interval)
        original_critical_interval_duration = target_critical_slot.interval
        critical_start_sub_name = target_critical_slot.related_subtask_name

        critical_start_completed_entry = next(
            (
                ce
                for ce in curr_state.completed_entries
                if ce.subtask.name == critical_start_sub_name
            ),
            None,
        )
        if not critical_start_completed_entry:
            log.error(
                f"CRITICAL LOGIC ERROR: start_subtask '{critical_start_sub_name}' not found. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        critical_start_sub_actual_end_time = (
            critical_start_completed_entry.schedule_end_time
        )

        monitoring_target_obj = next(
            (
                (remain_sub.execution.primitive_actions[0].split()[1])
                for remain_sub in curr_node.state.remaining_subtasks
                if remain_sub.name == critical_end_sub_name
                and remain_sub.execution
                and remain_sub.execution.primitive_actions
            ),
            None,
        )
        if not monitoring_target_obj:
            log.warning(
                f"Could not determine monitoring target for '{critical_end_sub_name}'. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        log.debug(
            f"Main monitoring context for {original_task_name}: CritStart='{critical_start_sub_name}' (ends {critical_start_sub_actual_end_time:.2f}), "
            f"CritEnd='{critical_end_sub_name}', OriginalInterval={original_critical_interval_duration:.2f}."
        )

        # --- Refined Splitting Logic ---
        # Retrieve variance from the edge info
        edge_data = curr_state.constraints.get_edge_data(
            critical_start_sub_name, critical_end_sub_name
        )
        variance_val = INIT_PRIOR_VARIANCE
        if edge_data and "info" in edge_data:
            variance_val = edge_data["info"].get("Variance", INIT_PRIOR_VARIANCE)

        # Calculate trigger time based on probability threshold: t = mu + sigma * Phi^-1(eta)
        sigma = np.sqrt(variance_val)
        mu_absolute = (
            critical_start_sub_actual_end_time + original_critical_interval_duration
        )
        z_score = norm.ppf(BAYESIAN_THRESHOLD_PROBABILITY)

        original_absolute_monitoring_trigger_time = mu_absolute + sigma * z_score

        log.debug(
            f"Bayesian Trigger: Mu={mu_absolute:.2f}, Sigma={sigma:.2f}, Eta={BAYESIAN_THRESHOLD_PROBABILITY}, Z={z_score:.2f} "
            f"-> TriggerTime={original_absolute_monitoring_trigger_time:.2f}"
        )

        full_candidate_action_info_check = self.action_handler.get_actions_info(
            curr_node, candidate.subtask.execution.primitive_actions
        )
        if not (
            full_candidate_action_info_check
            and full_candidate_action_info_check.success
        ):
            log.warning(
                f"Full action sim failed for candidate {original_task_name} during check. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        candidate_expected_completion_time_wo_split = (
            curr_state.current_time + full_candidate_action_info_check.cumulative_time
        )

        # Scenario 1: Task is "safe" and finishes before monitoring is needed.
        if (
            candidate_expected_completion_time_wo_split
            <= original_absolute_monitoring_trigger_time
        ):
            log.debug(
                f"Candidate {original_task_name} finishes before monitoring trigger ({original_absolute_monitoring_trigger_time:.2f}). Executing without split."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        # Scenario 3: Monitoring trigger falls during the task. Splitting is necessary.
        duration_for_early_sub_target = (
            original_absolute_monitoring_trigger_time - curr_state.current_time
        )

        pre_actions_log, post_actions_log, split_successful, pre_ends_holding_object = (
            self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                duration_for_early_sub_target,
            )
        )

        if not split_successful or pre_ends_holding_object:
            log.warning(
                f"Failed to split {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. "
                f"Executing the task without splitting as a fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        log.info(f"{pre_actions_log.total_time_used()},{pre_actions_log=}")
        log.info(f"{post_actions_log.total_time_used()},{post_actions_log=}")

        early_sub_actions = []
        actual_early_sub_duration = 0.0

        if (
            pre_actions_log
            and pre_actions_log.results
            and pre_actions_log.get_actions()
        ):
            early_sub_actions = pre_actions_log.get_actions()
            actual_early_sub_duration = pre_actions_log.total_time_used()
            log.debug(
                f"Split {original_task_name}: Initial early_actions ({len(early_sub_actions)}), actual_duration={actual_early_sub_duration:.2f}, target_duration={duration_for_early_sub_target:.2f}"
            )
        else:
            log.warning(
                f"Failed to get valid early_actions from split for {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. "
                f"Executing the task without splitting as a fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        # --- Phase 3: early_sub 확장 및 실제 모니터링 시점 결정 ---
        early_sub_task = copy.deepcopy(candidate.subtask)
        early_sub_task.name = (
            f"EARLY_{original_task_name}"
            if len(post_actions_log.results) != 0
            else original_task_name
        )
        early_sub_task.execution.primitive_actions = early_sub_actions
        early_sub_task.decomposed = True

        early_candidate = Candidate(
            subtask=early_sub_task,
            scheduling_due=None,
            is_critical=candidate.is_critical,
            logical_interaction_start_time=candidate.logical_interaction_start_time,
            actual_interaction_start_time=candidate.actual_interaction_start_time,
            estimated_first_nav_duration=candidate.estimated_first_nav_duration,
        )

        log.info(
            f"  Expanding adjusted EARLY subtask: {early_sub_task.name} (actions: {len(early_sub_actions)}, initial_est_duration: {actual_early_sub_duration:.2f})"
        )
        node_after_early_sub = self._expand_subtask_wo_monitoring(
            curr_node, early_candidate, not_yet_candidates
        )

        if node_after_early_sub is None:
            log.warning(
                f"Expansion of EARLY subtask {early_sub_task.name} failed. "
                f"Executing the original task without splitting as a fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        actual_monitoring_trigger_time = node_after_early_sub.state.current_time

        log.info(
            f"  EARLY subtask {early_sub_task.name} expanded. Actual Monitoring Trigger Time: {actual_monitoring_trigger_time:.2f} "
            f"(Original trigger was: {original_absolute_monitoring_trigger_time:.2f})"
        )

        state_after_early_expansion = node_after_early_sub.state

        # --- Phase 4: mon_sub (주요 인터벌용) 및 remain_sub 생성 ---
        mon_sub_task_for_main_interval = TaskUtil.create_monitoring_subtask(
            name=f"{critical_end_sub_name}",
            obj=monitoring_target_obj,
        )
        mon_sub_task_for_main_interval.decomposed = True

        remain_sub_task: Optional[Subtask] = None
        remain_sub_actions = (
            post_actions_log.get_actions()
            if post_actions_log and post_actions_log.results
            else []
        )
        if remain_sub_actions:
            first_action = remain_sub_actions[0]
            if not first_action.startswith("NAVIGATE_TO"):
                # Try to infer a reasonable target object id from actions
                def _extract_target_id(actions: List[str]) -> Optional[str]:
                    for act in actions:
                        parts = act.split()
                        if len(parts) > 1:
                            return parts[1]
                    return None

                target_id = _extract_target_id(remain_sub_actions)
                if target_id and target_id in curr_state.scene_positions:
                    remain_sub_actions = [
                        f"NAVIGATE_TO {target_id}"
                    ] + remain_sub_actions

        if remain_sub_actions:
            remain_sub_task = copy.deepcopy(candidate.subtask)
            remain_sub_task.name = f"REMAIN_{original_task_name}"
            remain_sub_task.execution.primitive_actions = remain_sub_actions
            remain_sub_task.decomposed = True
            log.debug(
                f"Prepared REMAIN subtask: {remain_sub_task.name} with {len(remain_sub_actions)} actions."
            )

        # --- Phase 5: 제약 조건 그래프 및 remaining_subtasks 업데이트 ---
        new_constraints_graph = copy.deepcopy(state_after_early_expansion.constraints)

        original_task_in_edges_data = []
        original_task_out_edges_data = []
        if new_constraints_graph.has_node(original_task_name):
            original_task_in_edges_data = list(
                new_constraints_graph.in_edges(original_task_name, data=True)
            )
            original_task_out_edges_data = list(
                new_constraints_graph.out_edges(original_task_name, data=True)
            )
            new_constraints_graph.remove_node(original_task_name)
            log.debug(f"Removed node '{original_task_name}' from constraints graph.")

        if not new_constraints_graph.has_node(early_sub_task.name):
            new_constraints_graph.add_node(early_sub_task.name)
            log.debug(f"Node for EARLY subtask '{early_sub_task.name}' added to graph.")
        if not new_constraints_graph.has_node(mon_sub_task_for_main_interval.name):
            new_constraints_graph.add_node(mon_sub_task_for_main_interval.name)
        if remain_sub_task and not new_constraints_graph.has_node(remain_sub_task.name):
            new_constraints_graph.add_node(remain_sub_task.name)

        for pred_name, _, data in original_task_in_edges_data:
            if pred_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_sub_task.name if remain_sub_task else ""),
                original_task_name,
                # critical_start_sub_name,
            ]:
                edge_info = copy.deepcopy(data.get("info", {}))
                if not new_constraints_graph.has_edge(pred_name, early_sub_task.name):
                    new_constraints_graph.add_edge(
                        pred_name, early_sub_task.name, info=edge_info
                    )
                    log.debug(
                        f"Rerouted incoming constraint from '{pred_name}' to '{early_sub_task.name}'."
                    )

        source_for_outgoing_edges = (
            remain_sub_task.name
            if remain_sub_task
            else mon_sub_task_for_main_interval.name
        )
        for _, succ_name, data in original_task_out_edges_data:
            if succ_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_sub_task.name if remain_sub_task else ""),
                original_task_name,
                # critical_end_sub_name,
            ]:
                edge_info = copy.deepcopy(data.get("info", {}))
                if not new_constraints_graph.has_edge(
                    source_for_outgoing_edges, succ_name
                ):
                    new_constraints_graph.add_edge(
                        source_for_outgoing_edges, succ_name, info=edge_info
                    )
                    log.debug(
                        f"Rerouted outgoing constraint from '{source_for_outgoing_edges}' to '{succ_name}'."
                    )

        info_early_to_mon = {"Interval": 0.0, "IsCritical": True}
        if not new_constraints_graph.has_edge(
            early_sub_task.name, mon_sub_task_for_main_interval.name
        ):
            new_constraints_graph.add_edge(
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                info=info_early_to_mon,
            )
            log.debug(
                f"Added internal constraint: '{early_sub_task.name}' -> '{mon_sub_task_for_main_interval.name}'."
            )

        if remain_sub_task:
            info_mon_to_remain = {"Interval": 0.0, "IsCritical": False}
            if not new_constraints_graph.has_edge(
                mon_sub_task_for_main_interval.name, remain_sub_task.name
            ):
                new_constraints_graph.add_edge(
                    mon_sub_task_for_main_interval.name,
                    remain_sub_task.name,
                    info=info_mon_to_remain,
                )
                log.debug(
                    f"Added internal constraint: '{mon_sub_task_for_main_interval.name}' -> '{remain_sub_task.name}'."
                )

        interval_crit_start_to_mon = (
            actual_monitoring_trigger_time - critical_start_sub_actual_end_time
        )
        info_crit_start_to_mon = {
            "Interval": max(0.0, interval_crit_start_to_mon),
            "IsCritical": True,
        }
        if not new_constraints_graph.has_edge(
            critical_start_sub_name, mon_sub_task_for_main_interval.name
        ):
            new_constraints_graph.add_edge(
                critical_start_sub_name,
                mon_sub_task_for_main_interval.name,
                info=info_crit_start_to_mon,
            )
        else:
            new_constraints_graph.edges[
                critical_start_sub_name, mon_sub_task_for_main_interval.name
            ]["info"].update(info_crit_start_to_mon)
        log.debug(
            f"Added/Updated main monitoring constraint: '{critical_start_sub_name}' -> '{mon_sub_task_for_main_interval.name}', Interval: {info_crit_start_to_mon['Interval']:.2f}."
        )

        critical_end_sub_original_deadline = (
            critical_start_sub_actual_end_time + original_critical_interval_duration
        )
        mon_sub_expected_completion_time = (
            actual_monitoring_trigger_time + MONITORING_DURATION
        )

        interval_mon_to_crit_end = (
            critical_end_sub_original_deadline - mon_sub_expected_completion_time
        )
        info_mon_to_crit_end = {
            "Interval": max(0.0, interval_mon_to_crit_end),
            "IsCritical": False,
        }

        # [DEBUG LOG] Check Interval Update in _expand_subtask_with_monitoring
        prev_interval_sub = "N/A"
        if new_constraints_graph.has_edge(
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ):
            prev_interval_sub = (
                new_constraints_graph.edges[
                    mon_sub_task_for_main_interval.name, critical_end_sub_name
                ]
                .get("info", {})
                .get("Interval", "N/A")
            )

        log.debug(
            f"[DEBUG _expand_subtask_with_monitoring] Updating Edge '{mon_sub_task_for_main_interval.name}' -> '{critical_end_sub_name}'\n"
            f"  - CritEndDeadline: {critical_end_sub_original_deadline:.2f}\n"
            f"  - MonitorFinish: {mon_sub_expected_completion_time:.2f}\n"
            f"  - Calc Interval: {interval_mon_to_crit_end:.2f} (Prev: {prev_interval_sub})"
        )

        if not new_constraints_graph.has_edge(
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ):
            new_constraints_graph.add_edge(
                mon_sub_task_for_main_interval.name,
                critical_end_sub_name,
                info=info_mon_to_crit_end,
            )
        else:
            new_constraints_graph.edges[
                mon_sub_task_for_main_interval.name, critical_end_sub_name
            ]["info"].update(info_mon_to_crit_end)

        # Verify update
        check_interval_sub = new_constraints_graph.edges[
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ]["info"]["Interval"]
        log.debug(f"  -> Update Verified: {check_interval_sub:.2f}")
        log.debug(
            f"Added/Updated main monitoring constraint: '{mon_sub_task_for_main_interval.name}' -> '{critical_end_sub_name}', Interval: {info_mon_to_crit_end['Interval']:.2f}."
        )

        remaining_after_early_executed = list(
            state_after_early_expansion.remaining_subtasks
        )
        final_remaining_subtasks_list = [
            r for r in remaining_after_early_executed if r.name != original_task_name
        ]

        if mon_sub_task_for_main_interval.name not in {
            r.name for r in final_remaining_subtasks_list
        }:
            final_remaining_subtasks_list.append(mon_sub_task_for_main_interval)
        if remain_sub_task and remain_sub_task.name not in {
            r.name for r in final_remaining_subtasks_list
        }:
            final_remaining_subtasks_list.append(remain_sub_task)

        log.debug(
            f"Updated remaining subtasks. Added mon: {mon_sub_task_for_main_interval.name}, remain: {remain_sub_task.name if remain_sub_task else 'None'}"
        )
        log.debug(
            f"  Final remaining: {[r.name for r in final_remaining_subtasks_list]}"
        )

        updated_final_state = SchedulerState(
            subtask=state_after_early_expansion.subtask,
            completed_entries=state_after_early_expansion.completed_entries,
            remaining_subtasks=final_remaining_subtasks_list,
            constraints=new_constraints_graph,
            current_time=actual_monitoring_trigger_time,
            scene_positions=state_after_early_expansion.scene_positions,
            held_object=state_after_early_expansion.held_object,
        )

        return node_after_early_sub._replace(state=updated_final_state)

    # -----------------------------------------------------
    # (C) Wait expansions
    # -----------------------------------------------------
    def _expand_wait_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        nav_duration: float = 0.0,
        feasible_candidates: List[Candidate] = None,
    ) -> SimulationNode:
        """
        Performs monitoring and, if needed, a follow-up wait until the
        candidate's actual_interaction_start_time.
        """
        curr_state = curr_node.state

        # 1. 이미 Monitor 태스크를 수행한 직후라면 -> Trigger Time까지 Wait 수행
        if curr_node.state.subtask.subtask_type == "Monitor":
            # Determine the critical interval that triggers this monitoring split
            scheduling_due = candidate.scheduling_due
            if not (
                scheduling_due
                and scheduling_due.due_date != float("inf")
                and scheduling_due.due_related_sub_name
            ):
                log.debug(
                    "Candidate has no valid scheduling_due. Fallback to non-monitoring."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate, not_yet_candidates, feasible_candidates
                )

            critical_end_sub_name = scheduling_due.due_related_sub_name

            # Find the start of the critical interval directly from constraints
            incoming_constraints_to_crit_end = self.constraint_handler.get_time_slots(
                critical_end_sub_name, curr_state.constraints, "in"
            )
            critical_incoming_slots = [
                s for s in incoming_constraints_to_crit_end if s.is_critical
            ]

            if not critical_incoming_slots:
                log.debug(
                    f"No incoming critical constraints for '{critical_end_sub_name}'. Fallback for {candidate.subtask.name}."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate, not_yet_candidates, feasible_candidates
                )

            # [수정 251217] 분산(Variance)이 가장 작은(=가장 확실한) 제약을 우선 선택.
            # 분산이 같다면, Logical End Time이 가장 늦은(=가장 보수적인) 제약을 선택.
            best_slot = None
            min_variance = float("inf")
            max_logical_end_time = -float("inf")

            for slot in critical_incoming_slots:
                pred_name = slot.related_subtask_name
                pred_entry = next(
                    (
                        ce
                        for ce in curr_state.completed_entries
                        if ce.subtask.name == pred_name
                    ),
                    None,
                )

                # Edge 데이터에서 분산 조회
                variance = INIT_PRIOR_VARIANCE
                edge_data = curr_state.constraints.get_edge_data(
                    pred_name, critical_end_sub_name
                )
                if edge_data and "info" in edge_data:
                    variance = edge_data["info"].get("Variance", INIT_PRIOR_VARIANCE)

                if pred_entry:
                    logical_end = pred_entry.sim_end_time + slot.interval

                    # 1. 분산이 현저히 더 작은 경우 -> 무조건 선택 (신뢰도 우선)
                    if variance < min_variance - EPSILON:
                        min_variance = variance
                        max_logical_end_time = logical_end
                        best_slot = slot
                    # 2. 분산이 비슷한 경우 -> 더 늦게 끝나는 제약 선택 (보수적 접근)
                    elif abs(variance - min_variance) <= EPSILON:
                        if logical_end > max_logical_end_time + EPSILON:
                            max_logical_end_time = logical_end
                            best_slot = slot

            target_critical_slot = best_slot

            # Fallback
            if target_critical_slot is None:
                target_critical_slot = max(
                    critical_incoming_slots, key=lambda s: s.interval
                )

            critical_start_sub_name = target_critical_slot.related_subtask_name

            critical_start_completed_entry = next(
                (
                    ce
                    for ce in curr_state.completed_entries
                    if ce.subtask.name == critical_start_sub_name
                ),
                None,
            )

            trigger_time = curr_state.current_time  # Default to NOW if calc fails

            if critical_start_completed_entry:
                edge_data = curr_state.constraints.get_edge_data(
                    critical_start_sub_name, critical_end_sub_name
                )

                # Default values
                variance_val = INIT_PRIOR_VARIANCE
                interval_val = 0.0

                if edge_data and "info" in edge_data:
                    variance_val = edge_data["info"].get(
                        "Variance", INIT_PRIOR_VARIANCE
                    )
                    interval_val = edge_data["info"].get("Interval", 0.0)

                # Get start task end time
                start_end_time = critical_start_completed_entry.sim_end_time

                # Bayesian trigger time calculation
                sigma = np.sqrt(variance_val)
                mu_absolute = start_end_time + interval_val
                z_score = norm.ppf(BAYESIAN_THRESHOLD_PROBABILITY)
                trigger_time = mu_absolute + sigma * z_score

                log.debug(
                    f"[_expand_wait_with_monitoring] Smart Wait Check: TriggerTime={trigger_time:.2f} "
                    f"(Current={curr_state.current_time:.2f}, Nav={nav_duration:.2f})"
                )
            else:
                log.warning(
                    f"Critical predecessor '{critical_start_sub_name}' not found in completed entries. Cannot calc trigger time."
                )

            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
                max_wait_duration=max(0.0, trigger_time - curr_state.current_time),
            )

        # 2. 아직 Monitor를 하지 않았다면 -> Monitor Step 삽입
        target_obj_id = candidate.subtask.execution.primitive_actions[0].split()[1]

        # [수정] candidate.critical_context 대신 그래프 직접 조회하여 정보 추출
        critical_start_sub_name = None
        critical_start_sub_end_time = None
        critical_interval_duration = None

        # Candidate 자체로 들어오는 Critical Edge 찾기
        incoming_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_state.constraints, "in"
        )
        critical_slots = [s for s in incoming_slots if s.is_critical]

        if critical_slots:
            target_slot = max(critical_slots, key=lambda s: s.interval)
            critical_start_sub_name = target_slot.related_subtask_name
            critical_interval_duration = target_slot.interval

            # 선행 작업 완료 시간 조회
            pred_entry = next(
                (
                    ce
                    for ce in curr_state.completed_entries
                    if ce.subtask.name == critical_start_sub_name
                ),
                None,
            )
            if pred_entry:
                critical_start_sub_end_time = pred_entry.sim_end_time

        inserted_node = self._insert_monitoring_step(
            curr_node=curr_node,
            candidate=candidate,
            monitoring_target_obj=target_obj_id,
            predecessor_name=curr_node.state.subtask.name,
            target_actual_start_time=candidate.actual_interaction_start_time,
            not_yet_candidates=not_yet_candidates,
            critical_start_sub_name=critical_start_sub_name,
            critical_start_sub_end_time=critical_start_sub_end_time,
            critical_end_sub_name=candidate.subtask.name,
            critical_interval_duration=critical_interval_duration,
            monitoring_target_sub_name=candidate.subtask.name,
        )

        if inserted_node is None:
            log.warning(
                f"[_expand_wait_with_monitoring] Monitoring expansion failed for {candidate.subtask.name}. Fallback to plain wait."
            )
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
            )

        return inserted_node

    def _expand_wait_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        nav_duration: float = 0.0,
        feasible_candidates: List[Candidate] = None,
        max_wait_duration: Optional[float] = None,
    ) -> Optional[SimulationNode]:
        """
        Inserts a single "Wait" action until the candidate's actual_interaction_start_time.

        - If actual_interaction_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with type="Wait".
        - [Fix 251216] Safe Wait Splitting: The wait duration is capped by the earliest
          deadline among other feasible candidates to prevent blocking critical tasks.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.
            nav_duration (float): Estimated navigation duration to the target object.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
            모니터링 시점까지 대기 혹은 Earliest start time의 candidate 시작 시점까지 대기
        """
        curr_state = curr_node.state
        depth = curr_node.depth

        target_start_time = (
            candidate.actual_interaction_start_time
            if candidate.actual_interaction_start_time is not None
            else (
                candidate.logical_interaction_start_time
                if candidate.logical_interaction_start_time is not None
                else curr_state.current_time
            )
        )

        if max_wait_duration is not None:
            target_start_time = min(
                target_start_time, curr_state.current_time + max_wait_duration
            )

        # Calculate Wait Duration
        total_wait_duration = max(
            0.0, target_start_time - curr_state.current_time - nav_duration
        )

        log.debug(
            f"[_expand_wait_wo_monitoring] Check for {candidate.subtask.name}:\n"
            f"  Current Time: {curr_state.current_time:.2f}\n"
            f"  Target Start (Est): {target_start_time:.2f}\n"
            f"  Nav Duration: {nav_duration:.2f}\n"
            f"  -> Calculated Wait Duration: {total_wait_duration:.2f}"
        )

        if total_wait_duration <= EPSILON:
            log.debug(
                f"[_expand_wait_wo_monitoring] Total wait duration ({total_wait_duration:.2f}) is less than or equal to EPSILON. Skip waiting."
            )
            return None

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=total_wait_duration, type="Controllable"),
            repetition=1,
            subtask_type="Interaction",
            execution=Execution(
                objects=None, primitive_actions=[f"WAIT {total_wait_duration}"]
            ),
            temporal_constraints=None,
        )

        start_time = curr_state.current_time
        end_time = curr_state.current_time + total_wait_duration

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            schedule_start_time=start_time,
            schedule_end_time=end_time,
            schedule_nav_time=0.0,
            execution_status=True,
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_entries=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=end_time,
            scene_positions=curr_state.scene_positions,
            held_object=curr_state.held_object,
        )

        # Create a synthetic candidate to represent the 'Wait' action for the heuristic calculator.
        # [Fix 251216] Preserve the original scheduling_due to allow proper risk assessment
        wait_candidate = Candidate(
            subtask=wait_sub,
            is_critical=candidate.is_critical,
            # Inherit the deadline to let heuristic manager know about the pressure
            scheduling_due=candidate.scheduling_due,
        )

        # Global Risk Check을 위해 feasible_candidates도 포함하여 전달
        all_candidates = not_yet_candidates
        if feasible_candidates:
            all_candidates = feasible_candidates + not_yet_candidates

        step_risk, step_cost = self.cost_calculator.calc_heuristic(
            curr_node,
            wait_candidate,
            all_candidates,
            # Wait action creates delay. We must check if this delay hurts ANY feasible or not_yet task.
        )
        # Same logic as above: prevent double counting of future costs.
        # f(n) = time_so_far + heuristic_score + past_penalties
        new_cost = step_cost + curr_node.heuristic_cost

        # Accumulate max risk level
        new_risk = max(curr_node.risk_level, step_risk)

        log.info(
            f"  [Wait] For {candidate.subtask.name}\n"
            f"    └─ Time : {start_time:.2f} -> {end_time:.2f} (Duration: {total_wait_duration:.2f})\n"
            f"    └─ Cost : {step_cost:.2f} (H) = {new_cost:.2f} | Risk: {new_risk} | Depth: {depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )
