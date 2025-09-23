from __future__ import annotations

import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, List, Optional

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
from src.utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from src.utils.config.constants import (
    BEAM_WIDTH,
    MONITORING_SPLIT_TOLERANCE_ABS,
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
                log.warning("[_simulate_search] No expansions => branch ends.")
                continue

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth} (expanding to {curr_depth + 1})\n"
                f"Current Time : {round(curr_state.current_time,2)}\n\n"
                f"Completed_subs={[ce.subtask.name for ce in curr_state.completed_entries]}\n"
                f"Remaining_subs={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[c for c in feasible_candidates]},\n\n"
                f"Not_yet_feasible_subs={[c for c in not_yet_candidates]}\n\n"
                f"========================================"
            )

            # Expand current node
            expanded_nodes = self._expand_candidates(
                curr_node, feasible_candidates, not_yet_candidates
            )
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)

            # (3) Local Beam Pruning: Keep only the top-K expansions
            for i, nd in enumerate(expanded_nodes):
                if i < self.search_width:
                    queue.put(nd)
                else:
                    break

        if not best_solutions:
            log.error("[_simulate_search] best_solutions empty => no feasible path")
            return None

        # Return the best solution (lowest cost)

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        log.debug(
            f"[_simulate_search] Best node found with cost={round(best_solutions[0].heuristic_cost,2)}."
        )
        return best_solutions[0]

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
        Expands all possible actions from the current node, including executing
        feasible subtasks and waiting for not-yet-feasible subtasks.

        This method transitions from a rigid rule-based policy to a flexible,
        heuristic-driven one. It generates all potential next-step nodes
        (for both execution and waiting) and returns them. The calling method,
        `_simulate_search`, is then responsible for sorting these nodes by
        their heuristic cost and applying beam search pruning.

        Args:
            curr_node: The current node in the search tree.
            feasible_candidates: A list of candidates that can be executed now.
            not_yet_candidates: A list of candidates that require waiting.

        Returns:
            A list of all possible successor simulation nodes.
        """
        expansions: List[SimulationNode] = []

        # --- 1. Expand all feasible candidates ---
        # Each feasible subtask is a potential action to take immediately.
        log.debug(
            f"[_expand_candidates] Expanding {len(feasible_candidates)} feasible candidates."
        )
        for candidate in feasible_candidates:
            child_node = self._expand_single_subtask(
                curr_node, candidate, not_yet_candidates
            )
            if child_node:
                expansions.append(child_node)

        # --- 2. Expand a 'wait' candidate if beneficial ---
        # Waiting is now considered a strategic choice, evaluated alongside execution.
        if not_yet_candidates:
            # Determine the most promising candidate to wait for.
            # The best candidate is typically the one with the earliest valid future start time.
            sorted_not_feasible = sorted(
                not_yet_candidates,
                key=lambda c: (
                    c.actual_interaction_start_time
                    if c.actual_interaction_start_time is not None
                    and c.actual_interaction_start_time
                    > curr_node.state.current_time + EPSILON
                    else (
                        c.logical_interaction_start_time
                        if c.logical_interaction_start_time is not None
                        and c.logical_interaction_start_time
                        > curr_node.state.current_time + EPSILON
                        else float("inf")
                    )
                ),
            )

            # Check if there's a valid future task to wait for.
            if (
                sorted_not_feasible
                and sorted_not_feasible[0].actual_interaction_start_time is not None
                and sorted_not_feasible[0].actual_interaction_start_time
                > curr_node.state.current_time + EPSILON
            ) or (
                sorted_not_feasible
                and sorted_not_feasible[0].logical_interaction_start_time is not None
                and sorted_not_feasible[0].logical_interaction_start_time
                > curr_node.state.current_time + EPSILON
            ):
                wait_candidate = sorted_not_feasible[0]

                log.debug(
                    f"[_expand_candidates] Considering 'WAIT' action for subtask: {wait_candidate.subtask.name}."
                )
                wait_node = self._expand_single_wait(
                    curr_node, wait_candidate, not_yet_candidates
                )
                if wait_node:
                    expansions.append(wait_node)
            else:
                log.debug(
                    "[_expand_candidates] No suitable future candidates to wait for."
                )

        if not expansions:
            log.warning(
                "[_expand_candidates] No expansions generated (neither feasible nor wait)."
            )

        return expansions

    # ==========================================================================
    #           SUBTASK EXPANSION: Single Subtask or Wait
    # ==========================================================================
    def _expand_single_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
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
        need_monitor = self._should_subtask_split_with_monitoring(curr_node, candidate)
        if need_monitor:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} requires monitoring-based splitting."
            )
            return self._expand_subtask_with_monitoring(
                curr_node, candidate, not_yet_candidates
            )
        else:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} will be executed without monitoring."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

    def _expand_single_wait(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
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

        wants_monitoring = candidate.is_critical and not getattr(
            candidate.subtask, "_monitoring_executed", False
        )

        if wants_monitoring:
            log.debug(
                f"[_expand_single_wait] Subtask {candidate.subtask.name} (non-critical) will wait WITH monitoring."
            )
            if curr_node.state.subtask.name.startswith("Monitoring"):
                log.debug(
                    f"[_expand_single_wait] Current node already monitoring. Falling back to wait WITHOUT monitoring for {candidate.subtask.name}."
                )
                return self._expand_wait_wo_monitoring(
                    curr_node, candidate, not_yet_candidates
                )
            return self._expand_wait_with_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        log.debug(
            f"[_expand_single_wait] Subtask {candidate.subtask.name} Using wait WITHOUT monitoring."
        )
        return self._expand_wait_wo_monitoring(curr_node, candidate, not_yet_candidates)

    # ======================
    # Helper: 모니터링 필요한지
    # ======================
    def _should_subtask_split_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> bool:
        """
        Determines whether the candidate subtask requires monitoring-based splitting.

        Conditions checked here:
        1) The subtask has a finite scheduling due.
        2) The subtask is long enough that it won't finish before the monitoring cutoff.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The subtask candidate to check.

        Returns:
            bool: True if we should expand the subtask with monitoring, False otherwise.
        """

        if getattr(candidate.subtask, "_monitoring_executed", False):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} already handled monitoring => No monitoring."
            )
            return False

        # Find any active critical interval in the current state, regardless of the candidate's own properties.
        # An interval is active if its start_subtask is completed but its end_subtask is not.
        active_intervals = []
        graph = curr_node.state.constraints
        completed_entries_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_entries
        }

        for start_name, end_name, data in graph.edges(data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval") > 0:
                if (
                    start_name in completed_entries_map
                    and end_name not in completed_entries_map
                ):
                    start_entry = completed_entries_map[start_name]
                    interval = info.get("Interval", 0.0)
                    due_date = start_entry.schedule_end_time + interval
                    if due_date > curr_node.state.current_time:
                        active_intervals.append(
                            SchedulingDue(
                                due_date=due_date, due_related_sub_name=end_name
                            )
                        )

        if not active_intervals:
            log.debug(
                f"[_should_expand_with_monitoring] No active critical intervals found. No monitoring for {candidate.subtask.name}."
            )
            return False

        # If there are multiple active intervals, prioritize the one with the earliest due date.
        most_urgent_due = min(active_intervals, key=lambda d: d.due_date)
        candidate.scheduling_due = most_urgent_due
        log.debug(
            f"[_should_expand_with_monitoring] Active interval found targeting '{most_urgent_due.due_related_sub_name}' (due: {most_urgent_due.due_date:.2f}). "
            f"Assigning this context to candidate '{candidate.subtask.name}'."
        )

        # If subtask is already decomposed => no monitoring needed
        if candidate.subtask.decomposed:
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is already decomposed => No monitoring."
            )
            return False

        # (3) If a (0, True) constraint exists, it means consecutive execution is required.
        # This logic prevents monitoring from being inserted between two such tasks.
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        for slot in in_slots:
            if slot.is_critical and slot.interval < EPSILON:
                log.debug(
                    f"[_should_subtask_split_with_monitoring] Subtask {candidate.subtask.name} has an immediate critical predecessor ({slot.related_subtask_name}). "
                    f"Monitoring is disallowed to ensure consecutive execution."
                )
                return False

        return True

    # -----------------------------------------------------
    # (A) 서브태스크 (no monitoring)
    # -----------------------------------------------------
    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
    ) -> Optional[SimulationNode]:
        """
        Expands a non-monitoring subtask. The subtask is executed fully at once.
        Navigation (if any, as first_nav_duration) + Interaction are performed.
        """

        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
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
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, not_yet_candidates
        )
        new_cost = curr_cost + step_cost

        log.info(
            f"Expanded {original_task_name} (wo_monitoring): \n"
            f"  Nav Start: {planned_nav_start_time:.2f}, Interaction Start: {planned_interaction_start_time:.2f}, Completion: {planned_subtask_completion_time:.2f}\n"
            f"  Score: +{step_cost:.2f} -> Total: {new_cost:.2f}. Depth: {curr_depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
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
    ) -> Optional[SimulationNode]:
        """Insert a monitoring-only subtask before retrying the original candidate."""

        if not monitoring_target_obj:
            log.warning(
                "[_fallback_insert_monitoring] Missing monitoring target. Falling back to direct execution."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
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
                curr_node, candidate, not_yet_candidates
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

        remaining_with_flag: List[Subtask] = []
        monitoring_flag_applied = False
        for sub in monitor_state.remaining_subtasks:
            if not monitoring_flag_applied and sub.name == candidate.subtask.name:
                flagged_sub = copy.deepcopy(sub)
                setattr(flagged_sub, "_monitoring_executed", True)
                remaining_with_flag.append(flagged_sub)
                monitoring_flag_applied = True
            else:
                remaining_with_flag.append(sub)

        if not monitoring_flag_applied:
            flagged_sub = copy.deepcopy(candidate.subtask)
            setattr(flagged_sub, "_monitoring_executed", True)
            remaining_with_flag.append(flagged_sub)

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
            remaining_subtasks=remaining_with_flag,
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
    ) -> Optional[SimulationNode]:
        # ============== 정책 2: 작업 연속성 + 지연된 모니터링 ================
        # 1. early_sub 실행 시간 확보 및 조정 (WAIT 추가 가능성)
        # 2. early_sub 확장
        # 3. 실제 모니터링 시점 결정 (early_sub 완료 후)
        # 4. mon_sub (주요 인터벌용) 및 remain_sub 생성
        # 5. 제약 조건 업데이트 (지연된 모니터링 시점 기준)
        # =================================================================

        curr_state = curr_node.state
        original_task_name = (
            candidate.subtask.name
        )  # 분할 대상 태스크 (인터리빙 태스크)

        log.debug(
            f"[_expand_subtask_with_monitoring - Policy 2] Attempting to split {original_task_name} for monitoring."
        )
        scheduling_due = getattr(candidate, "scheduling_due", None)
        if (
            scheduling_due
            and scheduling_due.due_date != float("inf")
            and scheduling_due.due_related_sub_name
        ):
            critical_end_sub_name = scheduling_due.due_related_sub_name
        else:
            if not candidate.is_critical:
                log.debug(
                    f"Candidate {original_task_name} has no (or infinite) scheduling_due info for main critical interval. Fallback to non-monitoring."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate, not_yet_candidates
                )
            critical_end_sub_name = candidate.subtask.name

        incoming_constraints_to_crit_end = self.constraint_handler.get_time_slots(
            critical_end_sub_name, curr_state.constraints, "in"
        )

        critical_incoming_slots = [
            s for s in incoming_constraints_to_crit_end if s.is_critical
        ]

        if not critical_incoming_slots:
            log.debug(
                f"No incoming critical constraints found for the main interval's end task '{critical_end_sub_name}'. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        target_critical_slot = max(critical_incoming_slots, key=lambda s: s.interval)
        original_critical_interval_duration = target_critical_slot.interval
        critical_start_sub_name = target_critical_slot.related_subtask_name

        critical_start_completed_entry: Optional[CompletedEntry] = None
        for ce in curr_state.completed_entries:
            if ce.subtask.name == critical_start_sub_name:
                critical_start_completed_entry = ce
                break

        if not critical_start_completed_entry:
            log.error(
                f"CRITICAL LOGIC ERROR: Main critical interval's start_subtask '{critical_start_sub_name}' "
                f"NOT found in completed_entries. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
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
                f"Could not determine last interacted object for critical_start_subtask '{critical_start_sub_name}'. "
                f"Monitoring subtask cannot be created correctly. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        log.debug(
            f"Main monitoring context for {original_task_name}: CritStart='{critical_start_sub_name}' (ends {critical_start_sub_actual_end_time:.2f}, last_obj='{monitoring_target_obj}'), "
            f"CritEnd='{critical_end_sub_name}', OriginalInterval={original_critical_interval_duration:.2f}."
        )

        # --- Phase 2: early_sub 실행 시간 계산 및 조정 (정책 2 - 1.1.3) ---
        original_absolute_monitoring_trigger_time = (
            critical_start_sub_actual_end_time
            + (original_critical_interval_duration * BAYESIAN_CRITERIA)
        )

        # ? 모니터링 타이밍이 이미 늦은 경우에는?
        duration_for_early_sub_target = (
            original_absolute_monitoring_trigger_time - curr_state.current_time
        )

        full_candidate_action_info_check: Optional[ActionResult] = (
            self.action_handler.get_actions_info(
                curr_node, candidate.subtask.execution.primitive_actions
            )
        )
        if not (
            full_candidate_action_info_check
            and full_candidate_action_info_check.success
        ):
            log.warning(
                f"Full action sim failed for candidate {original_task_name} during check. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        candidate_expected_completion_time_wo_split = (
            curr_state.current_time + full_candidate_action_info_check.cumulative_time
        )

        should_even_try_split = (
            curr_state.current_time < original_absolute_monitoring_trigger_time
            and original_absolute_monitoring_trigger_time
            < candidate_expected_completion_time_wo_split
        )

        log.info(f"{original_absolute_monitoring_trigger_time=}")
        log.info(f"{candidate_expected_completion_time_wo_split=}")

        if not should_even_try_split:
            log.debug(
                f"Candidate {original_task_name} (expected_completion: {candidate_expected_completion_time_wo_split:.2f}) "
                f"does not warrant splitting based on original monitoring trigger {original_absolute_monitoring_trigger_time:.2f}."
            )

            if not monitoring_target_obj:
                log.warning(
                    f"Monitoring fallback skipped for {original_task_name}: could not resolve monitoring target object."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate, not_yet_candidates
                )

            log.info(
                f"[_expand_subtask_with_monitoring] Monitoring trigger already passed for {original_task_name}. "
                f"Inserting monitoring fallback before execution."
            )
            return self._fallback_insert_monitoring(
                curr_node,
                candidate,
                monitoring_target_obj,
                not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
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
                f"Failed to split {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. Inserting monitoring fallback."
            )
            return self._fallback_insert_monitoring(
                curr_node,
                candidate,
                monitoring_target_obj,
                not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
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
                f"Failed to get valid early_actions from split for {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. Inserting monitoring fallback."
            )
            return self._fallback_insert_monitoring(
                curr_node,
                candidate,
                monitoring_target_obj,
                not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
            )

        ideal_early_sub_duration = duration_for_early_sub_target

        lower_bound = max(
            0.0, ideal_early_sub_duration - MONITORING_SPLIT_TOLERANCE_ABS
        )
        upper_bound = ideal_early_sub_duration + MONITORING_SPLIT_TOLERANCE_ABS

        if not (lower_bound <= actual_early_sub_duration <= upper_bound):
            log.info(
                f"[_expand_subtask_with_monitoring] Subtask '{original_task_name}' (actual early_duration: {actual_early_sub_duration:.2f}) "
                f"does not meet timing tolerance for ideal early_duration ({ideal_early_sub_duration:.2f}, "
                f"bounds: [{lower_bound:.2f}, {upper_bound:.2f}]). Using monitoring fallback."
            )
            return self._fallback_insert_monitoring(
                curr_node,
                candidate,
                monitoring_target_obj,
                not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
            )

        log.debug(
            f"[_expand_subtask_with_monitoring] Subtask '{original_task_name}' (actual early_duration: {actual_early_sub_duration:.2f}) "
            f"meets timing tolerance for ideal early_duration ({ideal_early_sub_duration:.2f}). Proceeding with monitoring split."
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
                f"Expansion of EARLY subtask {early_sub_task.name} failed. Inserting monitoring fallback for {original_task_name}."
            )
            return self._fallback_insert_monitoring(
                curr_node,
                candidate,
                monitoring_target_obj,
                not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
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
            "IsCritical": True,
        }

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
    ) -> SimulationNode:
        """
        Performs monitoring and, if needed, a follow-up wait until the
        candidate's actual_interaction_start_time.

        - If `actual_interaction_start_time` <= current time, the logic falls
          back to the non-monitoring wait policy.
        - Navigation (partial) is executed before monitoring; any remaining
          slack is converted into a dedicated wait subtask scheduled **after**
          monitoring.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
        """
        curr_state = curr_node.state

        if candidate.actual_interaction_start_time is None:
            log.warning(
                f"[_expand_wait_with_monitoring] Candidate {candidate.subtask.name} has no actual start. Fallback to plain wait."
            )
            return self._expand_wait_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        slack_until_target = (
            candidate.actual_interaction_start_time - curr_state.current_time
        )
        if slack_until_target <= MONITORING_DURATION + EPSILON:
            log.debug(
                f"[_expand_wait_with_monitoring] Insufficient slack ({slack_until_target:.2f}) for monitoring. Fallback to plain wait."
            )
            return self._expand_wait_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        if getattr(candidate.subtask, "_monitoring_executed", False):
            log.debug(
                f"[_expand_wait_with_monitoring] Monitoring already executed for {candidate.subtask.name}. Proceeding with waiting only."
            )
            return self._expand_wait_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        target_obj_id = candidate.subtask.execution.primitive_actions[0].split()[1]
        critical_ctx = getattr(candidate, "critical_context", None)
        inserted_node = self._insert_monitoring_step(
            curr_node=curr_node,
            candidate=candidate,
            monitoring_target_obj=target_obj_id,
            predecessor_name=curr_node.state.subtask.name,
            target_actual_start_time=candidate.actual_interaction_start_time,
            not_yet_candidates=not_yet_candidates,
            critical_start_sub_name=(
                critical_ctx.source_subtask if critical_ctx else None
            ),
            critical_start_sub_end_time=(
                critical_ctx.source_end_time if critical_ctx else None
            ),
            critical_end_sub_name=candidate.subtask.name,
            critical_interval_duration=(
                critical_ctx.interval if critical_ctx else None
            ),
            monitoring_target_sub_name=candidate.subtask.name,
        )

        if inserted_node is None:
            log.warning(
                f"[_expand_wait_with_monitoring] Monitoring expansion failed for {candidate.subtask.name}. Fallback to plain wait."
            )
            return self._expand_wait_wo_monitoring(
                curr_node, candidate, not_yet_candidates
            )

        remaining_slack = max(
            0.0,
            candidate.actual_interaction_start_time - inserted_node.state.current_time,
        )

        log.debug(
            f"[_expand_wait_with_monitoring] Monitoring inserted before waiting for {candidate.subtask.name}. Remaining slack: {remaining_slack:.2f}."
        )

        return inserted_node

    def _expand_wait_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
    ) -> SimulationNode:
        """
        Inserts a single "Wait" action until the candidate's actual_interaction_start_time.

        - If actual_interaction_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with type="Wait".

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
        """
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
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
        total_wait_duration = max(0.0, target_start_time - curr_state.current_time)

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
        wait_candidate = Candidate(
            subtask=wait_sub,
            is_critical=candidate.is_critical,  # The wait inherits criticality from its target.
            # The 'due date' for the wait is the start time of the task we are waiting for.
            scheduling_due=SchedulingDue(
                due_date=target_start_time, due_related_sub_name=candidate.subtask.name
            ),
        )
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, wait_candidate, not_yet_candidates
        )
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_wo_monitoring] WAIT subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, 2)}, "
            f"Interval={round(start_time,2)}~{round(end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in curr_state.remaining_subtasks]}\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
