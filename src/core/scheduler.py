import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.dataclass import Candidate, CompletedEntry, SchedulerState, SimulationNode
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager
from scheduler.action_handler import ActionHandler
from src.utils.common import create_module_logger
from src.utils.config import (
    BAYESIAN_CRITERIA,
    EPSILON,
    LARGE_DURATION_THRESHOLD,
    LARGE_NUMBER,
    MONITORING_DURATION,
    RED,
    RESET,
)
from src.utils.task import TaskUtil
from utils.task.constraints_util import get_critical_start_info

log = create_module_logger(module_name=__name__, module_log=True)

# Forward declaration for type hinting
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.dataclass import Candidate, CompletedEntry, SchedulerState, SimulationNode
    from core.task import Subtask
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler
    from scheduler.heuristic_manager import HeuristicManager


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
        # --- Inject dependencies ---
        action_handler: "ActionHandler",
        constraint_handler: "ConstraintHandler",
        heuristic_manager: "HeuristicManager",
    ):
        self.search = search_width
        self.simulation_depth = simulation_depth
        log.info(
            f"{RED}[Scheduler Init] search_width={search_width}, simulation_depth={simulation_depth}{RESET}"
        )

        # Use injected handlers
        self.action_handler = action_handler
        self.constraint_handler = constraint_handler
        self.cost_calculator = (
            heuristic_manager  # Use alias 'cost_calculator' internally
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

            # (1) Termination condition Check: Add node to potential solutions if goal/depth reached.
            # The search continues until the queue is empty to explore all promising branches.
            if not curr_state.remaining_subtasks:
                log.debug(
                    f"[_simulate_search] Goal state reached at depth {curr_depth}. Adding to solutions."
                )
                best_solutions.append(curr_node)
                continue  # Continue exploring other potential solutions in the queue
            if curr_depth >= self.simulation_depth:
                log.debug(
                    f"[_simulate_search] Max depth ({curr_depth}) reached. Adding to solutions."
                )
                best_solutions.append(curr_node)
                continue  # Continue exploring other potential solutions in the queue

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
            # Sort by heuristic cost to prioritize adding lower cost nodes first
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)

            # (3) Local Beam Pruning: Keep only the top-K expansions
            # Filter out clearly infeasible nodes (cost = LARGE_NUMBER) before adding to queue,
            # but allow high-cost nodes to be potentially pruned by better alternatives.
            nodes_added_to_queue = 0
            for nd in expanded_nodes:
                # Add node if its cost is not infinity and we haven't reached the beam width limit
                if (
                    nd.heuristic_cost
                    < LARGE_NUMBER  # Allow high cost, but not infinite
                    and nodes_added_to_queue < self.search
                ):
                    queue.put(nd)
                    nodes_added_to_queue += 1
                elif nd.heuristic_cost >= LARGE_NUMBER:
                    # Log if a node is pruned due to extremely high cost (optional)
                    log.warning(  # Changed from debug to warning
                        f"Node for {nd.state.subtask.name if nd.state.subtask else 'Wait'} has >= LARGE_NUMBER cost ({nd.heuristic_cost:.2f}). "
                        f"Pruning this path. Verify HeuristicManager's LARGE_NUMBER criteria accurately reflects irrecoverable states."  # Added clarification
                    )
                # Implicitly prune nodes if nodes_added_to_queue >= self.search

        if not best_solutions:
            log.error(
                "[_simulate_search] No solutions found after exploring the search space."
            )
            return None

        # Select the best solution (lowest cost) from all collected solutions
        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        log.info(  # Use info level for final result
            f"[_simulate_search] Best solution node found with cost={best_solutions[0].heuristic_cost:.2f} at depth {best_solutions[0].depth}."
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

        # --- MODIFIED: Expand feasible candidates first ---
        if feasible_candidates:
            log.debug(
                f"[_expand_candidates] Expanding {len(feasible_candidates)} feasible candidates."
            )
            sorted_feasible = sorted(
                feasible_candidates,
                key=lambda c: c.adjusted_start_time,
                reverse=False,
            )
            for candidate in sorted_feasible:
                is_critical_now = (
                    candidate.is_critical
                    and abs(
                        candidate.adjusted_start_time - curr_node.state.current_time
                    )
                    < EPSILON  # Use config EPSILON, not CRITICAL_TIME_TOLERANCE here
                )

                if is_critical_now:
                    log.info(
                        f"[_expand_candidates] Critical Task {candidate.subtask.name} needs immediate start (Adj. EST: {candidate.adjusted_start_time:.2f}). Expanding."
                    )
                    child_node = self._expand_single_subtask(curr_node, candidate)
                    # 2.2: 크리티컬 확장 실패 시 분기 가지치기
                    if child_node is None or child_node.heuristic_cost >= LARGE_NUMBER:
                        log.error(
                            f"[_expand_candidates] Expansion failed (or resulted in LARGE_NUMBER cost) for CRITICAL task {candidate.subtask.name}. "
                            f"Pruning this branch immediately."
                        )
                        return []  # 즉시 빈 리스트 반환하여 가지치기
                    expansions.append(child_node)

                elif not candidate.is_critical or (
                    candidate.is_critical and not is_critical_now
                ):
                    log.debug(
                        f"[_expand_candidates] Attempting feasible: {candidate.subtask.name} (Adj. EST: {candidate.adjusted_start_time:.2f})"
                    )
                    child_node = self._expand_single_subtask(curr_node, candidate)
                    # 여기서도 None 또는 LARGE_NUMBER 비용 노드는 추가하지 않음 (Beam search에서 처리)
                    if child_node and child_node.heuristic_cost < LARGE_NUMBER:
                        expansions.append(child_node)
                    elif child_node is None:
                        log.warning(
                            f"Expansion returned None for non-critical {candidate.subtask.name}"
                        )
                    # else: LARGE_NUMBER cost node is implicitly pruned by not adding

        # --- MODIFIED: Only consider wait if NO feasible candidates exist ---
        elif not feasible_candidates and not_yet_candidates:
            # 2.1: 로그 메시지 개선 (로직 변경 없음)
            log.info(
                f"[_expand_candidates] No feasible candidates found. Considering {len(not_yet_candidates)} not-yet-feasible candidates for wait expansion."
                f" Current strategy: wait for the one with the earliest adjusted start time."  # 전략 명시
            )
            best_wait_candidate = min(
                not_yet_candidates, key=lambda c: c.adjusted_start_time
            )

            log.debug(
                f"[_expand_candidates] Generating wait expansion for the earliest not-yet-feasible: {best_wait_candidate.subtask.name} (Adjusted EST: {best_wait_candidate.adjusted_start_time:.2f})."
            )
            wait_node = self._expand_single_wait(curr_node, best_wait_candidate)
            # LARGE_NUMBER 비용 노드는 추가하지 않음
            if wait_node and wait_node.heuristic_cost < LARGE_NUMBER:
                expansions.append(wait_node)
            elif wait_node is None:
                log.warning(
                    f"Wait expansion returned None for {best_wait_candidate.subtask.name}"
                )
            # else: LARGE_NUMBER cost node is implicitly pruned

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
        # 모니터링 필요 여부 판단 (이 로직의 복잡성 및 BAYESIAN_CRITERIA 검증 필요)
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
        # 모니터링 wait? (nav_time > 0.1 and candidate.is_critical 조건의 일반적 타당성 검토 필요)
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

        # * (1) 실제 실행 시간 (ActionHandler None 반환 처리 추가)
        last_action_info = self.action_handler.get_actions_info(curr_node, sub_actions)
        # Check if action simulation was successful
        if (
            last_action_info is None
            or last_action_info.time_used
            < 0  # Check for negative time as error indicator
        ):
            log.error(
                f"[_expand_subtask_wo_monitoring] Failed to get valid action info for {candidate.subtask.name}. Cannot expand."
            )
            # Return a node with infinite cost to indicate failure, letting beam search handle pruning
            return SimulationNode(
                parent_node=curr_node,
                heuristic_cost=LARGE_NUMBER,  # Indicate infeasibility
                depth=curr_node.depth + 1,
                tie_breaker=next(self._counter),
                state=curr_node.state,  # Stay in the same state effectively
            )
        # --- MODIFIED: Add check for abnormally large time ---
        elif (
            last_action_info.time_used > LARGE_DURATION_THRESHOLD
        ):  # Define LARGE_DURATION_THRESHOLD appropriately in config
            log.warning(
                f"[_expand_subtask_wo_monitoring] Action simulation for {candidate.subtask.name} resulted "
                f"in unusually large duration: {last_action_info.time_used:.2f}. Proceeding, but check ActionHandler/Simulator."
            )

        start_time = curr_state.current_time
        end_time = start_time + last_action_info.time_used

        # * (2) subtask 종료 시각이 deadline보다 느리면 infeasible 수정
        # 기존: candidate.deadline.due_date < end_time - EPSILON
        # 수정: end_time이 deadline을 명확히 초과하면 infeasible
        if end_time > candidate.deadline.due_date + EPSILON:
            log.debug(
                f"[_expand_subtask_wo_monitoring] Deadline {candidate.deadline.due_date:.2f} violated by "
                f"subtask end time {end_time:.2f} for {candidate.subtask.name}. Infeasible expansion."
            )
            # Return a node with infinite cost
            return SimulationNode(
                parent_node=curr_node,
                heuristic_cost=LARGE_NUMBER,
                depth=curr_node.depth + 1,
                tie_breaker=next(self._counter),
                state=curr_node.state,  # 상태는 변경하지 않음 (실패한 확장)
            )

        # * (3) subtask 복사 & duration 설정 (기존 로직 유지)
        copied_sub = copy.deepcopy(candidate.subtask)
        # Duration interval represents the *expected* duration, not updating with simulated time here.

        # * (4) subtask 실행 후, 실제 최종 위치/held_object 반영 (기존 로직 유지)
        new_held_obj = last_action_info.held_object
        new_scene_positions = last_action_info.scene_positions

        completed_entry = CompletedEntry(copied_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != candidate.subtask.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,  # 원본 subtask 정보 사용 (duration 등)
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=curr_state.constraints,
            current_time=end_time,  # 시간은 실제 소요 시간으로 업데이트
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # 휴리스틱 계산 (오류 발생 가능성 있음, LARGE_NUMBER 반환 가능)
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node,
            candidate,
            new_remain,
            actual_duration=last_action_info.time_used,  # 실제 소요 시간 전달 (옵션)
        )
        # calc_heuristic 수정 필요: actual_duration 인자 추가 또는 내부에서 재계산 방지

        # 휴리스틱 계산이 실패하거나 매우 높은 비용을 반환해도 노드는 생성
        # Beam search will prune based on cost comparison later
        if step_cost >= LARGE_NUMBER:
            log.warning(
                f"[_expand_subtask_wo_monitoring] Expansion for {candidate.subtask.name} resulted in LARGE_NUMBER heuristic cost ({step_cost}). Node created but likely pruned."
            )
            # No longer returning None here, let beam search handle it

        new_cost = curr_node.heuristic_cost + step_cost

        log.info(
            f"[_expand_subtask_wo_monitoring] Subtask {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, 2)}, Interval={round(start_time,2)}~{round(end_time,2)}\n"
            f"  -> Updated remain={[r.name for r in new_remain]}\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,  # 계산된 비용 사용 (LARGE_NUMBER일 수 있음)
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
        curr_depth = curr_node.depth

        log.debug(
            f"[_expand_subtask_with_monitoring] Splitting subtask {candidate.subtask.name} into monitoring form."
        )
        # ! ------------------- Re-check monitoring necessity constraints -------------------
        # Re-validate that the deadline constraint triggering this monitoring split
        # is still valid and critical in the current constraint graph state.
        # This differs from _should_expand_with_monitoring, which checks the candidate itself.
        # * 1) We identify the relevant "critical" slot for the subtask's deadline
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        # Find all critical constraints leading *into* the deadline subtask
        constraints_start_names = self.constraint_handler.get_time_slots(
            deadline_sub_name, curr_node.state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            # If no critical constraints lead to the deadline task anymore,
            # monitoring based on that deadline is unnecessary. Fallback to normal expansion.
            log.debug(
                f"[_expand_subtask_with_monitoring] No critical constraints found leading to deadline task '{deadline_sub_name}'. "
                f"Monitoring split is not needed based on this candidate's deadline. Falling back to normal subtask expansion."
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
        # --- MODIFIED: Add error handling if critical start info not found ---
        found_critical_start = False
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_constraint_start_time = ce.end_time
                critical_constraint_start_sub_objs = ce.subtask.execution.objects
                found_critical_start = True  # Mark as found
                break
        # --- If critical start task not found in completed, cannot proceed reliably ---
        if not found_critical_start:
            log.error(
                f"[_expand_subtask_with_monitoring] Critical start subtask '{critical_start_sub_name}' "
                f"not found in completed tasks for node at time {curr_state.current_time:.2f}. "
                f"Cannot reliably calculate monitoring timings or update constraints. Aborting expansion."
            )
            return None  # Return None to indicate failure

        # --- MODIFIED: Check if monitoring target object is found ---
        if not critical_constraint_start_sub_objs:
            log.error(
                f"[_expand_subtask_with_monitoring] Could not determine monitoring target object from "
                f"critical start subtask '{critical_start_sub_name}'. Aborting expansion."
            )
            return None  # Return None if target object cannot be determined

        expected_monitoring_start_timing = critical_constraint_start_time + cutoff

        # * 4) Check if the entire subtask ends before the monitoring cutoff
        # --- MODIFIED: Add check for valid last_action_info ---
        last_action_info = self.action_handler.get_actions_info(
            curr_node, candidate.subtask.execution.primitive_actions
        )
        if last_action_info is None or last_action_info.time_used < 0:
            log.error(
                f"[_expand_subtask_with_monitoring] Failed to get valid action info for candidate "
                f"'{candidate.subtask.name}'. Cannot determine execution time. Aborting expansion."
            )
            return None  # Return None if action simulation fails

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
            name=candidate.subtask.name, obj=monitoring_target_obj
        )

        log.debug(
            f"[_expand_subtask_with_monitoring] Created early_sub={early_sub.name}, "
            f"mon_sub ({mon_sub.name}), remain_sub={remain_sub.name}"
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

        # ---- START: Critical Chain Edges Correction (Reflecting Semantic Correction & Logical Time Basis) ----

        # Calculate the LOGICAL start time of the monitoring task based on the critical constraint start and Bayesian cutoff.
        # This avoids discrepancies caused by variable navigation/early_sub execution time.
        expected_monitoring_logical_start_time = (
            critical_constraint_start_time + cutoff
        )  # cutoff = max_critical_interval * BAYESIAN_CRITERIA

        # Edge: Critical Start -> Monitoring Task Start
        # Interval is the time from the critical start event's end to the *logical* start time of the monitor task.
        interval_crit_start_to_mon_start_logical = max(
            0, expected_monitoring_logical_start_time - critical_constraint_start_time
        )
        # Note: This interval should ideally match 'cutoff' if critical_constraint_start_time is accurate.

        new_constraints.add_edge(
            critical_start_sub_name,
            mon_sub.name,
            info={
                # Use logical interval based on cutoff
                "Interval": interval_crit_start_to_mon_start_logical,
                "IsCritical": True,
            },
        )
        log.debug(
            f"Added critical edge: {critical_start_sub_name} -> {mon_sub.name} with LOGICAL Interval={interval_crit_start_to_mon_start_logical:.2f} (based on cutoff)"
        )

        # Edge: Monitoring Task End -> Original Deadline Subtask Start
        # The interval reflects the remaining time from the *logical* start of mon_sub + its duration
        # to the original deadline subtask's *logical* start (which is critical_start_end_time + max_critical_interval).
        original_deadline_sub_logical_start = (
            critical_constraint_start_time + max_critical_interval
        )
        monitor_task_logical_end_time = (
            expected_monitoring_logical_start_time + MONITORING_DURATION
        )  # Assuming MONITORING_DURATION is fixed

        remain_critical_interval_logical = max(
            0, original_deadline_sub_logical_start - monitor_task_logical_end_time
        )

        new_constraints.add_edge(
            mon_sub.name,  # From the end of monitoring task
            deadline_sub_name,  # To the start of the task ending the critical period
            info={
                # Use remaining interval based on logical timings
                "Interval": remain_critical_interval_logical,
                "IsCritical": True,
            },
        )
        log.debug(
            f"Added critical edge: {mon_sub.name} -> {deadline_sub_name} with Remaining LOGICAL Interval={remain_critical_interval_logical:.2f}"
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
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    # -----------------------------------------------------
    # (C) Wait expansions
    # -----------------------------------------------------
    def _expand_wait_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> Optional[SimulationNode]:
        """
        Expands a wait action for a critical candidate with partial navigation
        and planned monitoring. Uses logical_start_time for monitoring timing.
        """
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        target_subtask_name = candidate.subtask.name
        target_logical_start_time = candidate.logical_start_time
        log.debug(
            f"[_expand_wait_with_monitoring] Calculating timings for {target_subtask_name} "
            f"based on LogicalEST: {target_logical_start_time:.2f} "
            f"(AdjustedEST was: {candidate.adjusted_start_time:.2f})"
        )

        # --- Determine Navigation Target ---
        target_obj_id = None
        try:
            target_obj_id = candidate.subtask.execution.primitive_actions[0].split()[1]
        except (IndexError, AttributeError):
            log.error(
                f"Cannot determine nav target for {target_subtask_name}. Cannot expand wait."
            )
            return None

        # --- Calculate Timings (논리적 시작 시간 기준) ---
        ideal_monitor_start_time = target_logical_start_time - MONITORING_DURATION
        available_time_for_nav = ideal_monitor_start_time - curr_state.current_time

        partial_nav_time = 0.0
        if available_time_for_nav < EPSILON:
            log.warning(
                f"Wait time too short ({available_time_for_nav:.2f}) for nav before ideal monitoring for {target_subtask_name}."
            )
            partial_nav_time = 0.0
        else:
            try:
                nav_action_str = f"NAVIGATE_TO {target_obj_id}"
                full_nav_time_info = self.action_handler.get_actions_info(
                    curr_node, [nav_action_str]
                )
                # [수정] get_actions_info는 ActionResult 반환, 단일 액션이므로 time_used 사용
                full_nav_time = (
                    full_nav_time_info.time_used if full_nav_time_info else 0.0
                )
                partial_nav_time = max(0, min(available_time_for_nav, full_nav_time))
                log.debug(f"Calculated partial_nav_time: {partial_nav_time:.2f}")
            except Exception as e:
                log.error(
                    f"Error calculating nav time for {target_obj_id}: {e}. Assuming 0."
                )
                partial_nav_time = 0.0

        # --- Simulate ONLY Partial Navigation ---
        nav_start_time = curr_state.current_time
        actual_nav_time_used = 0.0
        navigate_sub = None
        new_scene_positions = copy.deepcopy(curr_state.scene_positions)
        new_held_obj = curr_state.held_object

        if partial_nav_time > EPSILON:
            try:
                nav_action_str = f"NAVIGATE_TO {target_obj_id} {partial_nav_time}"
                nav_action = [nav_action_str]
                temp_sim_node_for_nav = SimulationNode(
                    state=copy.deepcopy(curr_state),
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

                    # [수정] Navigate 서브태스크 생성 시 objects 수정
                    navigate_sub = Subtask(
                        task_name=None,
                        name=f"Navigate({target_obj_id})_{round(actual_nav_time_used,1)}s_for_{target_subtask_name}",
                        duration=Duration(
                            interval=actual_nav_time_used, type="Controllable"
                        ),
                        repetition=1,
                        type="Interaction",
                        execution=Execution(
                            objects={target_obj_id: 1} if target_obj_id else {},
                            primitive_actions=nav_action,
                        ),
                        decomposed=True,
                    )
                else:
                    log.warning(
                        f"Partial navigation simulation failed for {target_obj_id}. No nav."
                    )
                    actual_nav_time_used = 0.0
            except Exception as e:
                log.error(
                    f"Error during partial nav simulation for {target_subtask_name}: {e}. No nav."
                )
                actual_nav_time_used = 0.0

        nav_end_time = nav_start_time + actual_nav_time_used

        # --- State Update ---
        new_completed = list(curr_state.completed_subtasks)
        if navigate_sub:
            new_completed.append(
                CompletedEntry(navigate_sub, nav_start_time, nav_end_time)
            )

        # [수정] 모니터링 서브태스크 생성 시 obj 인자 확인
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=candidate.subtask.name,  # 또는 target_subtask_name 사용
            obj=target_obj_id,
        )
        mon_sub.name = f"Monitor({target_obj_id})_for_{target_subtask_name}"
        mon_sub.duration = Duration(type="Controllable", interval=MONITORING_DURATION)
        mon_sub.decomposed = True

        # 남은 태스크 업데이트
        new_remain = [r for r in curr_state.remaining_subtasks]
        if not any(r.name == mon_sub.name for r in new_remain):
            new_remain.append(mon_sub)
        if not any(r.name == target_subtask_name for r in new_remain):
            log.warning(
                f"Target candidate {target_subtask_name} missing in remaining. Re-adding."
            )
            new_remain.append(candidate.subtask)

        # --- Constraints Update --- (이전과 동일)
        new_constraints = copy.deepcopy(curr_state.constraints)

        # --- Required context for constraint updates ---
        # Identify the critical constraint that triggered this wait/monitoring
        # This requires looking up the constraint graph based on the candidate we are waiting FOR.
        monitoring_target_sub_name = candidate.subtask.name  # The task we wait for

        # We need the critical constraint leading INTO the 'monitoring_target_sub_name'
        # AND the constraint starting the critical period for that deadline.
        # This logic is complex and might need access similar to _expand_subtask_with_monitoring
        # For now, assume we can retrieve these names/times (Placeholder logic):
        # --- MODIFIED: Wrap critical info retrieval in try-except and return None on failure ---
        critical_start_sub_name = None
        critical_start_sub_end_time = 0.0
        deadline_sub_name = None
        max_critical_interval = 0.0
        cutoff = 0.0
        try:
            crit_info = get_critical_start_info(  # Assuming a helper function exists or is added
                subtask_name=monitoring_target_sub_name,
                completed=curr_state.completed_subtasks,
                constraints=new_constraints,
                constraint_handler=self.constraint_handler,  # Pass the handler
            )
            if crit_info is None:  # Check if helper function indicated failure
                raise ValueError("get_critical_start_info returned None")

            critical_start_sub_name = crit_info[0]
            critical_start_sub_end_time = crit_info[1]

            deadline_sub_name = (
                candidate.deadline.subtask_name
            )  # Assuming reliable deadline info

            if not new_constraints.has_edge(critical_start_sub_name, deadline_sub_name):
                # Might happen if constraints changed, log a warning but might be okay if handled later
                log.warning(
                    f"No direct edge found between critical start '{critical_start_sub_name}' and deadline '{deadline_sub_name}'. Constraint update might be partial."
                )
                # Allow proceeding, but be aware. Alternatively, could return None here too if strictness needed.
            else:
                edge_data = new_constraints.get_edge_data(
                    critical_start_sub_name, deadline_sub_name
                )
                if edge_data and edge_data.get("info", {}).get("IsCritical"):
                    max_critical_interval = float(
                        edge_data.get("info", {}).get("Interval", 0.0)
                    )
                else:
                    # If the edge isn't critical anymore, monitoring based on it might be invalid.
                    log.warning(
                        f"Edge between '{critical_start_sub_name}' and '{deadline_sub_name}' is no longer marked critical. Monitoring rationale might be outdated."
                    )
                    # Depending on requirements, could return None here. For now, proceed with interval 0.

            # Calculate cutoff based on Bayesian criteria (assuming constant)
            # This might need adjustment if BAYESIAN_CRITERIA is dynamic
            from src.utils.config import BAYESIAN_CRITERIA  # Import locally if needed

            if max_critical_interval <= 0:
                log.warning(
                    f"Max critical interval is {max_critical_interval:.2f}. Cutoff calculation might be zero."
                )
            cutoff = max_critical_interval * BAYESIAN_CRITERIA

        except Exception as e:
            log.error(
                f"[_expand_wait_with_monitoring] Failed to retrieve or process critical constraint info for {monitoring_target_sub_name}: {e}. Constraint update unreliable. Aborting.",
                exc_info=True,  # Include traceback
            )
            return None  # Return None to indicate failure

        # --- Constraint Updates (Adapted for Wait + Monitor) ---
        # Check if nodes exist before adding edges
        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)
        # --- MODIFIED: Add checks before adding edges ---
        if critical_start_sub_name and new_constraints.has_node(
            critical_start_sub_name
        ):
            expected_monitoring_logical_start_time = (
                critical_start_sub_end_time + cutoff
            )
            interval_crit_start_to_mon_start_logical = max(
                0, expected_monitoring_logical_start_time - critical_start_sub_end_time
            )
            # Avoid adding self-loops or redundant edges if logic allows
            if critical_start_sub_name != mon_sub.name:
                new_constraints.add_edge(
                    critical_start_sub_name,
                    mon_sub.name,
                    info={
                        "Interval": interval_crit_start_to_mon_start_logical,
                        "IsCritical": True,
                    },
                )
                log.debug(
                    f"Added critical edge: {critical_start_sub_name} -> {mon_sub.name} Interval={interval_crit_start_to_mon_start_logical:.2f}"
                )
        else:
            log.warning(
                f"Cannot add edge from critical start '{critical_start_sub_name}' to '{mon_sub.name}'. Node missing or name is None."
            )

        # Connect Monitor task to the original task it monitors
        if (
            new_constraints.has_node(monitoring_target_sub_name)
            and mon_sub.name != monitoring_target_sub_name
        ):
            # Interval might be 0 if original task starts immediately after monitoring
            new_constraints.add_edge(
                mon_sub.name,
                monitoring_target_sub_name,  # Connect monitor to the task we waited for
                info={
                    "Interval": 0,  # Adjust if needed based on logic
                    "IsCritical": False,  # Usually non-critical link
                },
            )
        else:
            log.warning(
                f"Cannot add edge from monitor '{mon_sub.name}' to target '{monitoring_target_sub_name}'. Node missing or self-loop."
            )

        # Re-establish the critical link from monitor end to the task that ENDS the critical section
        if (
            deadline_sub_name
            and new_constraints.has_node(deadline_sub_name)
            and mon_sub.name != deadline_sub_name
        ):
            # Calculate remaining logical interval (ensure critical_start_sub_end_time was valid)
            if (
                critical_start_sub_name is not None
            ):  # Only calculate if we had a valid start
                original_deadline_sub_logical_start = (
                    critical_start_sub_end_time + max_critical_interval
                )
                monitor_task_logical_end_time = (
                    expected_monitoring_logical_start_time + MONITORING_DURATION
                )
                remain_interval_logical = max(
                    0,
                    original_deadline_sub_logical_start - monitor_task_logical_end_time,
                )

                # Remove the original direct critical edge if it exists
                if critical_start_sub_name and new_constraints.has_edge(
                    critical_start_sub_name, deadline_sub_name
                ):
                    try:
                        new_constraints.remove_edge(
                            critical_start_sub_name, deadline_sub_name
                        )
                        log.debug(
                            f"Removed original critical edge: {critical_start_sub_name} -> {deadline_sub_name}"
                        )
                    except (
                        nx.NetworkXError
                    ):  # Handle case where edge might have been removed already
                        log.debug(
                            f"Original critical edge {critical_start_sub_name} -> {deadline_sub_name} not found for removal."
                        )

                new_constraints.add_edge(
                    mon_sub.name,
                    deadline_sub_name,
                    info={
                        "Interval": remain_interval_logical,
                        "IsCritical": True,
                    },
                )
                log.debug(
                    f"Added critical edge: {mon_sub.name} -> {deadline_sub_name} Interval={remain_interval_logical:.2f}"
                )
            else:
                log.warning(
                    f"Cannot calculate remaining logical interval for {mon_sub.name} -> {deadline_sub_name} due to missing critical start info."
                )
        else:
            log.warning(
                f"Cannot add critical edge from monitor '{mon_sub.name}' to deadline '{deadline_sub_name}'. Node missing or self-loop."
            )

        # Update incoming/outgoing edges for the original 'monitoring_target_sub_name'
        # This needs careful handling - should they now point to/from the monitor task?
        # This part is complex and requires clear definition of how wait+monitor interacts
        # with existing constraints of the waited-for task.
        # --- Placeholder for potential edge redirection ---
        # Example: Edges previously pointing to 'monitoring_target_sub_name' might now point to 'mon_sub.name'
        # Edges previously originating from 'monitoring_target_sub_name' might still originate from it.

        # --- State Creation (using updated constraints) ---
        new_state = SchedulerState(
            subtask=(
                navigate_sub if navigate_sub else mon_sub
            ),  # Task executed in this step
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,  # Use updated constraints
            current_time=nav_end_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # --- Calculate Heuristic Cost ---
        # Note: Candidate passed might be the original 'wait for X', heuristic needs care
        # Pass the actual executed subtask (nav or monitor) or handle appropriately inside heuristic
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node,
            candidate,
            new_remain,  # Heuristic needs to understand wait/monitor context
        )
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_with_monitoring] Expanded wait for '{target_subtask_name}'. "
            f"Completed: {navigate_sub.name if navigate_sub else 'No Nav'} ({round(nav_start_time,2)}~{round(nav_end_time,2)}). "
            f"Next state time: {round(nav_end_time,2)}. Monitor '{mon_sub.name}' added."
            f" Score={round(new_cost, 2)}"
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
        curr_depth = curr_node.depth

        # * (1) subtask가 시작될 때까지 기다려야 하는 시간 계산
        # adjusted_start_time은 이미 navigation 시간을 고려한 값임
        # current_time보다 adjusted_start_time이 이전이면 즉시 시작 가능 (wait_duration = 0)
        wait_duration = candidate.adjusted_start_time - curr_state.current_time
        if wait_duration < 0:
            log.debug(
                f"[_expand_wait_wo_monitoring] Adjusted start time {candidate.adjusted_start_time:.2f} is before current time {curr_state.current_time:.2f} "
                f"for {candidate.subtask.name}. Clamping wait duration {wait_duration:.2f} to 0."
            )
            wait_duration = 0  # 음수 대기 시간은 0으로 처리

        start_time = curr_state.current_time + wait_duration  # 대기 후 시작 시간
        end_time = start_time  # Wait 액션 자체의 시간은 0

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
            depth=curr_depth + 1,
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

        # (3) critical-constraint end => no monitoring?
        # TODO: Review this condition. The definition of "critical-constraint end" and its implication
        # on monitoring necessity needs careful validation. A task might be at the end of an incoming
        # critical path but still require monitoring due to its own deadline or duration uncertainty.
        # This logic might be too simplistic depending on the specific monitoring goals.
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        if any(slot.is_critical for slot in in_slots):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} has an incoming critical edge. "
                f"Assuming it doesn't need *this type* of monitoring split. (Review Needed)"  # 로그 명확화
            )
            return False  # 기존 로직 유지

        # If none of the above conditions are met, monitoring might be needed.
        log.debug(
            f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} meets initial criteria for potential monitoring split."
        )
        return True  # Renamed variable for clarity and returned directly
