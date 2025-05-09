from __future__ import annotations

import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, List, Optional

from src.core.dataclass import Candidate, CompletedEntry, SchedulerState, SimulationNode
from src.core.task import Duration, Execution, Subtask
from src.utils.common import create_module_logger
from src.utils.common.decorators import time_logger
from utils.config import (
    BAYESIAN_CRITERIA,
    EPSILON,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    RED,
    RESET,
)
from utils.task import TaskUtil

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
        beam_width: int,
        simulation_depth: int,
        nav_graph: dict,
        action_handler: ActionHandler,
        constraint_handler: ConstraintHandler,
        heuristic_manager: HeuristicManager,
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

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """
        Expand the current node for both feasible and not-yet-feasible subtasks.

        - Feasible candidates are sorted by actual_interaction_start_time (descending),
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
        expansions: List[SimulationNode] = []
        is_expanded = False

        # * (A) Expand feasible candidates:
        # * Descending인 이유, Critical In 제약이 존재하는 subtask는 actual_interaction_start_time이 0이 아닌 current_time과 근사한 경우임
        sorted_feasible = sorted(
            feasible_candidates,
            key=lambda c: c.actual_interaction_start_time,
            reverse=True,
        )
        for candidate in sorted_feasible:

            log.debug(
                f"[_expand_candidates] Attempting to expand feasible subtask: {candidate.subtask.name}.\n"
            )
            child_node = self._expand_single_subtask(curr_node, candidate)
            if child_node is not None:
                expansions.append(child_node)
                is_expanded = True

                if (
                    candidate.is_critical
                    and candidate.logical_interaction_start_time
                    is not None  # 논리적 시작 시간 계산이 가능해야 함
                    and abs(
                        (
                            candidate.logical_interaction_start_time
                            - candidate.estimated_first_nav_duration
                        )
                        - curr_node.state.current_time
                    )
                    < EPSILON
                ):
                    # 위 조건은 "이 critical task의 (논리적) 상호작용을 제때 시작하기 위해
                    # 필요한 네비게이션 시작 시점이 현재 시간과 거의 같은가?"를 의미합니다.
                    log.debug(
                        f"Critical task {candidate.subtask.name} requires immediate start of its process (nav+interaction)."
                    )
                    break  # 이 후보를 즉시 실행 (더 이상 다른 feasible 후보를 보지 않음)

        # * (B) If we have not expanded any feasible subtask,
        # *     then we do a single Wait expansion (pick earliest not-yet-feasible)
        if not is_expanded and not_yet_candidates:
            sorted_not_feasible = sorted(
                not_yet_candidates,
                key=lambda c: (
                    c.actual_interaction_start_time
                    if c.actual_interaction_start_time is not None
                    else float("inf")
                ),
            )
            wait_candidate = sorted_not_feasible[0]
            log.debug(
                f"[_expand_candidates] No feasible expansions done. Waiting for subtask: {wait_candidate.subtask.name}.\n"
            )
            wait_node = self._expand_single_wait(curr_node, wait_candidate)
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
    ) -> SimulationNode:
        """
        Inserts necessary actions (Navigation then Wait) to meet candidate's actual_interaction_start_time.


        - If earliest_start_time <= current_time, wait_duration becomes 0.
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

        target_interaction_time = candidate.actual_interaction_start_time
        nav_duration_for_candidate = candidate.estimated_first_nav_duration

        # 네비게이션을 시작해야 하는 계획된 시간
        planned_nav_start_for_target = (
            target_interaction_time - nav_duration_for_candidate
        )

        # 순수 대기 시간 (네비게이션 시작 전까지)
        # 이 값은 0보다 작을 수 없음 (이미 feasible check를 통과했거나, not_yet 후보이므로 nav 시작은 current_time 이후)
        pure_wait_time_before_nav = max(
            0, planned_nav_start_for_target - curr_state.current_time
        )

        # 실제 네비게이션이 시작될 시간
        actual_nav_start_time = curr_state.current_time + pure_wait_time_before_nav

        # 실제 네비게이션 완료 및 상호작용 시작 시간
        actual_interaction_start_at_target = (
            actual_nav_start_time + nav_duration_for_candidate
        )

        # 이 값은 target_interaction_time과 거의 같아야 함
        if (
            abs(actual_interaction_start_at_target - target_interaction_time)
            > EPSILON * 10
        ):  # 좀 더 여유있는 엡실론
            log.warning(
                f"[_expand_wait_wo_monitoring] Mismatch in interaction time calculation for {candidate.subtask.name}."
                f" Target: {target_interaction_time:.2f}, Calculated: {actual_interaction_start_at_target:.2f}"
            )
            # 이 경우, pure_wait_time_before_nav를 조정하거나, nav_duration_for_candidate가 부정확할 수 있음.
            # 우선은 target_interaction_time을 기준으로 전체 wait subtask duration을 설정.

        # Wait Subtask 구성
        wait_sub_primitive_actions = []
        current_sim_time_offset = 0.0  # wait_sub 내부에서의 상대 시간

        # 1. 필요하다면 순수 대기 액션 추가 (네비게이션 시작 전)
        if pure_wait_time_before_nav > EPSILON:
            wait_sub_primitive_actions.append(f"WAIT {pure_wait_time_before_nav:.2f}")
            current_sim_time_offset += pure_wait_time_before_nav

        # 2. 필요하다면 네비게이션 액션 추가
        nav_target_object_id = None
        if nav_duration_for_candidate > EPSILON:
            # candidate.subtask의 첫 액션에서 네비게이션 타겟을 가져와야 함
            if (
                candidate.subtask.execution
                and candidate.subtask.execution.primitive_actions
            ):
                first_action_tokens = candidate.subtask.execution.primitive_actions[
                    0
                ].split()
                if (
                    len(first_action_tokens) > 1
                    and first_action_tokens[0].upper() == "NAVIGATE_TO"
                ):
                    nav_target_object_id = first_action_tokens[1]
                    wait_sub_primitive_actions.append(
                        f"NAVIGATE_TO {nav_target_object_id}"
                    )
                    current_sim_time_offset += (
                        nav_duration_for_candidate  # 여기서는 estimated 값 사용
                    )
                else:  # 네비게이션 액션이 아닌데 nav_duration_for_candidate 가 있는 경우 로깅
                    log.warning(
                        f"Non-NAVIGATE_TO action but nav_duration > 0 for {candidate.subtask.name}"
                    )
            else:  # primitive_actions가 없는데 nav_duration_for_candidate 가 있는 경우 로깅
                log.warning(
                    f"No primitive_actions but nav_duration > 0 for {candidate.subtask.name}"
                )

        # ActionHandler를 통해 이 wait_sub_primitive_actions의 실제 소요시간 계산
        # curr_node는 wait_sub 시작 시점의 상태 (즉, curr_node.state.current_time 에서 시작)
        wait_sub_executed_info = self.action_handler.get_actions_info(
            curr_node, wait_sub_primitive_actions
        )
        if wait_sub_executed_info is None or not wait_sub_executed_info.results:
            log.error(
                f"[_expand_wait_wo_monitoring] Failed to simulate wait subtask actions for {candidate.subtask.name}"
            )
            return None  # 확장 실패

        actual_total_duration_for_wait_sub = wait_sub_executed_info.cumulative_time

        # Wait Subtask 객체 생성
        # 이 Wait Subtask는 "candidate.subtask를 시작하기 위한 준비 작업"을 의미함
        wait_sub_obj_name = f"PrepareFor_{candidate.subtask.name}"
        if nav_target_object_id:
            wait_sub_obj_name += f"_to_{nav_target_object_id}"

        wait_sub = Subtask(
            task_name="SchedulerGenerated",
            name=wait_sub_obj_name,
            duration=Duration(
                interval=actual_total_duration_for_wait_sub, type="Controllable"
            ),
            repetition=1,
            subtask_type="Wait",  # 또는 "Preparation"
            execution=Execution(
                objects=None, primitive_actions=wait_sub_primitive_actions
            ),
            temporal_constraints=None,
        )

        # 시간 기록
        planned_wait_sub_start_time = curr_state.current_time
        planned_wait_sub_completion_time = (
            planned_wait_sub_start_time + actual_total_duration_for_wait_sub
        )

        # 이 시점이 원래 candidate의 상호작용 시작 시간과 일치해야 함
        if (
            abs(planned_wait_sub_completion_time - target_interaction_time)
            > EPSILON * 10
        ):
            log.warning(
                f"[_expand_wait_wo_monitoring] Wait sub completion time {planned_wait_sub_completion_time:.2f} "
                f"does not match target interaction time {target_interaction_time:.2f} for {candidate.subtask.name}. "
                f"Using target_interaction_time for next state."
            )
            # 오차가 크면, 다음 상태의 current_time을 target_interaction_time으로 강제할 수 있으나,
            # 이는 action_handler의 시뮬레이션 결과와 불일치를 의미하므로 원인 파악 필요.
            # 여기서는 계산된 planned_wait_sub_completion_time 사용.

        log.debug(
            f"    Expanding Wait for {candidate.subtask.name}:\n"
            f"    Current Time                    : {curr_state.current_time:.2f}\n"
            f"    Target Interaction Time         : {target_interaction_time:.2f}\n"
            f"    Est. Nav Duration for Candidate : {nav_duration_for_candidate:.2f}\n"
            f"    Pure Wait Time Before Nav       : {pure_wait_time_before_nav:.2f}\n"
            f"    Wait Sub Actions                : {wait_sub_primitive_actions}\n"
            f"    Actual Wait Sub Duration (Sim)  : {actual_total_duration_for_wait_sub:.2f}\n"
            f"    Planned Wait Sub Completion     : {planned_wait_sub_completion_time:.2f}"
        )

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            schedule_start_time=planned_wait_sub_start_time,
            schedule_end_time=planned_wait_sub_completion_time,
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        new_scene_positions = wait_sub_executed_info.scene_positions
        new_held_obj = wait_sub_executed_info.held_object

        # 다음 상태의 current_time은 wait_sub이 완료된 시간
        # 이 시간은 원래 candidate의 actual_interaction_start_time이 되어야 함.
        new_state = SchedulerState(
            subtask=wait_sub,  # 방금 완료한 wait_sub
            completed_entries=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,  # 아직 원래 candidate는 남아있음
            constraints=curr_state.constraints,  # 제약조건은 이 wait_sub에 의해 변경되지 않음
            current_time=planned_wait_sub_completion_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # Wait 확장의 비용은 어떻게 계산할 것인가?
        # candidate 자체에 대한 휴리스틱을 사용하되, 실제 진행은 wait_sub 만큼만.
        # 아니면 wait_sub 자체에 대한 비용 (주로 시간 비용)을 계산?
        # 여기서는 원래 candidate에 대한 휴리스틱을 그대로 사용 (wait는 어차피 해야 하는 것)
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate
        )  # candidate을 기다리기 위한 것이므로
        new_cost = (
            curr_cost + step_cost
        )  # 또는 step_cost를 실제 wait 시간에 기반한 값으로 변경

        log.info(
            f"[_expand_wait_wo_monitoring] Expanded {wait_sub.name} (for {candidate.subtask.name})\n"
            f"  Nav Start: {actual_nav_start_time:.2f} (if any), Wait Sub Completion: {planned_wait_sub_completion_time:.2f}\n"
            f"  Cost: +{step_cost:.2f} -> Total: {new_cost:.2f}. Depth: {depth + 1}"
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
        1) The subtask has a finite scheduling due.
        2) The subtask has not been decomposed yet (decomposed=False).
        3) The subtask is long enough that it won't finish before the monitoring cutoff.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The subtask candidate to check.

        Returns:
            bool: True if we should expand the subtask with monitoring, False otherwise.
        """
        # (1) If there's no scheduling due => no monitoring needed
        if candidate.scheduling_due.due_date == float("inf"):
            log.debug(
                f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} has no finite scheduling due => No monitoring."
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

    # -----------------------------------------------------
    # (B) 서브태스크 (with monitoring)
    # -----------------------------------------------------
    def _expand_subtask_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> Optional[SimulationNode]:
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        depth = curr_node.depth
        original_task_name = candidate.subtask.name

        log.debug(
            f"[_expand_subtask_with_monitoring] Attempting to split {original_task_name} for monitoring."
        )

        # ! ------------------- Monitoring Necessity & Timing (기존 로직 유지) -------------------
        scheduling_due_obj = candidate.scheduling_due
        # ... (critical_slots, max_critical, critical_start_sub_name, max_critical_interval 계산) ...
        # ... (cutoff, critical_constraint_start_time, expected_monitoring_start_timing 계산) ...
        # ... (전체 작업이 모니터링 시작 전에 끝나는지, 네비게이션만으로 모니터링 시간 부족한지 체크 후 fallback 로직 유지) ...
        # 이 부분은 사용자님께서 이미 잘 수정해주신 부분을 활용한다고 가정합니다.
        # (duration_for_early_sub_until_monitoring 계산 및 체크 포함)

        duration_for_early_sub_until_monitoring = (
            expected_monitoring_start_timing - curr_state.current_time
        )
        if (
            duration_for_early_sub_until_monitoring
            < candidate.estimated_first_nav_duration + EPSILON
        ):
            log.warning(
                f"Fallback: Not enough time for early_sub before monitoring for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        original_subtask_actions = candidate.subtask.execution.primitive_actions
        try:
            full_candidate_action_info = self.action_handler.get_actions_info(
                curr_node, original_subtask_actions
            )
            if not (
                full_candidate_action_info
                and full_candidate_action_info.results
                and full_candidate_action_info.results[-1].success
            ):
                log.warning(
                    f"Fallback: Full action sim failed for {original_task_name}."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate
                )  # 또는 None 반환

            total_original_subtask_duration = full_candidate_action_info.cumulative_time
            if (
                expected_monitoring_start_timing
                > curr_state.current_time + total_original_subtask_duration - EPSILON
            ):
                log.debug(
                    f"Fallback: Entire subtask {original_task_name} ends before monitoring cutoff."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

            pre_actions_info, post_actions_info = (
                self.action_handler.split_subtask_by_cutoff_time(
                    curr_node,
                    original_subtask_actions,
                    duration_for_early_sub_until_monitoring,
                )
            )
            if not (
                pre_actions_info and pre_actions_info.results and post_actions_info
            ):  # post_actions_info.results는 비어도 됨
                log.warning(
                    f"Fallback: split_subtask_by_cutoff_time failed for {original_task_name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)
            if (
                not post_actions_info.get_actions()
            ):  # Post-actions가 아예 없으면 분할 의미 없음
                log.warning(
                    f"Fallback: Post actions are empty after splitting {original_task_name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

        except ValueError as e:
            log.error(
                f"Error during action simulation/splitting for {original_task_name}: {e}"
            )
            return None

        # ! ------------------- Subtask Creation (early, mon, remain) -------------------
        # early_sub
        planned_early_sub_nav_start_time = curr_state.current_time
        duration_of_early_sub_from_sim = pre_actions_info.cumulative_time
        early_sub = copy.deepcopy(candidate.subtask)
        early_sub.name = f"{original_task_name}_early"
        early_sub.execution.primitive_actions = pre_actions_info.get_actions()
        early_sub.duration.interval = duration_of_early_sub_from_sim
        early_sub.decomposed = True
        planned_early_sub_completion_time = (
            planned_early_sub_nav_start_time + duration_of_early_sub_from_sim
        )

        if len(
            early_sub.execution.primitive_actions
        ) == 1 and early_sub.execution.primitive_actions[0].upper().startswith(
            "NAVIGATE_TO"
        ):
            log.info(f"early_sub for {original_task_name} consists only of navigation.")

        # mon_sub
        # critical_constraint_start_sub_objs는 위에서 계산되었다고 가정
        monitoring_target_obj = (
            list(critical_constraint_start_sub_objs.keys())[-1]
            if critical_constraint_start_sub_objs
            else "UnknownTarget"
        )
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=f"{original_task_name}_mon_target_{original_task_name}",
            obj=monitoring_target_obj,
        )
        mon_sub.decomposed = True
        planned_mon_sub_start_time = planned_early_sub_completion_time
        planned_mon_sub_completion_time = (
            planned_mon_sub_start_time + MONITORING_DURATION
        )

        # remain_sub
        remain_sub = copy.deepcopy(candidate.subtask)
        remain_sub.name = f"{original_task_name}_remain"

        state_before_remain_nav = SchedulerState(  # mon_sub 완료 후 상태
            subtask=mon_sub,
            current_time=planned_mon_sub_completion_time,
            scene_positions=pre_actions_info.results[
                -1
            ].scene_positions,  # early_sub 완료 후 위치
            held_object=pre_actions_info.results[
                -1
            ].held_object,  # early_sub 완료 후 상태
            completed_entries=curr_state.completed_entries
            + [
                CompletedEntry(
                    early_sub,
                    planned_early_sub_nav_start_time,
                    planned_early_sub_completion_time,
                )
            ],  # mon_sub은 아직 completed 아님
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,  # 임시
        )
        temp_sim_node_for_remain_nav = SimulationNode(
            state=state_before_remain_nav,
            heuristic_cost=0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
        )

        nav_target_for_remain = (
            post_actions_info.get_actions()[0].split()[1]
            if post_actions_info.get_actions()
            else "UnknownRemainTarget"
        )
        nav_action_for_remain_str = f"NAVIGATE_TO {nav_target_for_remain}"
        actual_nav_duration_for_remain = 0.0
        executed_nav_info_for_remain = None

        try:
            if (
                post_actions_info.get_actions()
            ):  # 실제 post_actions가 있을 때만 네비게이션 시도
                executed_nav_info_for_remain = self.action_handler.get_actions_info(
                    temp_sim_node_for_remain_nav, [nav_action_for_remain_str]
                )
                if not (
                    executed_nav_info_for_remain
                    and executed_nav_info_for_remain.results
                    and executed_nav_info_for_remain.results[-1].success
                ):
                    log.warning(
                        f"Navigation for remain_sub of {original_task_name} failed."
                    )
                    # 네비게이션 실패 시 이 확장을 실패 처리할지, 아니면 네비게이션 없이 진행할지 정책 필요. 여기서는 실패로.
                    return None
                actual_nav_duration_for_remain = (
                    executed_nav_info_for_remain.cumulative_time
                )
            else:  # post_actions_info.get_actions()가 비어있다면 (이론상 split_subtask_by_cutoff_time에서 이미 걸러졌어야 함)
                log.warning(
                    f"post_actions_info.get_actions() is empty for {original_task_name}, remain_sub will have no actions."
                )
        except ValueError as e:
            log.error(
                f"Path finding for remain_sub of {original_task_name} failed: {e}"
            )
            return None

        pure_interaction_post_actions = []
        original_post_actions_list = post_actions_info.get_actions()
        if original_post_actions_list:
            first_is_nav = (
                original_post_actions_list[0].upper().startswith("NAVIGATE_TO")
            )
            pure_interaction_post_actions = (
                original_post_actions_list[1:]
                if first_is_nav and len(original_post_actions_list) > 1
                else (
                    []
                    if first_is_nav and len(original_post_actions_list) == 1
                    else original_post_actions_list
                )
            )

        final_post_actions = (
            ([nav_action_for_remain_str] + pure_interaction_post_actions)
            if actual_nav_duration_for_remain > EPSILON
            else pure_interaction_post_actions
        )
        remain_sub.execution.primitive_actions = final_post_actions

        # remain_sub의 전체 소요 시간 (새로운 네비게이션 + 순수 상호작용)
        duration_of_remain_sub_from_sim = 0.0
        if final_post_actions:
            # remain_sub의 네비게이션 시작 시점의 상태 (mon_sub 완료 후, 새로운 네비게이션 시작 직전)
            # executed_nav_info_for_remain 이 nav_action_for_remain_str 하나에 대한 정보이므로,
            # 이 네비게이션 완료 후 상태에서 pure_interaction_post_actions를 실행해야 함.
            state_after_remain_nav = SchedulerState(
                current_time=state_before_remain_nav.current_time
                + actual_nav_duration_for_remain,
                scene_positions=(
                    executed_nav_info_for_remain.scene_positions
                    if executed_nav_info_for_remain
                    else state_before_remain_nav.scene_positions
                ),
                held_object=(
                    executed_nav_info_for_remain.held_object
                    if executed_nav_info_for_remain
                    else state_before_remain_nav.held_object
                ),
                # ... (다른 필드들도 state_before_remain_nav 기반으로 업데이트)
                subtask=None,
                completed_entries=state_before_remain_nav.completed_entries,
                remaining_subtasks=[],
                constraints=state_before_remain_nav.constraints,
            )
            temp_node_for_remain_interaction = SimulationNode(
                state=state_after_remain_nav,
                heuristic_cost=0,
                depth=0,
                tie_breaker=0,
                parent_node=None,
            )

            duration_of_post_interaction_sim = 0.0
            if pure_interaction_post_actions:
                executed_post_interaction_info = self.action_handler.get_actions_info(
                    temp_node_for_remain_interaction, pure_interaction_post_actions
                )
                if not (
                    executed_post_interaction_info
                    and executed_post_interaction_info.results
                    and executed_post_interaction_info.results[-1].success
                ):
                    log.warning(
                        f"Interaction part of remain_sub of {original_task_name} failed."
                    )
                    # 상호작용 실패 시 이 확장을 실패 처리할지 정책 필요. 여기서는 실패로.
                    return None
                duration_of_post_interaction_sim = (
                    executed_post_interaction_info.cumulative_time
                )
            duration_of_remain_sub_from_sim = (
                actual_nav_duration_for_remain + duration_of_post_interaction_sim
            )

        remain_sub.duration.interval = duration_of_remain_sub_from_sim
        remain_sub.decomposed = True

        # ! ------------------- SchedulingDue Check (early_sub 기준) -------------------
        if scheduling_due_obj.due_date < planned_early_sub_completion_time - EPSILON:
            log.warning(f"Scheduling due fail for early_sub of {original_task_name}.")
            return None

        # ! ------------------- Final State & Node Creation -------------------
        new_state = SchedulerState(
            subtask=early_sub,
            completed_entries=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=planned_early_sub_completion_time,
            scene_positions=pre_actions_info.results[-1].scene_positions,
            held_object=pre_actions_info.results[-1].held_object,
        )
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost
        log.info(
            f"Expanded {original_task_name} with monitoring: early_sub='{early_sub.name}'."
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
        depth = curr_node.depth
        original_task_name = candidate.subtask.name

        log.debug(
            f"[_expand_wait_with_monitoring] Attempting wait for {original_task_name} with monitoring."
        )

        # ! ------------------- Time Calculation (기존 로직 유지 및 강화) -------------------
        # ... (target_interaction_time_for_original_candidate, nav_duration_to_original_candidate_loc 등 계산) ...
        # ... (planned_nav_completion_time, planned_monitoring_completion_time, pure_wait_duration_after_monitoring 계산) ...
        # ... (시간 부족 시 None 반환, 시뮬레이션된 네비게이션 시간과 예상 시간 비교 후 재계산 로직 포함) ...
        # 이 부분은 사용자님께서 이미 잘 수정해주신 부분을 활용한다고 가정합니다. (try-except 포함)

        target_obj_of_candidate = candidate.subtask.execution.primitive_actions[
            0
        ].split()[1]
        target_interaction_time_for_original_candidate = (
            candidate.actual_interaction_start_time
        )
        nav_duration_to_original_candidate_loc = candidate.estimated_first_nav_duration
        planned_nav_start_time = curr_state.current_time

        # Simulate navigation for prep_nav_sub
        nav_actions_for_prep = []
        if nav_duration_to_original_candidate_loc > EPSILON:
            nav_actions_for_prep.append(f"NAVIGATE_TO {target_obj_of_candidate}")

        actual_nav_duration_sim = 0.0
        executed_nav_info = None
        new_scene_positions_after_nav = curr_state.scene_positions
        new_held_obj_after_nav = curr_state.held_object

        if nav_actions_for_prep:
            try:
                executed_nav_info = self.action_handler.get_actions_info(
                    curr_node, nav_actions_for_prep
                )
                if not (
                    executed_nav_info
                    and executed_nav_info.results
                    and executed_nav_info.results[-1].success
                ):
                    log.warning(
                        f"Navigation simulation failed for prep_nav_sub of {original_task_name}."
                    )
                    return None
                actual_nav_duration_sim = executed_nav_info.cumulative_time
                new_scene_positions_after_nav = executed_nav_info.scene_positions
                new_held_obj_after_nav = executed_nav_info.held_object
            except ValueError as e:
                log.error(
                    f"Path finding for prep_nav_sub of {original_task_name} failed: {e}"
                )
                return None

        planned_nav_completion_time = planned_nav_start_time + actual_nav_duration_sim
        # (시간 불일치 시 재계산 로직은 이미 반영되었다고 가정)
        planned_monitoring_start_time = planned_nav_completion_time
        planned_monitoring_completion_time = (
            planned_monitoring_start_time + MONITORING_DURATION
        )
        pure_wait_duration_after_monitoring = (
            target_interaction_time_for_original_candidate
            - planned_monitoring_completion_time
        )

        if pure_wait_duration_after_monitoring < -EPSILON:
            log.warning(
                f"Not enough time for nav, mon, wait for {original_task_name}. Adjusted nav_dur: {actual_nav_duration_sim:.2f}"
            )
            return None
        pure_wait_duration_after_monitoring = max(
            0, pure_wait_duration_after_monitoring
        )

        # ! ------------------- Subtask Creation (prep_nav, mon) -------------------
        prep_nav_sub_name = f"NavigateFor_{original_task_name}_Mon"
        prep_nav_sub = Subtask(
            task_name="SchedulerGenerated",
            name=prep_nav_sub_name,
            duration=Duration(interval=actual_nav_duration_sim, type="Controllable"),
            execution=Execution(objects=None, primitive_actions=nav_actions_for_prep),
            decomposed=True,
            subtask_type="Navigation",
        )
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=f"{original_task_name}_mon_target_{original_task_name}",
            obj=target_obj_of_candidate,
        )
        mon_sub.decomposed = True

        # ! ------------------- State Update (prep_nav_sub 완료 시점) -------------------
        completed_entry = CompletedEntry(
            prep_nav_sub, planned_nav_start_time, planned_nav_completion_time
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]  # 기존 candidate 제거
        new_remain.extend(
            [mon_sub, candidate.subtask]
        )  # mon_sub과 원래 subtask (이름은 같지만 객체는 다를 수 있음) 추가

        # ! ------------------- Constraints Update (Critical Chain 이전 포함) -------------------
        new_constraints = copy.deepcopy(curr_state.constraints)
        original_node_exists_in_constraint = new_constraints.has_node(
            original_task_name
        )

        # 새로운 노드들 추가 (mon_sub만. prep_nav_sub은 실행된 것으로 처리, original_task_name은 유지되거나 mon_sub 이후로 연결)
        if not new_constraints.has_node(
            mon_sub.name
        ):  # mon_sub 이름이 unique하다면 항상 추가
            new_constraints.add_node(mon_sub.name)

        # 1. mon_sub -> original_task (원래 candidate.subtask)
        # 이 연결은 항상 필요. original_task_name 노드가 없다면 새로 추가될 수도 있음 (하지만 보통은 존재).
        if not new_constraints.has_node(original_task_name):
            new_constraints.add_node(original_task_name)  # 만약을 위해
            log.warning(
                f"Original task {original_task_name} was not in constraints, added for mon_sub link."
            )

        if new_constraints.has_edge(mon_sub.name, original_task_name):
            new_constraints.edges[mon_sub.name, original_task_name]["info"].update(
                {
                    "Interval": pure_wait_duration_after_monitoring,
                    "IsCritical": candidate.is_critical,
                }
            )
        else:
            new_constraints.add_edge(
                mon_sub.name,
                original_task_name,
                info={
                    "Interval": pure_wait_duration_after_monitoring,
                    "IsCritical": candidate.is_critical,
                },
            )
        log.debug(
            f"  Added/Updated link: {mon_sub.name} -> {original_task_name} (Interval: {pure_wait_duration_after_monitoring:.2f}, Crit: {candidate.is_critical})"
        )

        # 2. Critical Chain 이전: PredCrit -> mon_sub, original_task -> SuccCrit
        if original_node_exists_in_constraint:
            in_edges_data = list(
                new_constraints.in_edges(original_task_name, data=True)
            )
            out_edges_data = list(
                new_constraints.out_edges(original_task_name, data=True)
            )

            # PredCrit -> original_task 였던 것을 PredCrit -> mon_sub 으로 변경
            # original_task으로 향하는 모든 엣지를 mon_sub으로 옮기고, original_task으로 향하는 엣지는 mon_sub->original_task 하나만 남김.
            for pred, _, data in in_edges_data:
                if pred == mon_sub.name:
                    continue  # 자기 자신으로의 루프 방지 (mon_sub -> original_task 연결은 위에서 처리)

                # pred -> original_task 엣지 제거
                if new_constraints.has_edge(pred, original_task_name):
                    new_constraints.remove_edge(pred, original_task_name)

                # pred -> mon_sub 엣지 추가. Interval 계산이 핵심.
                # I(pred, mon_sub) = I(pred, original_task_nav_start) - duration(prep_nav_sub)
                # 여기서 I(pred, original_task_nav_start)는 data['info']['Interval']
                # 이 Interval은 pred 완료 후 mon_sub 시작 (즉, prep_nav_sub 완료)까지의 시간.
                # prep_nav_sub은 current_time (pred 완료 후 시간)부터 시작해서 actual_nav_duration_sim 만큼 걸림.
                # 따라서, pred 완료 후 mon_sub 시작까지의 시간은 actual_nav_duration_sim.
                # data['info']['Interval']은 pred 완료 후 original_task (네비게이션 포함) 시작까지의 시간.
                # new_interval = data['info'].get('Interval', 0) # 기존 인터벌 유지 또는 0으로 가정
                # 여기서는 mon_sub이 prep_nav_sub 직후 시작하므로, pred -> mon_sub의 interval은
                # pred -> prep_nav_sub (0) + duration(prep_nav_sub) = actual_nav_duration_sim
                # 하지만 prep_nav_sub은 이미 실행된 것이므로, pred와 mon_sub 간의 관계는
                # (pred 완료 시점) -- (prep_nav_sub 실행 시간) --> (mon_sub 시작 시점)
                # 즉, pred가 curr_node.state.subtask라면, 그 완료시점과 prep_nav_sub의 시작시점(curr_time)은 거의 같고,
                # prep_nav_sub 완료 후 mon_sub이 시작되므로,
                # pred -> mon_sub의 interval은 actual_nav_duration_sim이 되어야 함.
                # 하지만, constraints는 보통 subtask의 "상호작용 시작" 기준.
                # **가장 간단한 접근**: original_task로 가던 critical edge들을 mon_sub으로 redirect하고,
                # interval은 원래 값을 유지하거나, constraint_handler가 재계산하도록 0으로 설정.
                # 여기서는 원래 critical 정보를 mon_sub으로 옮기는 것에 집중.

                # 만약 pred가 curr_node.state.subtask (즉, 바로 이전 작업)이라면,
                # 그 작업 완료(curr_state.current_time) 후 prep_nav_sub (actual_nav_duration_sim) 하고 mon_sub 시작.
                # 즉, curr_node.state.subtask -> mon_sub 의 Interval = actual_nav_duration_sim
                # 하지만 이 연결은 보통 SchedulerState의 흐름으로 표현됨.
                # 여기서는 original_task의 선행 critical 제약들을 mon_sub으로 옮기는 것에 집중.

                new_edge_info = copy.deepcopy(data["info"])
                # new_edge_info['Interval'] = ... (재계산 필요 또는 0)
                # 여기서는 복잡성을 줄이기 위해, IsCritical만 정확히 옮기고, Interval은 0으로 설정하여
                # 가능한 빨리 mon_sub이 고려되도록 함. 실제 시작 시간은 current_time과 SchedulingDue로 결정.
                # 여기서는 원래 critical 정보를 mon_sub으로 옮기는 것에 집중.

                # 만약 pred가 curr_node.state.subtask (즉, 바로 이전 작업)이라면,
                # 그 작업 완료(curr_state.current_time) 후 prep_nav_sub (actual_nav_duration_sim) 하고 mon_sub 시작.
                # 즉, curr_node.state.subtask -> mon_sub 의 Interval = actual_nav_duration_sim
                # 하지만 이 연결은 보통 SchedulerState의 흐름으로 표현됨.
                # 여기서는 original_task의 선행 critical 제약들을 mon_sub으로 옮기는 것에 집중.

                if new_edge_info.get("IsCritical"):  # Critical edge만 옮긴다.
                    new_edge_info["Interval"] = (
                        0  # 또는 원래 Interval 값에서 prep_nav_sub 시간 등을 빼야함.
                    )
                    # 하지만 mon_sub은 prep_nav_sub 직후 시작이므로,
                    # pred -> mon_sub의 간격은 pred -> prep_nav_sub 간격 + prep_nav_sub 길이.
                    # 여기서는 0으로 두고, SchedulingDue에 의존.
                    if not new_constraints.has_edge(pred, mon_sub.name):
                        new_constraints.add_edge(pred, mon_sub.name, info=new_edge_info)
                        log.debug(
                            f"  Redirected critical pred '{pred}' to '{mon_sub.name}' (Interval 0, Crit: True)"
                        )

            # original_task -> SuccCrit 는 그대로 유지됨. (mon_sub -> original_task -> SuccCrit)
            # 단, original_task의 시작이 pure_wait_duration_after_monitoring 만큼 늦춰지므로,
            # succ_crit_task의 SchedulingDue에 영향. 이는 ConstraintHandler가 담당.

        # ! ------------------- Final State & Node Creation -------------------
        new_state = SchedulerState(
            subtask=prep_nav_sub,
            completed_entries=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=planned_nav_completion_time,
            scene_positions=new_scene_positions_after_nav,
            held_object=new_held_obj_after_nav,
        )
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost
        log.info(
            f"Expanded wait for {original_task_name} with monitoring: prep_nav='{prep_nav_sub.name}'."
        )
        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
