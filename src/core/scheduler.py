import copy
import itertools
import uuid
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.task import Duration, Execution, Subtask
from scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from scheduler.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from utils import BEAM_WIDTH, SIMULATION_DEPTH, create_module_logger
from utils.constants import (
    BAYESIAN_CRITERIA,
    EPSILON,
    LOG_ROUND,
    MONITORING_DURATION,
    RED,
    RESET,
)
from utils.task.task_util import split_subtask_for_monitoring

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Scheduler:
    """
    Beam Search based Scheduler with n-step lookahead.
    Given a current state, it attempts to find the best next subtask to execute
    by simulating expansions of feasible (or soon-to-be-feasible) subtasks.

    Attributes:
        search (int): Beam width (number of top expansions to keep).
        simulation_depth (int): Maximum search depth for lookahead.
        nav_manager (NavigationManager): Handles navigation time calculations.
        constraint_handler (ConstraintHandler): Checks subtask feasibility.
        cost_calculator (HeuristicManager): Calculates heuristic cost of expansions.
        _counter (itertools.count): A counter to break ties in the priority queue.
    """

    def __init__(
        self,
        nav_graph: dict,
        search_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):
        """
        Initialize the Scheduler with given beam width and simulation depth.
        """
        self.search = search_width
        self.simulation_depth = simulation_depth
        log.info(
            f"{RED}[Scheduler Init] search_width={search_width}, simulation_depth={simulation_depth}{RESET}"
        )

        self.nav_manager = ActionHandler(nav_graph)
        self.constraint_handler = ConstraintHandler()
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        # Tie-breaker counter for the priority queue
        self._counter = itertools.count()

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
            log.error("[get_next_state] No child_state found (No feasible solution).")
            return None

        new_state = self._extract_state(child_node)
        if new_state is None:
            log.error(
                "[get_next_state] ChildState was found, but _extract_state returned None."
            )
            return None

        log.debug(
            f"[get_next_state] Returning new state with subtask: "
            f"{new_state.subtask.name if new_state.subtask else 'None'}, "
            f"current_time={round(new_state.current_time,2)}\n"
        )
        return new_state

    # ==========================================================================
    #                        MAIN BEAM SEARCH LOGIC
    # ==========================================================================
    def _simulate_search(self, init_state: SchedulerState) -> Optional[SimulationNode]:
        """
        Conducts a beam search up to self.simulation_depth from the init_state.
        - Each node expansion checks feasible and not-yet-feasible candidates.
        - If no feasible expansions exist, that branch is deemed infeasible.
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

        # Initialize root node
        init_node = SimulationNode(
            parent_node=None,
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=next(self._counter),
            state=init_state,
        )
        queue.put(init_node)

        best_solutions: List[SimulationNode] = []

        # Standard Beam Search
        while not queue.empty():
            curr_node = queue.get()
            curr_state, curr_depth = curr_node.state, curr_node.depth

            # (1) Termination condition
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:

                best_solutions.append(curr_node)
                continue

            # (2) Get feasible and not-yet-feasible subtask candidates
            feasible_candidates, not_yet_candidates = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )

            # No expansions possible => infeasible branch
            if not feasible_candidates and not not_yet_candidates:
                log.warning("[_simulate_search] No expansions possible => branch ends.")
                continue

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth} (expanding to {curr_depth + 1})\n"
                f"Current Time : {round(curr_state.current_time,2)}\n\n"
                f"Completed_subs={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[c for c in feasible_candidates]},\n\n"
                f"Not_yet_feasible_subs={[c for c in not_yet_candidates]}\n\n"
                f"========================================"
            )

            # Expand current node
            expanded_nodes = self._expand_candidates(
                curr_node, feasible_candidates, not_yet_candidates
            )

            # (3) Local Beam Pruning: Keep only the top-K expansions
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):
                if i < self.search:
                    queue.put(nd)

                else:
                    break

        # Choose the best among the best_solutions found
        if not best_solutions:
            log.error("[_simulate_search] best_solutions is empty -> No feasible path")
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        best_node = best_solutions[0]
        log.debug(
            f"[_simulate_search] Best node found with cost={round(best_node.heuristic_cost,2)}."
        )
        return best_node

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """
        Expand the current node for both feasible and not-yet-feasible subtasks.

        - Feasible candidates are sorted by earliest_start_time (descending),
          then expanded via `_expand_single_subtask`.
        - If no feasible expansion is done and we have not-yet-feasible tasks,
          we insert a single Wait expansion (the earliest not-yet-feasible candidate).
          This is a simplified approach to "waiting" until a subtask becomes feasible.

        Args:
            curr_node (SimulationNode): The node being expanded.
            feasible_candidates (List[Candidate]): Currently feasible tasks.
            not_yet_candidates (List[Candidate]): Tasks that are not yet feasible.

        Returns:
            List[SimulationNode]: Children nodes expanded from curr_node.
        """
        expanded_nodes: List[SimulationNode] = []
        is_expanded = False

        # (A) Expand feasible candidates:
        #     Sort by earliest_start_time in descending order
        # ? 왜 descending order로 정렬하는지?
        sorted_feasible = sorted(
            feasible_candidates, key=lambda x: x.earliest_start_time, reverse=True
        )
        log.debug(
            f"[_expand_candidates] Expanding {len(sorted_feasible)} feasible candidates "
            f"and {len(not_yet_candidates)} not-yet-feasible candidates.\n"
        )

        for candidate in sorted_feasible:
            log.debug(
                f"[_expand_candidates] Attempting to expand feasible subtask: {candidate.subtask.name}.\n"
            )
            new_node = self._expand_single_subtask(curr_node, candidate)
            if new_node is not None:
                expanded_nodes.append(new_node)
                is_expanded = True

                # * Subtask가 Critical Constraints End인 경우, 반드시 도래. 다른 Subtask에 대한 고려 X
                if (
                    candidate.is_critical
                    and abs(
                        candidate.earliest_start_time - curr_node.state.current_time
                    )
                    < EPSILON
                ):
                    log.debug(
                        "[_expand_candidates] Subtask is critical and must start immediately => Breaking."
                    )
                    break

        # (B) If we have not expanded any feasible subtask,
        #     then we do a single Wait expansion (pick earliest not-yet-feasible)
        if not is_expanded and not_yet_candidates:
            sorted_not_yet = sorted(
                not_yet_candidates, key=lambda x: x.earliest_start_time
            )
            wait_candidate = sorted_not_yet[0]
            log.debug(
                f"[_expand_candidates] No feasible expansions done. Waiting for subtask: {wait_candidate.subtask.name}.\n"
            )
            wait_node = self._expand_single_wait(curr_node, wait_candidate)
            expanded_nodes.append(wait_node)

        return expanded_nodes

    def _extract_state(self, child_node: SimulationNode) -> Optional[SchedulerState]:
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
        curr = child_node
        while curr is not None:
            path.append(curr)
            curr = curr.parent_node
        path.reverse()

        # If only the root (depth=0) is present
        if len(path) < 2:
            log.debug("[_extract_state] Only root node in path. Returning root state.")
            return path[0].state if path else None

        # Return the state at the first step beyond root (depth=1)
        log.debug("[_extract_state] Returning state at depth=1 in the best path.")
        return path[1].state

    # ==========================================================================
    #           SUBTASK EXPANSION: Single Subtask or Wait
    # ==========================================================================
    def _expand_single_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
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

        # ? 꼭 있어야 하는 구문?
        # # Check if deadline is already violated
        # if candidate.deadline.due_date < curr_node.state.current_time:
        #     log.debug(
        #         f"[_expand_single_subtask] Deadline {candidate.deadline.due_date} is already past "
        #         f"current_time {curr_node.state.current_time} => Infeasible."
        #     )
        #     return None

        # Decide if we need monitoring
        use_monitoring = self._should_expand_with_monitoring(curr_node, candidate)
        if use_monitoring:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} requires monitoring-based splitting."
            )
            return self._expand_subtask_with_monitoring(curr_node, candidate)
        else:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} will be executed without monitoring."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

    def _expand_single_wait(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        "wait_candidate"를 만들거나 "wait_with_monitoring"을 만듦.
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

        # nav_time, new_location = self.nav_manager.compute_total_navigation_time(
        #     curr_node, candidate.subtask
        # )
        agent_location = curr_node.state.agent_location.split("|")[0]
        target_location = list(candidate.subtask.execution.objects.keys())[0].split("|")[0]
        nav_time = self.nav_manager.get_specific_nav_time(
            agent_location, target_location
        )

        # If there's enough time to monitor during waiting
        if nav_time > 0.1 and candidate.is_critical:
            log.debug("[_expand_single_wait] Using wait WITH monitoring.")
            return self._expand_wait_with_monitoring(curr_node, candidate)
        else:
            log.debug("[_expand_single_wait] Using wait WITHOUT monitoring.")
            return self._expand_wait_wo_monitoring(curr_node, candidate)

    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        Expands a time-critical Subtask by splitting it into:
            - early_sub
            - monitoring_sub
            - remain_sub

        (Including navigation time in the first portion.)

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): Subtask candidate to be monitored.

        Returns:
            Optional[SimulationNode]: Child node after expansion if feasible,
            otherwise None.
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        log.debug(
            f"[_expand_subtask_with_monitoring] Splitting subtask {candidate.subtask.name} into monitoring form."
        )

        # ------------------- Re-check monitoring necessity constraints -------------------
        # 1) We identify the relevant "critical" slot for the subtask's deadline
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        constraints_start_names = self.constraint_handler.get_time_slots(
            deadline_sub_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            # If no critical constraints, fallback to non-monitoring
            log.debug(
                f"[_expand_subtask_with_monitoring] No critical constraints found for {deadline_sub_name}, "
                f"falling back to normal subtask expansion."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name = max_critical.related_subtask_name
        max_critical_interval = max_critical.interval

        # 2) Find the time at which the critical subtask starts
        critical_start_time = 0.0
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_start_time = ce.end_time
                break

        # 3) Calculate the early cutoff
        early_cutoff = max_critical_interval * BAYESIAN_CRITERIA

        # 4) Check if subtask ends before the monitoring cutoff => no need to split
        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        total_duration = nav_time + candidate.subtask.duration.interval
        if (critical_start_time + early_cutoff) > (
            curr_state.current_time + total_duration
        ):
            log.debug(
                f"[_expand_subtask_with_monitoring] Entire subtask ends before monitoring cutoff => No split needed."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # ------------------- Proceed with actual splitting -------------------
        # (A) Split into early_sub, mon_sub, remain_sub
        early_sub, mon_sub, remain_sub = split_subtask_for_monitoring(
            curr_node=curr_node,
            candidate=candidate,
            nav_manager=self.nav_manager,
            early_cutoff=early_cutoff,
        )
        log.debug(
            f"[_expand_subtask_with_monitoring] Created early_sub={early_sub.name}, "
            f"mon_sub={mon_sub.name}, remain_sub={remain_sub.name}"
        )

        # Compute nav_time for early_sub specifically
        nav_time_early_sub, new_location_early_sub = (
            self.nav_manager.compute_total_navigation_time(curr_node, early_sub)
        )

        # (B) Check feasibility against deadline, including potential nav time
        if deadline_due < (
            curr_state.current_time + early_sub.duration.interval + nav_time_early_sub
        ):
            log.debug(
                f"[_expand_subtask_with_monitoring] Deadline {deadline_due} < "
                f"earliest_finish_time {curr_state.current_time + early_sub.duration.interval + nav_time_early_sub} "
                f"=> Infeasible."
            )
            return None

        # (C) Build the new constraints graph
        old_name = candidate.subtask.name
        new_constraints = copy.deepcopy(curr_state.constraints)

        in_edges = (
            list(new_constraints.in_edges(old_name, data=True))
            if new_constraints.has_node(old_name)
            else []
        )
        out_edges = (
            list(new_constraints.out_edges(old_name, data=True))
            if new_constraints.has_node(old_name)
            else []
        )

        # Remove old subtask node
        if new_constraints.has_node(old_name):
            new_constraints.remove_node(old_name)
        # Reconnect edges
        for pred, _, data in in_edges:
            new_constraints.add_edge(
                pred, early_sub.name, info=copy.deepcopy(data["info"])
            )
        for _, succ, data in out_edges:
            new_constraints.add_edge(
                remain_sub.name, succ, info=copy.deepcopy(data["info"])
            )

        # Add new subtask nodes
        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        # Connect early_sub -> mon_sub -> remain_sub
        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        # Add edges for the critical chain
        new_constraints.add_edge(
            critical_start_sub_name,
            mon_sub.name,
            info={"Interval": early_cutoff, "IsCritical": True},
        )
        new_constraints.add_edge(
            mon_sub.name,
            deadline_sub_name,
            info={
                "Interval": max_critical_interval
                - early_cutoff
                - mon_sub.duration.interval,
                "IsCritical": True,
            },
        )

        # (D) Update "remaining subtasks"
        new_remaining = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        new_remaining.extend([mon_sub, remain_sub])

        # (E) Compute step cost
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, 0)
        new_cost = curr_heuristic + step_cost

        # (F) Build new "completed" entry for early_sub
        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=curr_state.current_time,
            end_time=curr_state.current_time + early_sub.duration.interval,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # (G) Create next state
        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=curr_state.current_time + early_sub.duration.interval,
            agent_location=new_location_early_sub,
        )

        log.info(
            f"[_expand_subtask_with_monitoring] Subtask {candidate.subtask.name} => early_sub: {early_sub.name}\n"
            f"  -> Score={round(new_cost, LOG_ROUND)}, "
            f"Interval={round(completed_entry.start_time,2)}~{round(completed_entry.end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in new_remaining]}"
        )

        # Construct the child node
        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        Expands a non-monitoring subtask. The subtask is executed fully at once.
        Navigation time is added to the subtask's duration.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The subtask candidate to be executed without monitoring.

        Returns:
            Optional[SimulationNode]: Child node if feasible, otherwise None.
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        exec_time = candidate.subtask.duration.interval + nav_time

        start_time = curr_state.current_time
        end_time = start_time + exec_time

        if candidate.deadline.due_date < end_time:
            log.debug(
                f"[_expand_subtask_wo_monitoring] Deadline {candidate.deadline.due_date} < "
                f"subtask_end_time {end_time} => Infeasible."
            )
            return None

        # Build a copy of the subtask with total execution time
        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = exec_time

        # Compute cost
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, 0)
        new_cost = curr_heuristic + step_cost

        # Mark subtask as completed
        completed_entry = CompletedEntry(
            subtask=copied_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate.subtask.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_subtask_wo_monitoring] Executed subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, LOG_ROUND)}, Interval={round(start_time,2)}~{round(end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in new_remaining]}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    def _expand_wait_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> SimulationNode:
        """
        Inserts a single "Wait" action until the candidate's earliest_start_time.

        - If earliest_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with type="Wait".

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        wait_start_time = curr_state.current_time
        wait_duration = candidate.earliest_start_time - curr_state.current_time

        agent_locating = curr_node.state.agent_location.split("|")[0]
        target_location = list(candidate.subtask.execution.objects.keys())[0].split("|")[0]
        nav_time = self.nav_manager.get_specific_nav_time(
            agent_locating, target_location
        )

        nav_action = [f"NAVIGATE_TO {target_location}"]
        monitoring_action = (
            [
                f"MONITORING {candidate.subtask.execution.primitive_actions[0].split()[1]}"
            ]
            if nav_time > 0
            else []
        )

        nav_before_wait_sub = Subtask(
            task_name=None,
            name=f"Navigate to {target_location}",
            duration=Duration(interval=nav_time, type="Controllable"),
            repetition=1,
            type="Interaction",
            execution=Execution(
                objects=None,
                primitive_actions=nav_action,
            ),
            temporal_constraints=None,
        )

        mon_sub = Subtask(
            task_name=None,
            name=f"Monitor for {candidate.subtask.name}_{uuid.uuid4().hex[:6]}",
            duration=Duration(interval=MONITORING_DURATION, type="Controllable"),
            repetition=1,
            type="Monitor",
            execution=Execution(
                objects=None,
                primitive_actions=monitoring_action,
            ),
            temporal_constraints=None,
        )

        new_constraints = copy.deepcopy(curr_state.constraints)
        new_constraints.add_node(mon_sub.name)

        new_constraints.add_edge(
            curr_node.state.subtask.name,
            mon_sub.name,
            info={"Interval": nav_time, "IsCritical": True},
        )

        new_constraints.add_edge(
            mon_sub.name,
            candidate.subtask.name,
            info={
                "Interval": wait_duration - MONITORING_DURATION - nav_time,
                "IsCritical": True,
            },
        )

        new_remaining = [r for r in curr_state.remaining_subtasks]
        new_remaining.extend([mon_sub])

        completed_entry = CompletedEntry(
            subtask=nav_before_wait_sub,
            start_time=wait_start_time,
            end_time=wait_start_time + nav_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_state = SchedulerState(
            subtask=nav_before_wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=wait_start_time + nav_time,
            agent_location=target_location,
        )

        wait_candidate = Candidate(
            subtask=nav_before_wait_sub,
            earliest_start_time=curr_node.state.current_time,
            is_critical=False,
        )

        step_cost = self.cost_calculator.calc_heuristic(curr_node, wait_candidate, 0)
        new_cost = curr_heuristic + step_cost

        log.info(
            f"[_expand_wait_with_monitoring] WAIT + MONITOR subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, LOG_ROUND)}, "
            f"Interval={round(wait_start_time,2)}~{round(wait_start_time + wait_duration,2)}\n"
            f"  -> Updated remain={[r.name for r in curr_state.remaining_subtasks]}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    def _expand_wait_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> SimulationNode:
        """
        Inserts a single "Wait" action until the candidate's earliest_start_time.

        - If earliest_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with type="Wait".

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        wait_start_time = curr_state.current_time
        wait_duration = candidate.earliest_start_time - curr_state.current_time

        target_location = list(candidate.subtask.execution.objects.keys())[0].split("|")[0]

        wait_action = [f"Wait {wait_duration}"] if wait_duration > 0 else []

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None,
                primitive_actions=wait_action,
            ),
            temporal_constraints=None,
        )

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            start_time=wait_start_time,
            end_time=wait_start_time + wait_duration,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=wait_start_time + wait_duration,
            agent_location=target_location,
        )

        wait_candidate = Candidate(
            subtask=wait_sub,
            earliest_start_time=curr_node.state.current_time,
            is_critical=False,
        )

        step_cost = self.cost_calculator.calc_heuristic(curr_node, wait_candidate, 0)
        new_cost = curr_heuristic + step_cost

        log.info(
            f"[_expand_wait_wo_monitoring] WAIT subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, LOG_ROUND)}, "
            f"Interval={round(wait_start_time,2)}~{round(wait_start_time+wait_duration,2)}\n"
            f"  -> Updated remain={[r.name for r in curr_state.remaining_subtasks]}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    # ==========================================================================
    #        HELPER
    # ==========================================================================
    def _should_expand_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> bool:
        """
        Determines whether the candidate subtask requires monitoring-based splitting.

        Conditions checked here:
        1) The subtask has a finite deadline.
        2) The subtask has not been decomposed yet (decomposed=False).
        3) The subtask is long enough that it won't finish before the monitoring cutoff.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The subtask candidate to check.

        Returns:
            bool: True if we should expand the subtask with monitoring, False otherwise.
        """
        # (1) If there's no deadline => no monitoring needed
        if candidate.deadline.due_date == float("inf"):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} has no finite deadline => No monitoring."
            )
            return False

        # (2) If subtask is already decomposed => no monitoring needed
        if candidate.subtask.decomposed:
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is already decomposed => No monitoring."
            )
            return False

        # (3) Check if subtask is Critical Constraints End => no monitoring needed
        # critical 한 작업은 나눠지면 안되는 정책.
        in_time_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, "in"
        )
        if any([slot.is_critical for slot in in_time_slots]):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is a critical-constraint end => No monitoring."
            )
            return False

        # (4) Check if subtask ends before the monitoring cutoff
        curr_state = curr_node.state
        nav_time, _ = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        total_duration = nav_time + candidate.subtask.duration.interval
        subtask_end_time = curr_state.current_time + total_duration

        constraints_start_names = self.constraint_handler.get_time_slots(
            candidate.deadline.subtask_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            log.debug(
                f"[_should_expand_with_monitoring] No critical slots for {candidate.deadline.subtask_name} => No monitoring."
            )
            return False

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name = max_critical.related_subtask_name
        max_critical_interval = max_critical.interval

        critical_start_time = 0.0
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_start_time = ce.end_time
                break

        early_cutoff = max_critical_interval * BAYESIAN_CRITERIA
        monitoring_start_time = critical_start_time + early_cutoff

        # If monitoring start time is later than subtask end => no need for monitoring
        if monitoring_start_time > subtask_end_time:
            log.debug(
                f"[_should_expand_with_monitoring] Monitoring start time {monitoring_start_time} > "
                f"subtask_end_time {subtask_end_time} => No monitoring."
            )
            return False

        log.debug(
            f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} meets monitoring criteria."
        )
        return True
