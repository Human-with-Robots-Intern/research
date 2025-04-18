import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

from core.dataclass import Candidate, CompletedEntry, SchedulerState, SimulationNode
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager
from scheduler.action_handler import ActionHandler
from src.utils.common import create_module_logger
from src.utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from src.utils.task import TaskUtil

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
        search_width: int,
        simulation_depth: int,
        nav_graph: dict,
    ):

        self.search = search_width
        self.simulation_depth = simulation_depth
        log.info(
            f"{RED}[Scheduler Init] search_width={search_width}, simulation_depth={simulation_depth}{RESET}"
        )

        self.action_handler = ActionHandler(nav_graph or {})
        self.constraint_handler = ConstraintHandler(self.action_handler)
        self.cost_calculator = HeuristicManager(
            self.constraint_handler, self.action_handler
        )

        self._counter = itertools.count()

    # ======================
    # Public method
    # ======================
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
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)

            # (3) Local Beam Pruning: Keep only the top-K expansions
            for i, nd in enumerate(expanded_nodes):
                if i < self.search:
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

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """Expands candidates. Feasible ones first, then wait if necessary."""
        expansions: List[SimulationNode] = []
        is_expanded = False

        # Feasible 후보 확장 (adjusted_start_time은 이미 이동 고려됨)
        # Critical Task 처리: 조정된 시작 시간이 현재 시간과 거의 같으면 바로 실행
        sorted_feasible = sorted(
            feasible_candidates,
            key=lambda c: c.adjusted_start_time,
            reverse=False,
        )
        for candidate in sorted_feasible:
            # Critical이고 조정된 시작 시간이 지금인가?
            if (
                candidate.is_critical
                and abs(candidate.adjusted_start_time - curr_node.state.current_time)
                < EPSILON
            ):
                log.info(
                    f"[_expand_candidates] Critical Task {candidate.subtask.name} needs immediate start (Adjusted EST: {candidate.adjusted_start_time:.2f}). Expanding only this."
                )
                child_node = self._expand_single_subtask(curr_node, candidate)
                if child_node:
                    expansions.append(child_node)
                    is_expanded = True
                # Critical은 하나만 즉시 실행
                return expansions  # 바로 반환

            # 그 외 feasible 확장 시도
            log.debug(
                f"[_expand_candidates] Attempting feasible: {candidate.subtask.name} (Adjusted EST: {candidate.adjusted_start_time:.2f})"
            )
            child_node = self._expand_single_subtask(curr_node, candidate)
            if child_node:
                expansions.append(child_node)
                is_expanded = True
                # 여기서 break 여부는 Beam Search 전략에 따라 결정

        # Wait 확장 (조정된 adjusted_start_time 기준으로 가장 빠른 것 선택)
        if not is_expanded and not_yet_candidates:
            sorted_not_feasible = sorted(
                not_yet_candidates,
                key=lambda c: c.adjusted_start_time,
            )
            wait_candidate = sorted_not_feasible[0]
            log.info(
                f"[_expand_candidates] No feasible expansion. Waiting for {wait_candidate.subtask.name} (Adjusted EST: {wait_candidate.adjusted_start_time:.2f})."
            )
            wait_node = self._expand_single_wait(curr_node, wait_candidate)
            if wait_node:
                expansions.append(wait_node)

        return expansions

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

    # ==========================================================================
    #           SUBTASK EXPANSION: Single Subtask or Wait
    # ==========================================================================
    def _expand_single_subtask(
        self, curr_node: SimulationNode, candidate: Candidate
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
        need_monitor = self._should_expand_with_monitoring(curr_node, candidate)
        if need_monitor:
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
        self, curr_node: SimulationNode, candidate: Candidate
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
        # 모니터링 wait? (동일 위치로 navigate할 때, 0.1 반환함, 또한 monitoring 시간 0.1) 합산하여 0.2를 기준으로 함
        if nav_time > 0.1 and candidate.is_critical:
            log.debug(
                f"[_expand_single_wait] Subtask {candidate.subtask.name} Using wait WITH monitoring."
            )
            return self._expand_wait_with_monitoring(curr_node, candidate)
        else:
            log.debug(
                f"[_expand_single_wait] Subtask {candidate.subtask.name} Using wait WITHOUT monitoring."
            )
            return self._expand_wait_wo_monitoring(curr_node, candidate)

    # -----------------------------------------------------
    # (A) 서브태스크 (no monitoring)
    # -----------------------------------------------------
    def _expand_subtask_wo_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
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
        curr_cost = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        sub_actions = candidate.subtask.execution.primitive_actions

        # * (1) 실제 실행 시간
        last_action_info = self.action_handler.get_actions_info(curr_node, sub_actions)
        # success = controller.last_event.metadata.get('lastActionSuccess', 'N/A')
        start_time = curr_state.current_time
        end_time = start_time + last_action_info.time_used

        # * (2) subtask 종료 시각이 deadline보다 느리면 infeasible
        if candidate.deadline.due_date < end_time:
            log.debug(
                f"[_expand_subtask_wo_monitoring] Deadline {candidate.deadline.due_date} < "
                f"subtask_end_time {end_time} => Infeasible."
            )
            return None

        # * (3) subtask 복사 & duration 설정
        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = last_action_info.time_used

        # * (4) subtask 실행 후, 실제 최종 위치/held_object 반영
        # *    "get_actions_info" 결과를 통해 scene_positions, held_object를 가져온다

        new_held_obj = last_action_info.held_object
        new_scene_positions = last_action_info.scene_positions

        completed_entry = CompletedEntry(copied_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != candidate.subtask.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=curr_state.constraints,
            current_time=end_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, new_remain
        )
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_subtask_wo_monitoring] Subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, 2)}, Interval={round(start_time,2)}~{round(end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in new_remain]}\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    # -----------------------------------------------------
    # (B) 서브태스크 (with monitoring)
    # -----------------------------------------------------
    def _expand_subtask_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
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
        curr_cost = curr_node.heuristic_cost
        depth = curr_node.depth

        log.debug(
            f"[_expand_subtask_with_monitoring] Splitting subtask {candidate.subtask.name} into monitoring form."
        )
        # ! ------------------- Re-check monitoring necessity constraints -------------------
        # * 1) We identify the relevant "critical" slot for the subtask's deadline
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        # Critical constraint를 끝내는 Subtask를 향하는 모든 critical constraints를 찾는다
        constraints_start_names = self.constraint_handler.get_time_slots(
            deadline_sub_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            # Re-check monitoring necessity constraints
            # 현재 candidate subtask가 critical constraints 영향 하에 있지 않는 경우, fallback to non-monitoring
            log.debug(
                f"[_expand_subtask_with_monitoring] No critical constraints found for {deadline_sub_name}, "
                f"falling back to normal subtask expansion."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name, max_critical_interval = (
            max_critical.related_subtask_name,
            max_critical.interval,
        )

        # * 2) Calculate the early cutoff based on Bayesian criteria
        cutoff = max_critical_interval * BAYESIAN_CRITERIA

        # * 3) Find monitoring obj and the time at which the critical constraint starts
        critical_constraint_start_time = 0.0
        critical_constraint_start_sub_objs = None
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_constraint_start_time = ce.end_time
                critical_constraint_start_sub_objs = ce.subtask.execution.objects
                break
        expected_monitoring_start_timing = critical_constraint_start_time + cutoff

        # * 4) Check if the entire subtask ends before the monitoring cutoff
        last_action_info = self.action_handler.get_actions_info(
            curr_node, candidate.subtask.execution.primitive_actions
        )
        exec_time = last_action_info.time_used

        if expected_monitoring_start_timing > curr_state.current_time + exec_time:
            log.debug(
                f"[_expand_subtask_with_monitoring] Entire subtask ends before monitoring cutoff => No split needed."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # ! ------------------- Proceed with actual splitting -------------------
        # * (1) split_subtask_for_monitoring
        split_time = max(0, expected_monitoring_start_timing - curr_state.current_time)

        pre_actions_info, post_actions_info = (
            self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                split_time,
            )
        )

        if not post_actions_info:
            log.warning(
                "[_expand_subtask_with_monitoring] Entire pre subtask ends before monitoring cutoff => No split needed."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)
        early_sub = copy.deepcopy(candidate.subtask)
        early_sub.name += "_early"
        early_sub.execution.primitive_actions = pre_actions_info.get_actions()
        early_sub.duration.interval = pre_actions_info.results[-1].time_used
        early_sub.decomposed = True

        remain_sub = copy.deepcopy(candidate.subtask)
        remain_sub.name += "_remain"
        remain_sub.execution.primitive_actions = post_actions_info.get_actions()
        remain_sub.duration.interval = post_actions_info.results[-1].time_used
        remain_sub.decomposed = True

        monitoring_target_obj = list(critical_constraint_start_sub_objs.keys())[-1]
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=deadline_sub_name, obj=monitoring_target_obj
        )

        log.debug(
            f"[_expand_subtask_with_monitoring] Created early_sub={early_sub.name}, "
            f"mon_sub, remain_sub={remain_sub.name}"
        )

        # * (B) Check feasibility against deadline
        early_sub_start_time = curr_state.current_time
        early_sub_end_time = early_sub_start_time + early_sub.duration.interval

        if deadline_due < early_sub_end_time:
            # * Critical Subtask 도래가 early sub 끝나는 시간보다 느리면 infeasible
            log.debug(
                f"[_expand_subtask_with_monitoring] Deadline {deadline_due} < "
                f"earliest_finish_time {early_sub_end_time}"
                f"=> Infeasible.\n"
            )
            return None

        # * (C) Update the state with the new subtasks
        old_name = candidate.subtask.name
        completed_entry = CompletedEntry(
            early_sub, early_sub_start_time, early_sub_end_time
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]
        new_held_obj = pre_actions_info.results[-1].held_object
        new_scene_positions = pre_actions_info.results[-1].scene_positions
        new_remain = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        new_remain.extend([mon_sub, remain_sub])  # monitoring + remain 추가

        # ! ------------------- Constraints Update (REVISED LOGIC) -------------------
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

        if new_constraints.has_node(old_name):
            new_constraints.remove_node(old_name)

        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        # Reconnect original incoming edges to early_sub
        for pred, _, data in in_edges:
            # IMPORTANT: Check if the incoming edge is the critical start edge itself
            if pred != critical_start_sub_name:
                new_constraints.add_edge(pred, early_sub.name, **data)
            # else: We handle the critical connection below

        # Reconnect original outgoing edges from remain_sub
        for _, succ, data in out_edges:
            # IMPORTANT: Check if the outgoing edge is the critical deadline edge itself
            if succ != deadline_sub_name:
                new_constraints.add_edge(remain_sub.name, succ, **data)
            # else: We handle the critical connection below

        # Connect early_sub -> mon_sub -> remain_sub (Non-critical connections)
        new_constraints.add_edge(
            early_sub.name,
            mon_sub.name,
            info={
                "Interval": 0,
                "IsCritical": True,
            },  # Assuming immediate start after early_sub
        )
        new_constraints.add_edge(
            mon_sub.name,
            remain_sub.name,
            info={
                "Interval": 0,
                "IsCritical": False,
            },  # remain starts after monitoring duration
        )

        # ---- START: Critical Chain Edges Correction (Reflecting Semantic Correction) ----

        # Calculate the ACTUAL time elapsed from critical start event end to the end of the (corrected) early_sub
        # end_time = curr_state.current_time + early_sub.duration.interval
        actual_elapsed_until_early_end = (
            early_sub_end_time - critical_constraint_start_time
        )

        # Edge: Critical Start -> Monitoring Task Start
        # The interval reflects the *actual* expected time until mon_sub starts.
        # Since mon_sub starts immediately after early_sub ends (Interval=0 edge above),
        # this interval is the time from critical_start_sub_end to early_sub_end.
        interval_crit_start_to_mon_start = actual_elapsed_until_early_end
        new_constraints.add_edge(
            critical_start_sub_name,
            mon_sub.name,
            info={
                "Interval": interval_crit_start_to_mon_start,
                "IsCritical": True,
            },  # <<< Interval reflects actual early_sub end
        )
        log.debug(
            f"Added critical edge: {critical_start_sub_name} -> {mon_sub.name} with ACTUAL Interval={interval_crit_start_to_mon_start:.2f}"
        )

        # Edge: Monitoring Task End -> Original Deadline Subtask Start
        # The interval reflects the remaining time from mon_sub's END to deadline_sub_name's START.
        # Total original interval = max_critical_interval
        # Time spent until mon_sub starts = interval_crit_start_to_mon_start
        # Time spent for monitoring = MONITORING_DURATION
        remain_critical_interval = max(
            0,
            max_critical_interval
            - interval_crit_start_to_mon_start
            - MONITORING_DURATION,
        )
        new_constraints.add_edge(
            mon_sub.name,  # From the end of monitoring task
            deadline_sub_name,  # To the start of the task ending the critical period
            info={
                "Interval": remain_critical_interval,  # <<< Interval reflects remaining time after actual mon_sub start + duration
                "IsCritical": True,
            },
        )
        log.debug(
            f"Added critical edge: {mon_sub.name} -> {deadline_sub_name} with Remaining Interval={remain_critical_interval:.2f}"
        )

        # ---- END: Critical Chain Edges Correction ----

        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=early_sub_end_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, new_remain
        )
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_subtask_with_monitoring] Subtask {candidate.subtask.name} => early_sub: {early_sub.name}\n"
            f"  -> Score={round(new_cost, 2)}, "
            f"Interval={round(completed_entry.start_time,2)}~{round(completed_entry.end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in new_remain]}\n"
        )
        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    # -----------------------------------------------------
    # (C) Wait expansions
    # -----------------------------------------------------
    def _expand_wait_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> Optional[SimulationNode]:
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        # Target task info
        target_subtask_name = candidate.subtask.name
        target_logical_start_time = candidate.logical_start_time
        log.debug(
            f"[_expand_wait_with_monitoring] Calculating timings for {target_subtask_name} based on LogicalEST: {target_logical_start_time:.2f}"
        )

        # --- Calculate Timings (논리적 시작 시간 기준) ---
        # Ideal time to START monitoring
        ideal_monitor_start_time = target_logical_start_time - MONITORING_DURATION
        # Time available for navigation until ideal monitor start
        available_time_for_nav = ideal_monitor_start_time - curr_state.current_time

        partial_nav_time = 0.0
        if available_time_for_nav < 0:
            # Too late for ideal monitoring start, implies no time for navigation before monitoring.
            log.warning(
                f"Wait time too short ({available_time_for_nav:.2f}) for navigation before ideal monitoring. "
                f"Proceeding to schedule monitoring immediately after current state for {target_subtask_name}."
            )
            # partial_nav_time remains 0.0
        else:
            # Calculate possible navigation time
            try:
                full_nav_time_info = self.action_handler.get_actions_info(
                    curr_node, [f"NAVIGATE_TO {target_logical_start_time}"]
                )
                full_nav_time = (
                    full_nav_time_info.action_duration if full_nav_time_info else 0.0
                )
                partial_nav_time = max(0, min(available_time_for_nav, full_nav_time))
                log.debug(f"Calculated partial_nav_time: {partial_nav_time:.2f}")
            except Exception as e:
                log.error(
                    f"Error calculating navigation time for {target_subtask_name}: {e}. Assuming 0 nav time."
                )
                partial_nav_time = 0.0

        # --- Simulate ONLY Partial Navigation ---
        nav_start_time = curr_state.current_time
        actual_nav_time_used = 0.0
        navigate_sub = None
        new_scene_positions = copy.deepcopy(
            curr_state.scene_positions
        )  # Start with current state
        new_held_obj = curr_state.held_object

        if partial_nav_time > 1e-6:
            try:
                nav_action = [
                    f"NAVIGATE_TO {target_logical_start_time} {partial_nav_time}"
                ]
                temp_sim_node_for_nav = SimulationNode(
                    state=curr_state,
                    heuristic_cost=0,
                    depth=0,
                    tie_breaker=0,
                    parent_node=None,
                )
                nav_action_info = self.action_handler.get_actions_info(
                    temp_sim_node_for_nav, nav_action
                )

                if nav_action_info:
                    actual_nav_time_used = nav_action_info.time_used
                    new_scene_positions = nav_action_info.scene_positions
                    new_held_obj = nav_action_info.held_object

                    navigate_sub = Subtask(
                        task_name=None,
                        name=f"Navigate towards {target_logical_start_time} while waiting for {target_subtask_name}",
                        duration=Duration(
                            interval=actual_nav_time_used, type="Controllable"
                        ),
                        repetition=1,
                        type="Interaction",
                        execution=Execution(
                            objects=(
                                {target_logical_start_time: 1}
                                if target_logical_start_time
                                else None
                            ),
                            primitive_actions=nav_action,
                        ),
                        decomposed=True,  # Indicates it's part of a larger sequence
                    )
                else:
                    log.warning(
                        f"Partial navigation simulation failed for {target_logical_start_time}. No navigation performed."
                    )
            except Exception as e:
                log.error(
                    f"Error during partial navigation simulation for {target_subtask_name}: {e}. No navigation performed."
                )
                actual_nav_time_used = 0.0  # Ensure time doesn't advance if nav fails

        nav_end_time = nav_start_time + actual_nav_time_used

        # --- State Update ---
        new_completed = curr_state.completed_subtasks
        if navigate_sub:
            new_completed = curr_state.completed_subtasks + [
                CompletedEntry(navigate_sub, nav_start_time, nav_end_time)
            ]

        # Create the monitoring subtask definition BUT DO NOT EXECUTE IT HERE. Add it to remaining tasks.
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=target_subtask_name, obj=target_logical_start_time
        )
        # Ensure duration is set if TaskUtil doesn't do it
        if not hasattr(mon_sub, "duration") or mon_sub.duration is None:
            mon_sub.duration = Duration(
                type="Controllable", interval=MONITORING_DURATION
            )
        elif mon_sub.duration.interval != MONITORING_DURATION:
            mon_sub.duration.interval = MONITORING_DURATION

        # Update remaining tasks: remove original candidate if it exists (though it shouldn't change), add mon_sub
        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != target_subtask_name
        ]  # Keep others
        new_remain.append(mon_sub)  # Add the monitoring task to be scheduled next
        # Add the original candidate back AFTER the monitor task? Or let constraints handle order?
        # Let constraints handle the order. Target task should already be in remaining_subtasks.
        # Ensure original candidate is still there if it wasn't the one being replaced/modified.
        original_candidate_still_needed = True  # Assume yes unless it was decomposed
        if original_candidate_still_needed and not any(
            r.name == target_subtask_name for r in new_remain
        ):
            # If the original candidate got filtered out somehow, add it back.
            # This usually shouldn't happen if we just append mon_sub.
            original_candidate_task = candidate.subtask  # Get the actual Subtask object
            new_remain.append(original_candidate_task)

        # --- Constraints Update ---
        new_constraints = copy.deepcopy(curr_state.constraints)

        # Add monitor node if needed
        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)

        # Constraint 1: Monitoring task MUST start immediately after navigation (or current time if no nav).
        # The interval is the time between the end of the *last completed task* in the PREVIOUS state
        # and the start of the monitor task. Here, the "wait" conceptually fills the gap.
        # We enforce the sequence: navigate_sub (if any) -> mon_sub

        # Determine the name of the task completed just before this expansion
        last_completed_node_name = (
            curr_node.state.subtask.name
        )  # Task completed in the parent node's state

        # If navigation occurred, the link is from navigate_sub to mon_sub
        source_node_for_mon_constraint = (
            navigate_sub.name if navigate_sub else last_completed_node_name
        )

        # Calculate the time interval between the source node end and the ideal monitor start time
        source_node_end_time = (
            nav_end_time if navigate_sub else curr_state.current_time
        )  # Time when the source node finished
        interval_source_end_to_mon_start = (
            ideal_monitor_start_time - source_node_end_time
        )
        interval_source_end_to_mon_start = max(
            0, interval_source_end_to_mon_start
        )  # Interval cannot be negative

        # Add edge: Source -> Monitor Task Start
        new_constraints.add_edge(
            source_node_for_mon_constraint,
            mon_sub.name,
            info={
                "Interval": interval_source_end_to_mon_start,
                "IsCritical": True,  # Monitoring must start at this calculated time
            },
        )
        log.debug(
            f"Added constraint: {source_node_for_mon_constraint} -> {mon_sub.name} (Interval={interval_source_end_to_mon_start:.2f}, Critical=True)"
        )

        # Constraint 2: Target candidate task MUST start immediately after monitoring finishes.
        # Interval from monitor task START to target task START is MONITORING_DURATION.
        interval_mon_start_to_target_start = MONITORING_DURATION

        new_constraints.add_edge(
            mon_sub.name,  # From monitor task start
            target_subtask_name,  # To target task start
            info={
                "Interval": interval_mon_start_to_target_start,
                "IsCritical": True,  # Target must start right after monitor finishes
            },
        )
        log.debug(
            f"Added constraint: {mon_sub.name} -> {target_subtask_name} (Interval={interval_mon_start_to_target_start:.2f}, Critical=True)"
        )

        # --- Create New State ---
        new_state = SchedulerState(
            # The subtask for this state is the navigation task if it happened, otherwise the previous task?
            # Let's set it to navigate_sub if it exists, otherwise keep the parent's completed task.
            subtask=navigate_sub if navigate_sub else curr_state.subtask,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,  # Now contains mon_sub, target_subtask, and others
            constraints=new_constraints,  # Constraints enforce mon_sub -> target_subtask order/timing
            current_time=nav_end_time,  # Time advances only to the end of navigation
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # --- Calculate Heuristic Cost ---
        # Cost of performing the navigation towards the candidate
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, new_remain
        )  # Using candidate cost is approximation
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_with_monitoring] Expanded wait for '{target_subtask_name}' by navigating towards it.\n"
            f"  -> Completed: {navigate_sub.name if navigate_sub else 'No Nav'} ({round(nav_start_time,2)}~{round(nav_end_time,2)})\n"
            f"  -> Next state time: {round(nav_end_time,2)}. Monitoring task '{mon_sub.name}' added to remaining tasks and constrained.\n"
            f"  -> Score={round(new_cost, 2)}\n"
            f"  -> Updated remain={[r.name for r in new_remain]}\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    def _expand_wait_wo_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> SimulationNode:
        """
        Inserts a single "Wait" action until the candidate's adjusted_start_time.

        - If adjusted_start_time <= current_time, wait_duration becomes 0.
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

        # [수정됨] 기다리는 시간을 조정된 시작 시간 기준으로 계산 (필드 이름 변경됨)
        wait_duration = candidate.adjusted_start_time - curr_state.current_time
        wait_duration = max(0, wait_duration)  # 음수 방지

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None, primitive_actions=[f"WAIT {wait_duration}"]
            ),
            temporal_constraints=None,
        )

        start_time = curr_state.current_time
        end_time = curr_state.current_time + wait_duration

        completed_entry = CompletedEntry(wait_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=end_time,
            scene_positions=curr_state.scene_positions,
            held_object=curr_state.held_object,
        )

        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, curr_state.remaining_subtasks
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

    # ======================
    # Helper: 모니터링 필요한지
    # ======================
    def _should_expand_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
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

        # (3) critical-constraint end => no
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        if any(slot.is_critical for slot in in_slots):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is a critical-constraint end => No monitoring."
            )
            return False

        return True
