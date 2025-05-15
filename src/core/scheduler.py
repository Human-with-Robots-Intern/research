from __future__ import annotations

import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, List, Optional

from src.core.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from src.core.task import Duration, Execution, Subtask
from src.utils.common import create_module_logger
from src.utils.common.decorators import time_logger
from utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from utils.config.constants import BEAM_WIDTH, NAV_STEP_DURATION, SIMULATION_DEPTH
from utils.task import TaskUtil

# TODO Monitoring 분기 로직 다시 확인


if TYPE_CHECKING:
    from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager

log = create_module_logger(module_name=__name__, module_log=True)

# utils.config.constants 에 PRIMITIVE_ACTION_DURATION 가 없으면 임시로 정의
try:
    from utils.config.constants import PRIMITIVE_ACTION_DURATION
except ImportError:
    log.warning(
        "PRIMITIVE_ACTION_DURATION not found in utils.config.constants, using default 0.1"
    )
    PRIMITIVE_ACTION_DURATION = 0.1  # 임시 값


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

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        expansions: List[SimulationNode] = []
        is_expanded = False

        # --- 단계 1: 정책 1 - 정시(On-time) CRITICAL 서브태스크 우선 처리 ---
        # "즉시 실행 가능한 Time-critical" 후보를 찾아, 있다면 그것 하나만 확장하고 즉시 반환.

        on_time_critical_candidate_to_expand: Optional[Candidate] = None

        # feasible_candidates를 순회하며 정책 1에 부합하는 후보를 찾음.
        # ConstraintHandler가 critical 충돌을 방지하므로, 이 조건을 만족하는 후보는 최대 하나로 가정.
        for candidate in feasible_candidates:
            if candidate.is_critical:
                if candidate.logical_interaction_start_time is None:
                    log.error(
                        f"Critical candidate {candidate.subtask.name} has None LST. Skipping."
                    )
                    continue

                physical_earliest_interaction_start_time = (
                    curr_node.state.current_time
                    + candidate.estimated_first_nav_duration
                )

                # 정책 1 조건: 논리적 상호작용 시작 시간과 물리적으로 가능한 가장 빠른 시작 시간이 거의 일치하는가?
                if (
                    abs(
                        candidate.logical_interaction_start_time
                        - physical_earliest_interaction_start_time
                    )
                    < EPSILON
                ):
                    log.debug(
                        f"[_expand_candidates] Policy 1: Found ON-TIME CRITICAL candidate: {candidate.subtask.name}."
                    )
                    # AST를 LST와 동일하게 설정하여 정확한 시간에 실행되도록 보장.
                    candidate.actual_interaction_start_time = (
                        candidate.logical_interaction_start_time
                    )

                    # (선택 사항) Candidate 객체에 missed_ideal_timing 필드가 있다면 설정
                    # if hasattr(candidate, 'missed_ideal_timing'):
                    #     candidate.missed_ideal_timing = False

                    on_time_critical_candidate_to_expand = candidate
                    break  # 정책 1에 부합하는 첫 번째 후보를 찾았으므로 더 이상 탐색 불필요

        if on_time_critical_candidate_to_expand is not None:
            log.debug(
                f"[_expand_candidates] Expanding ONLY on-time critical: {on_time_critical_candidate_to_expand.subtask.name} "
                f"at LST/AST: {on_time_critical_candidate_to_expand.logical_interaction_start_time:.2f}."
            )
            child_node = self._expand_single_subtask(
                curr_node, on_time_critical_candidate_to_expand
            )
            if child_node is not None:
                expansions.append(child_node)
                # is_expanded = True # 여기서 설정해도 되지만, 어차피 즉시 반환하므로 큰 의미는 없음.
                # 단, _simulate_search로 반환될 때 expansions에 노드가 있으므로 문제 없음.
            return (
                expansions  # 정책 1에 따라 확장된 노드(최대 1개)만 포함하여 즉시 반환
            )

        # --- 단계 1에서 정시 Critical 확장이 없었던 경우 다음 단계로 진행 ---

        # --- 단계 2: 정책 3 (놓친 CRITICAL ASAP) 및 Non-CRITICAL, 미래 CRITICAL 서브태스크 처리 ---
        # 이 단계는 정시 Critical 후보가 없었을 때만 실행됨.

        if feasible_candidates:  # 여전히 처리할 feasible 후보가 있다면
            log.debug(
                f"[_expand_candidates] No on-time critical expanded. Processing other feasible candidates."
            )

            candidates_for_stage_2_expansion: List[Candidate] = []
            for (
                candidate
            ) in feasible_candidates:  # 모든 feasible_candidates를 다시 검토
                physical_earliest_interaction_start_time = (
                    curr_node.state.current_time
                    + candidate.estimated_first_nav_duration
                )

                if candidate.is_critical:
                    # 이 후보는 정책 1의 "정시" 조건은 만족하지 못한 Critical 후보임.
                    if candidate.logical_interaction_start_time is None:  # 방어적 코드
                        log.error(
                            f"Critical candidate {candidate.subtask.name} (Stage 2) has None LST. Skipping."
                        )
                        continue

                    # 정책 3: 타이밍을 놓친 Critical (LST < 물리적 ASAP 시간) -> 가능한 빨리(ASAP) 수행
                    if (
                        candidate.logical_interaction_start_time
                        < physical_earliest_interaction_start_time - EPSILON
                    ):
                        log.warning(
                            f"[_expand_candidates] Policy 3: MISSED CRITICAL {candidate.subtask.name}. "
                            f"Ideal LST: {candidate.logical_interaction_start_time:.2f}. Will perform ASAP at {physical_earliest_interaction_start_time:.2f}."
                        )
                        # AST를 물리적 ASAP 시간으로 설정 (ConstraintHandler가 이미 이렇게 했을 가능성 높음)
                        candidate.actual_interaction_start_time = (
                            physical_earliest_interaction_start_time
                        )

                        # (선택 사항) missed_ideal_timing 플래그 설정
                        # if hasattr(candidate, 'missed_ideal_timing'):
                        #     candidate.missed_ideal_timing = True
                        candidates_for_stage_2_expansion.append(candidate)

                    # 미래의 Critical (LST >= 물리적 ASAP, 단 정시 조건은 아님) -> LST에 맞춰 수행
                    else:
                        log.debug(
                            f"[_expand_candidates] Future CRITICAL (not on-time): {candidate.subtask.name}. "
                            f"LST: {candidate.logical_interaction_start_time:.2f}, PhysicalEarliest: {physical_earliest_interaction_start_time:.2f}. "
                            f"Scheduling for LST."
                        )
                        # AST를 LST로 설정 (ConstraintHandler가 LST > physical_ASAP일 때 AST=LST로 했을 것임)
                        candidate.actual_interaction_start_time = (
                            candidate.logical_interaction_start_time
                        )

                        # (선택 사항) missed_ideal_timing 플래그 설정
                        # if hasattr(candidate, 'missed_ideal_timing'):
                        #     candidate.missed_ideal_timing = False # LST에 맞추므로 놓친 것은 아님
                        candidates_for_stage_2_expansion.append(candidate)

                else:  # Non-CRITICAL 후보
                    if candidate.logical_interaction_start_time is None:  # 방어적 코드
                        log.error(
                            f"Non-critical candidate {candidate.subtask.name} has None LST. Skipping."
                        )
                        continue

                    # AST는 max(LST, 물리적 ASAP)로 설정 (ConstraintHandler가 이미 처리했을 가능성 높음)
                    expected_actual_start_time = max(
                        candidate.logical_interaction_start_time,
                        physical_earliest_interaction_start_time,
                    )
                    # 현재 Candidate 객체의 AST가 예상과 다르면 업데이트 (일관성 유지)
                    if (
                        candidate.actual_interaction_start_time is None
                        or abs(
                            candidate.actual_interaction_start_time
                            - expected_actual_start_time
                        )
                        > EPSILON
                    ):
                        candidate.actual_interaction_start_time = (
                            expected_actual_start_time
                        )

                    # (선택 사항) missed_ideal_timing 플래그 설정
                    # if hasattr(candidate, 'missed_ideal_timing'):
                    #     candidate.missed_ideal_timing = False
                    candidates_for_stage_2_expansion.append(candidate)

            if candidates_for_stage_2_expansion:
                # 확장 대상 후보들을 정렬 (예: AST 기준, 그 다음 LST 또는 휴리스틱)
                candidates_for_stage_2_expansion.sort(
                    key=lambda c: (
                        (
                            c.actual_interaction_start_time
                            if c.actual_interaction_start_time is not None
                            else float("inf")
                        ),
                        (
                            c.logical_interaction_start_time
                            if c.logical_interaction_start_time is not None
                            else float("inf")
                        ),
                    )
                )

                for candidate_to_expand in candidates_for_stage_2_expansion:
                    log.debug(
                        f"[_expand_candidates] Stage 2: Expanding candidate: {candidate_to_expand.subtask.name} "
                        f"at AST: {candidate_to_expand.actual_interaction_start_time:.2f} "
                        f"(LST: {candidate_to_expand.logical_interaction_start_time:.2f}, Critical: {candidate_to_expand.is_critical})."
                    )
                    child_node = self._expand_single_subtask(
                        curr_node, candidate_to_expand
                    )
                    if child_node is not None:
                        expansions.append(child_node)
                        is_expanded = (
                            True  # 여기서 실제 작업 확장이 일어나면 플래그 설정
                        )

        # --- 단계 3: 정책 2 - WAIT 서브태스크 확장 ---
        # 단계 1과 단계 2에서 어떤 작업 수행 확장도 일어나지 않았을 경우에만 실행.
        if not is_expanded and not_yet_candidates:
            log.debug(
                f"[_expand_candidates] Policy 2: No task-performing subtask expanded. Considering WAIT."
            )

            # not_yet_candidates 정렬 키 개선: 유효한 미래 시간 우선
            sorted_not_feasible = sorted(
                not_yet_candidates,
                key=lambda c: (
                    c.actual_interaction_start_time  # ConstraintHandler가 설정한 미래의 AST
                    if c.actual_interaction_start_time is not None
                    and c.actual_interaction_start_time
                    > curr_node.state.current_time + EPSILON
                    else (
                        c.logical_interaction_start_time  # AST가 없거나 과거면 LST (미래)
                        if c.logical_interaction_start_time is not None
                        and c.logical_interaction_start_time
                        > curr_node.state.current_time + EPSILON
                        else float("inf")
                    )  # 둘 다 없거나 과거면 맨 뒤로
                ),
            )

            # 정렬된 리스트가 비어있지 않고, 첫 번째 후보의 정렬 기준값이 유효한 미래 시간인지 확인
            if sorted_not_feasible and (
                (
                    sorted_not_feasible[0].actual_interaction_start_time is not None
                    and sorted_not_feasible[0].actual_interaction_start_time
                    > curr_node.state.current_time + EPSILON
                )
                or (
                    sorted_not_feasible[0].logical_interaction_start_time is not None
                    and sorted_not_feasible[0].logical_interaction_start_time
                    > curr_node.state.current_time + EPSILON
                )
            ):

                wait_candidate = sorted_not_feasible[0]
                log.debug(
                    f"[_expand_candidates] Waiting for subtask: {wait_candidate.subtask.name} "
                    f"(Target AST: {wait_candidate.actual_interaction_start_time}, Target LST: {wait_candidate.logical_interaction_start_time})."
                )
                wait_node = self._expand_single_wait(curr_node, wait_candidate)
                if wait_node:
                    expansions.append(wait_node)
                    # is_expanded는 여기서 True로 설정하지 않음 (Wait은 작업 수행 확장이 아님)
            else:
                log.debug(
                    f"[_expand_candidates] No task-performing subtask expanded, and no suitable not_yet_candidates to wait for."
                )

        # expansions 리스트는 _simulate_search로 전달되어 정렬 및 Beam Pruning 대상이 됨.
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
    # (A) 서브태스크 (no monitoring)
    # -----------------------------------------------------
    def _expand_subtask_wo_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
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

        if (
            candidate.scheduling_due
            and candidate.scheduling_due.due_date
            < planned_subtask_completion_time - EPSILON
        ):
            log.warning(
                f"Scheduling due {candidate.scheduling_due.due_date:.2f} < "
                f"planned_subtask_completion_time {planned_subtask_completion_time:.2f} for {original_task_name}. Infeasible."
            )
            return None

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.total_time = total_subtask_duration_from_sim

        completed_entry = CompletedEntry(
            subtask=copied_sub,
            schedule_start_time=planned_nav_start_time,
            schedule_end_time=planned_subtask_completion_time,
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
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost

        log.info(
            f"Expanded {original_task_name} (wo_monitoring): \n"
            f"  Nav Start: {planned_nav_start_time:.2f}, Interaction Start: {planned_interaction_start_time:.2f}, Completion: {planned_subtask_completion_time:.2f}\n"
            f"  Cost: +{step_cost:.2f} -> Total: {new_cost:.2f}. Depth: {curr_depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    # -----------------------------------------------------
    # (B) 서브태스크 (with monitoring) - 정책 2 적용
    # -----------------------------------------------------
    def _expand_subtask_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
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

        # --- Phase 1: 모니터링 컨텍스트 정의 (기존과 유사) ---
        if not candidate.scheduling_due or candidate.scheduling_due.due_date == float(
            "inf"
        ):
            log.debug(
                f"Candidate {original_task_name} has no (or infinite) scheduling_due info for main critical interval. Fallback to non-monitoring."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        critical_end_sub_name = candidate.scheduling_due.due_related_sub_name

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
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

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
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        critical_start_sub_actual_end_time = (
            critical_start_completed_entry.schedule_end_time
        )

        critical_start_sub_last_interacted_object_name: Optional[str] = None
        if (
            critical_start_completed_entry.subtask.execution
            and critical_start_completed_entry.subtask.execution.primitive_actions
        ):
            last_action_str = (
                critical_start_completed_entry.subtask.execution.primitive_actions[-1]
            )
            action_parts = last_action_str.split()
            if len(action_parts) > 1:
                critical_start_sub_last_interacted_object_name = action_parts[1]
            else:
                log.warning(
                    f"Could not parse object from last action '{last_action_str}' of {critical_start_sub_name}."
                )

        if not critical_start_sub_last_interacted_object_name:
            log.warning(
                f"Could not determine last interacted object for critical_start_subtask '{critical_start_sub_name}'. "
                f"Monitoring subtask cannot be created correctly. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        log.debug(
            f"Main monitoring context for {original_task_name}: CritStart='{critical_start_sub_name}' (ends {critical_start_sub_actual_end_time:.2f}, last_obj='{critical_start_sub_last_interacted_object_name}'), "
            f"CritEnd='{critical_end_sub_name}', OriginalInterval={original_critical_interval_duration:.2f}."
        )

        # --- Phase 2: early_sub 실행 시간 계산 및 조정 (정책 2 - 1.1.3) ---
        original_absolute_monitoring_trigger_time = (
            critical_start_sub_actual_end_time
            + (original_critical_interval_duration * BAYESIAN_CRITERIA)
        )
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
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        candidate_expected_completion_time_wo_split = (
            curr_state.current_time + full_candidate_action_info_check.cumulative_time
        )

        should_even_try_split = (
            curr_state.current_time
            < original_absolute_monitoring_trigger_time - EPSILON
            and candidate_expected_completion_time_wo_split
            > original_absolute_monitoring_trigger_time - EPSILON
        )
        if not should_even_try_split:
            log.debug(
                f"Candidate {original_task_name} (expected_completion: {candidate_expected_completion_time_wo_split:.2f}) "
                f"does not warrant splitting based on original monitoring trigger {original_absolute_monitoring_trigger_time:.2f}. Fallback."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        pre_actions_log, post_actions_log = (
            self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                duration_for_early_sub_target,
            )
        )

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
                f"Failed to get valid early_actions from split for {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. Will try to add WAIT or fallback."
            )

        if (
            not early_sub_actions
            or actual_early_sub_duration < duration_for_early_sub_target
        ):
            log.debug(
                f"Early actions for {original_task_name} are too short (duration: {actual_early_sub_duration:.2f}) or empty. Attempting to add WAIT."
            )
            remaining_time_to_fill = (
                duration_for_early_sub_target - actual_early_sub_duration
            )

            if remaining_time_to_fill > EPSILON:
                wait_action_str = f"WAIT {remaining_time_to_fill:.2f}"
                early_sub_actions.append(wait_action_str)

                actual_early_sub_duration += remaining_time_to_fill
                log.info(
                    f"Added WAIT action: '{wait_action_str}'. New actual_early_sub_duration approx: {actual_early_sub_duration:.2f}"
                )
            else:
                log.debug(
                    f"No significant time ({remaining_time_to_fill:.2f}) to fill with WAIT for early_sub of {original_task_name}."
                )

        if not early_sub_actions:
            log.warning(
                f"Even after attempting to add WAIT, early_actions for {original_task_name} are empty (target duration {duration_for_early_sub_target:.2f} was too short). "
                f"Fallback to non-monitoring."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # --- Phase 3: early_sub 확장 및 실제 모니터링 시점 결정 ---
        early_sub_task = copy.deepcopy(candidate.subtask)
        early_sub_task.name = f"EARLY_{original_task_name}"
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
            curr_node, early_candidate
        )

        if node_after_early_sub is None:
            log.warning(
                f"Expansion of EARLY subtask {early_sub_task.name} failed. Aborting monitoring split for {original_task_name}."
            )
            return None

        actual_monitoring_trigger_time = node_after_early_sub.state.current_time
        log.info(
            f"  EARLY subtask {early_sub_task.name} expanded. Actual Monitoring Trigger Time: {actual_monitoring_trigger_time:.2f} "
            f"(Original trigger was: {original_absolute_monitoring_trigger_time:.2f})"
        )

        state_after_early_expansion = node_after_early_sub.state

        # --- Phase 4: mon_sub (주요 인터벌용) 및 remain_sub 생성 ---
        mon_sub_task_for_main_interval = TaskUtil.create_monitoring_subtask(
            name=f"{critical_end_sub_name}",
            obj=critical_start_sub_last_interacted_object_name,
        )
        mon_sub_task_for_main_interval.decomposed = True

        remain_sub_task_obj: Optional[Subtask] = None
        remain_sub_actions = (
            post_actions_log.get_actions()
            if post_actions_log and post_actions_log.results
            else []
        )
        if remain_sub_actions:
            remain_sub_task_obj = copy.deepcopy(candidate.subtask)
            remain_sub_task_obj.name = f"REMAIN_{original_task_name}"
            remain_sub_task_obj.execution.primitive_actions = remain_sub_actions
            remain_sub_task_obj.decomposed = True
            log.debug(
                f"Prepared REMAIN subtask: {remain_sub_task_obj.name} with {len(remain_sub_actions)} actions."
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
        if remain_sub_task_obj and not new_constraints_graph.has_node(
            remain_sub_task_obj.name
        ):
            new_constraints_graph.add_node(remain_sub_task_obj.name)

        for pred_name, _, data in original_task_in_edges_data:
            if pred_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_sub_task_obj.name if remain_sub_task_obj else ""),
                original_task_name,
                critical_start_sub_name,
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
            remain_sub_task_obj.name
            if remain_sub_task_obj
            else mon_sub_task_for_main_interval.name
        )
        for _, succ_name, data in original_task_out_edges_data:
            if succ_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_sub_task_obj.name if remain_sub_task_obj else ""),
                original_task_name,
                critical_end_sub_name,
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

        if remain_sub_task_obj:
            info_mon_to_remain = {"Interval": 0.0, "IsCritical": False}
            if not new_constraints_graph.has_edge(
                mon_sub_task_for_main_interval.name, remain_sub_task_obj.name
            ):
                new_constraints_graph.add_edge(
                    mon_sub_task_for_main_interval.name,
                    remain_sub_task_obj.name,
                    info=info_mon_to_remain,
                )
                log.debug(
                    f"Added internal constraint: '{mon_sub_task_for_main_interval.name}' -> '{remain_sub_task_obj.name}'."
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

        mon_duration = MONITORING_DURATION
        if (
            hasattr(mon_sub_task_for_main_interval, "duration")
            and hasattr(mon_sub_task_for_main_interval.duration, "interval")
            and mon_sub_task_for_main_interval.duration.interval is not None
        ):
            mon_duration = mon_sub_task_for_main_interval.duration.interval

        critical_end_sub_original_deadline = (
            critical_start_sub_actual_end_time + original_critical_interval_duration
        )
        mon_sub_expected_completion_time = actual_monitoring_trigger_time + mon_duration

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
        if remain_sub_task_obj and remain_sub_task_obj.name not in {
            r.name for r in final_remaining_subtasks_list
        }:
            final_remaining_subtasks_list.append(remain_sub_task_obj)

        log.debug(
            f"Updated remaining subtasks. Added mon: {mon_sub_task_for_main_interval.name}, remain: {remain_sub_task_obj.name if remain_sub_task_obj else 'None'}"
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
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> Optional[SimulationNode]:
        # ============== 수정 원칙 적용: prep_nav 또는 mon_sub 중 첫 단계만 실행 ================
        # 이 함수는 "모니터링을 포함한 대기"를 위한 첫 번째 단일 논리적 스텝만을 처리합니다.
        # 1. 부분 네비게이션(prep_nav_sub)이 필요하면 그것을 실행하고 해당 SimulationNode 반환.
        #    이 경우 mon_sub는 생성되어 remaining_subtasks와 제약 그래프에 추가됨.
        # 2. 부분 네비게이션이 필요 없으면, 즉시 모니터링(mon_sub)을 실행하고 해당 SimulationNode 반환.
        # =======================================================================================
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost  # SimulationNode 생성시 사용
        depth = curr_node.depth
        original_task_name = candidate.subtask.name  # 대기 대상 태스크

        log.debug(
            f"[_expand_wait_with_monitoring] Attempting wait for {original_task_name} with monitoring. Will expand FIRST STEP (prep_nav or mon_sub) only."
        )

        # M_old 식별 로직 (기존과 동일)
        M_old_name: Optional[str] = None
        if (
            curr_state.subtask  # 이전 스텝에서 완료된 subtask
            and curr_state.subtask.subtask_type == "Monitor"
            and curr_node.state.subtask
            and curr_node.state.subtask.name
            and original_task_name in curr_node.state.subtask.name
        ):
            M_old_name = curr_node.state.subtask.name
            log.debug(
                f"  Identified M_old (previous monitor potentially for {original_task_name}): {M_old_name}"
            )

        # 시간 계산 (기존 코드 참고)
        target_interaction_abs_time = candidate.actual_interaction_start_time
        if target_interaction_abs_time is None:
            log.warning(
                f"Candidate {original_task_name} has no valid actual_interaction_start_time. Cannot expand wait with monitoring."
            )
            return None

        available_total_idle_time = (
            target_interaction_abs_time - curr_state.current_time
        )
        if available_total_idle_time < -EPSILON:  # 이미 늦음
            log.warning(
                f"Target time {target_interaction_abs_time:.2f} for {original_task_name} already passed (current: {curr_state.current_time:.2f}). Cannot wait effectively."
            )
            return None  # 또는 비용을 매우 높게 설정

        # 네비게이션 대상 객체 결정 (기존 코드 참고)
        nav_target_obj = None
        if (
            candidate.subtask.execution
            and candidate.subtask.execution.primitive_actions
        ):
            # NAVIGATE_TO가 첫번째 액션일 필요는 없음. INTERACT, PICKUP 등의 대상일 수 있음.
            # 여기서는 candidate의 첫번째 primitive action의 두번째 토큰을 nav_target_obj로 가정.
            # 더 견고한 로직은 candidate.subtask.execution.objects 등을 활용해야 함.
            first_action_tokens = candidate.subtask.execution.primitive_actions[
                0
            ].split()
            if len(first_action_tokens) > 1:  # "VERB OBJECT ..." 형태
                nav_target_obj = first_action_tokens[1]
            # if ( # NAVIGATE_TO 액션이 있는 경우
            #     len(first_action_tokens) > 1
            #     and first_action_tokens[0].upper() == "NAVIGATE_TO"
            # ):
            #     nav_target_obj = first_action_tokens[1]

        # 현재 위치에서 전체 네비게이션 시간 계산 (기존 코드 참고)
        full_nav_duration_from_current_pos = 0.0
        if nav_target_obj:
            nav_action_str = f"NAVIGATE_TO {nav_target_obj}"
            # NAVIGATE_TO 액션 시뮬레이션하여 시간 얻기
            nav_info = self.action_handler.get_actions_info(curr_node, [nav_action_str])
            if nav_info and nav_info.success:
                full_nav_duration_from_current_pos = (
                    nav_info.action_duration
                )  # NAVIGATE_TO는 단일 액션
            else:
                log.warning(
                    f"Failed to get full_nav_duration for {nav_target_obj}. Assuming 0 for now, but this might be an issue."
                )
                # full_nav_duration_from_current_pos = float('inf') # 또는 실패 처리

        # 부분 네비게이션 시간 계산 (모니터링 시간 고려)
        time_for_nav_before_monitoring = available_total_idle_time - MONITORING_DURATION
        calculated_partial_nav_time = 0.0
        if (
            time_for_nav_before_monitoring > EPSILON
            and full_nav_duration_from_current_pos > EPSILON
        ):
            calculated_partial_nav_time = max(
                0.0,
                min(
                    (time_for_nav_before_monitoring // NAV_STEP_DURATION)
                    * NAV_STEP_DURATION,
                    full_nav_duration_from_current_pos,
                ),
            )

        log.debug(
            f"  Wait for {original_task_name}: AvailableIdle={available_total_idle_time:.2f}, TimeForNavBeforeMon={time_for_nav_before_monitoring:.2f}, FullNavDur={full_nav_duration_from_current_pos:.2f}, PartialNavTime={calculated_partial_nav_time:.2f}"
        )

        # --- 시나리오 분기: prep_nav 실행 또는 mon_sub 즉시 실행 ---

        if calculated_partial_nav_time > EPSILON and nav_target_obj:
            # --- 시나리오 1: prep_nav_sub 실행 ---
            log.info(
                f"  Executing PREP_NAV for {original_task_name} (duration: {calculated_partial_nav_time:.2f})"
            )
            prep_nav_actions = [
                f"NAVIGATE_TO {nav_target_obj} {calculated_partial_nav_time:.2f}"
            ]  # 시간 명시
            prep_nav_sub_name = f"NavigatePartialFor_{original_task_name}"

            # prep_nav_sub Candidate 생성 (실제로는 _expand_subtask_wo_monitoring 사용 안하고 직접 처리)
            # 여기서는 ActionHandler를 직접 호출하여 정보를 얻고 SimulationNode를 구성
            executed_prep_nav_info = self.action_handler.get_actions_info(
                curr_node, prep_nav_actions
            )

            if not (executed_prep_nav_info and executed_prep_nav_info.success):
                log.warning(
                    f"  prep_nav_sub simulation failed for {original_task_name}. Cannot expand this path."
                )
                return None

            actual_prep_nav_duration = (
                executed_prep_nav_info.cumulative_time
            )  # NAVIGATE_TO는 단일 액션, cumulative_time = action_duration

            prep_nav_sub = Subtask(
                task_name="SchedulerGenerated",
                name=prep_nav_sub_name,
                duration=Duration(
                    interval=actual_prep_nav_duration, type="Controllable"
                ),
                execution=Execution(
                    objects=[nav_target_obj] if nav_target_obj else None,
                    primitive_actions=prep_nav_actions,
                ),  # objects 수정
                decomposed=True,
                subtask_type="Navigation",
                repetition=1,
            )

            # mon_sub 객체 생성 (실행은 다음 스텝에서)
            # 모니터링 대상은 prep_nav의 목적지 또는 original_task_name의 주요 객체
            mon_target_obj_for_mon_sub = nav_target_obj  # prep_nav의 목적지를 모니터링
            # 또는 candidate.scheduling_due.due_related_sub_name 관련 객체일 수도 있음.
            # 여기서는 nav_target_obj를 사용.
            mon_sub_name_prefix = (
                candidate.scheduling_due.due_related_sub_name
                if candidate.scheduling_due
                else original_task_name
            )
            mon_sub_for_next_step = TaskUtil.create_monitoring_subtask(
                name=f"MONITOR_{mon_sub_name_prefix}_afterNav_for_{original_task_name}",
                obj=mon_target_obj_for_mon_sub,
            )
            mon_sub_for_next_step.decomposed = True

            # New SchedulerState after prep_nav
            new_completed_entries_after_prep_nav = curr_state.completed_entries + [
                CompletedEntry(
                    subtask=prep_nav_sub,
                    schedule_start_time=curr_state.current_time,
                    schedule_end_time=curr_state.current_time
                    + actual_prep_nav_duration,
                    success=True,  # 위에서 성공 체크함
                )
            ]

            new_remaining_subtasks_after_prep_nav = list(curr_state.remaining_subtasks)
            # original_task_name은 아직 남아 있어야 함. mon_sub_for_next_step을 추가.
            if mon_sub_for_next_step.name not in {
                r.name for r in new_remaining_subtasks_after_prep_nav
            }:
                new_remaining_subtasks_after_prep_nav.append(mon_sub_for_next_step)

            new_constraints_after_prep_nav = copy.deepcopy(curr_state.constraints)
            if not new_constraints_after_prep_nav.has_node(prep_nav_sub.name):
                new_constraints_after_prep_nav.add_node(prep_nav_sub.name)
            if not new_constraints_after_prep_nav.has_node(mon_sub_for_next_step.name):
                new_constraints_after_prep_nav.add_node(mon_sub_for_next_step.name)

            # 제약: M_old -> prep_nav_sub (존재 시)
            if M_old_name:
                if not new_constraints_after_prep_nav.has_node(M_old_name):
                    new_constraints_after_prep_nav.add_node(M_old_name)  # 방어
                info_m_old_to_prep = {
                    "Interval": 0.0,
                    "IsCritical": True,
                }  # M_old 이후 즉시 prep_nav 가정
                if not new_constraints_after_prep_nav.has_edge(
                    M_old_name, prep_nav_sub.name
                ):
                    new_constraints_after_prep_nav.add_edge(
                        M_old_name, prep_nav_sub.name, info=info_m_old_to_prep
                    )
                    log.debug(
                        f"  Added constraint M_old '{M_old_name}' -> prep_nav '{prep_nav_sub.name}'."
                    )

            # 제약: prep_nav_sub -> mon_sub_for_next_step
            info_prep_to_mon = {
                "Interval": 0.0,
                "IsCritical": True,
            }  # prep_nav 이후 즉시 mon 가정
            if not new_constraints_after_prep_nav.has_edge(
                prep_nav_sub.name, mon_sub_for_next_step.name
            ):
                new_constraints_after_prep_nav.add_edge(
                    prep_nav_sub.name, mon_sub_for_next_step.name, info=info_prep_to_mon
                )
                log.debug(
                    f"  Added constraint prep_nav '{prep_nav_sub.name}' -> mon_sub (next) '{mon_sub_for_next_step.name}'."
                )

            new_state_after_prep_nav = SchedulerState(
                subtask=prep_nav_sub,  # 현재 완료된 작업
                completed_entries=new_completed_entries_after_prep_nav,
                remaining_subtasks=new_remaining_subtasks_after_prep_nav,
                constraints=new_constraints_after_prep_nav,
                current_time=curr_state.current_time + actual_prep_nav_duration,
                scene_positions=executed_prep_nav_info.scene_positions,
                held_object=executed_prep_nav_info.held_object,
            )

            # 비용 계산은 candidate (original_task_name) 기준으로 수행
            step_cost = self.cost_calculator.calc_heuristic(
                curr_node, candidate
            )  # prep_nav 자체의 비용은 여기서 미미할 수 있음
            new_node_cost = curr_cost + step_cost

            log.info(
                f"  Expanded PREP_NAV '{prep_nav_sub.name}' for {original_task_name}. Next is MON_SUB '{mon_sub_for_next_step.name}'."
            )
            return SimulationNode(
                parent_node=curr_node,
                heuristic_cost=new_node_cost,  # 비용은 candidate를 기준으로 계산
                depth=depth + 1,
                tie_breaker=next(self._counter),
                state=new_state_after_prep_nav,
            )
        else:
            # --- 시나리오 2: mon_sub 즉시 실행 ---
            # (calculated_partial_nav_time <= EPSILON or nav_target_obj is None)
            # 즉시 모니터링 수행. 모니터링 시간만큼 대기 시간에 추가됨.
            log.info(
                f"  No prep_nav needed or possible. Executing MON_SUB directly for {original_task_name}."
            )

            mon_target_obj_for_immediate_mon = (
                nav_target_obj
                if nav_target_obj
                else (
                    candidate.subtask.execution.objects[0]
                    if candidate.subtask.execution.objects
                    else "UnknownObject"
                )
            )  # 현재 위치의 객체 또는 주요 객체
            if not nav_target_obj:
                log.warning(
                    f"nav_target_obj is None for immediate monitoring of {original_task_name}, using fallback."
                )

            mon_sub_name_prefix_imm = (
                candidate.scheduling_due.due_related_sub_name
                if candidate.scheduling_due
                else original_task_name
            )
            mon_sub_immediate = TaskUtil.create_monitoring_subtask(
                name=f"MONITOR_{mon_sub_name_prefix_imm}_immediate_for_{original_task_name}",
                obj=mon_target_obj_for_immediate_mon,
            )
            mon_sub_immediate.decomposed = True

            # ActionHandler를 통해 mon_sub_immediate 시뮬레이션
            executed_mon_info = self.action_handler.get_actions_info(
                curr_node, mon_sub_immediate.execution.primitive_actions
            )
            if not (executed_mon_info and executed_mon_info.success):
                log.warning(
                    f"  Immediate mon_sub simulation failed for {original_task_name}. Cannot expand."
                )
                return None

            actual_mon_duration = (
                executed_mon_info.action_duration
            )  # MONITORING_DURATION과 같아야 함

            # New SchedulerState after mon_sub
            new_completed_entries_after_mon = curr_state.completed_entries + [
                CompletedEntry(
                    subtask=mon_sub_immediate,
                    schedule_start_time=curr_state.current_time,
                    schedule_end_time=curr_state.current_time + actual_mon_duration,
                    success=True,
                )
            ]

            # original_task_name (candidate.subtask)은 아직 remaining에 있어야 함.
            new_remaining_subtasks_after_mon = list(curr_state.remaining_subtasks)
            # mon_sub_immediate는 완료되었으므로 remaining에 추가하지 않음.

            new_constraints_after_mon = copy.deepcopy(curr_state.constraints)
            if not new_constraints_after_mon.has_node(mon_sub_immediate.name):
                new_constraints_after_mon.add_node(mon_sub_immediate.name)
            if not new_constraints_after_mon.has_node(
                original_task_name
            ):  # 대기 대상 태스크
                new_constraints_after_mon.add_node(original_task_name)

            # 제약: M_old -> mon_sub_immediate (존재 시)
            if M_old_name:
                if not new_constraints_after_mon.has_node(M_old_name):
                    new_constraints_after_mon.add_node(M_old_name)
                info_m_old_to_mon_imm = {"Interval": 0.0, "IsCritical": True}
                if not new_constraints_after_mon.has_edge(
                    M_old_name, mon_sub_immediate.name
                ):
                    new_constraints_after_mon.add_edge(
                        M_old_name, mon_sub_immediate.name, info=info_m_old_to_mon_imm
                    )
                    log.debug(
                        f"  Added constraint M_old '{M_old_name}' -> mon_sub (immediate) '{mon_sub_immediate.name}'."
                    )

            # 제약: mon_sub_immediate -> original_task_name (candidate)
            # Interval = target_interaction_abs_time - (current_time + actual_mon_duration)
            interval_mon_imm_to_original = target_interaction_abs_time - (
                curr_state.current_time + actual_mon_duration
            )
            info_mon_imm_to_original = {
                "Interval": max(0.0, interval_mon_imm_to_original),
                "IsCritical": candidate.is_critical,
            }
            if not new_constraints_after_mon.has_edge(
                mon_sub_immediate.name, original_task_name
            ):
                new_constraints_after_mon.add_edge(
                    mon_sub_immediate.name,
                    original_task_name,
                    info=info_mon_imm_to_original,
                )
                log.debug(
                    f"  Added constraint mon_sub (imm) '{mon_sub_immediate.name}' -> original '{original_task_name}', Interval: {interval_mon_imm_to_original:.2f}."
                )

            new_state_after_mon = SchedulerState(
                subtask=mon_sub_immediate,  # 현재 완료된 작업
                completed_entries=new_completed_entries_after_mon,
                remaining_subtasks=new_remaining_subtasks_after_mon,
                constraints=new_constraints_after_mon,
                current_time=curr_state.current_time + actual_mon_duration,
                scene_positions=executed_mon_info.scene_positions,  # 모니터링은 위치 변경 없을 것으로 예상
                held_object=executed_mon_info.held_object,  # 모니터링은 물건 변경 없을 것으로 예상
            )

            step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
            new_node_cost = curr_cost + step_cost

            log.info(
                f"  Expanded MON_SUB (immediate) '{mon_sub_immediate.name}' for {original_task_name}. Original task still pending."
            )
            return SimulationNode(
                parent_node=curr_node,
                heuristic_cost=new_node_cost,
                depth=depth + 1,
                tie_breaker=next(self._counter),
                state=new_state_after_mon,
            )

    def _expand_wait_wo_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> Optional[SimulationNode]:  # Optional로 변경하여 실패 시 None 반환 가능하도록
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        depth = curr_node.depth
        original_task_name = candidate.subtask.name

        log.debug(
            f"[_expand_wait_wo_monitoring] Attempting partial nav + pure wait for {original_task_name}."
        )

        # 1. 시간 계산
        target_interaction_abs_time = candidate.actual_interaction_start_time
        if target_interaction_abs_time is None:
            log.warning(
                f"Candidate {original_task_name} has no valid actual_interaction_start_time. Cannot expand with wait_wo_monitoring."
            )
            return None

        available_total_idle_time = (
            target_interaction_abs_time - curr_state.current_time
        )
        if available_total_idle_time < 0:
            log.warning(
                f"Available idle time for {original_task_name} is negative ({available_total_idle_time:.2f}). Target may be missed."
            )
            # available_total_idle_time = 0 # 또는 포기

        # 2. 현재 상태 기준 전체 네비게이션 시간 재계산
        nav_target_obj = None
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
                nav_target_obj = first_action_tokens[1]

        full_nav_duration_from_current_pos = float("inf")
        if nav_target_obj:
            log.debug(
                f"  Calculating full nav time from current pos to {nav_target_obj} for {original_task_name}"
            )
            full_nav_info_now = self.action_handler.get_actions_info(
                curr_node, [f"NAVIGATE_TO {nav_target_obj}"]
            )
            if full_nav_info_now and full_nav_info_now.success:
                full_nav_duration_from_current_pos = full_nav_info_now.action_duration
            else:
                log.warning(
                    f"  Failed to get full_nav_duration from current pos for {nav_target_obj}."
                )
        else:
            log.debug(
                f"  No NAVIGATE_TO action for {original_task_name}. Full nav duration is 0."
            )
            full_nav_duration_from_current_pos = 0.0

        # 3. 부분 네비게이션 시간 결정 (모니터링 시간 제외 없음)
        time_for_nav = available_total_idle_time
        calculated_partial_nav_time = 0.0
        if time_for_nav > EPSILON and full_nav_duration_from_current_pos > EPSILON:
            calculated_partial_nav_time = max(
                0.0,
                min(
                    (time_for_nav // NAV_STEP_DURATION) * NAV_STEP_DURATION,
                    full_nav_duration_from_current_pos,
                ),
            )
        log.debug(
            f"  Available for nav: {time_for_nav:.2f}, Full nav needed: {full_nav_duration_from_current_pos:.2f}, Calculated partial nav: {calculated_partial_nav_time:.2f}"
        )

        # 4. `prep_nav_sub` 생성 및 시뮬레이션
        prep_nav_actions = []
        if calculated_partial_nav_time > EPSILON and nav_target_obj:
            prep_nav_actions.append(
                f"NAVIGATE_TO {nav_target_obj} {calculated_partial_nav_time:.2f}"
            )

        actual_prep_nav_duration = 0.0
        scene_positions_after_prep_nav = curr_state.scene_positions
        held_object_after_prep_nav = curr_state.held_object
        prep_nav_sub_success = True
        prep_nav_sub: Optional[Subtask] = None

        if prep_nav_actions:
            prep_nav_sub_name = f"Navigate Partial For {original_task_name}"
            log.debug(
                f"  Creating prep_nav_sub: {prep_nav_sub_name} with actions: {prep_nav_actions}"
            )
            executed_prep_nav_info = self.action_handler.get_actions_info(
                curr_node, prep_nav_actions
            )
            if executed_prep_nav_info and executed_prep_nav_info.success:
                actual_prep_nav_duration = executed_prep_nav_info.cumulative_time
                scene_positions_after_prep_nav = executed_prep_nav_info.scene_positions
                held_object_after_prep_nav = executed_prep_nav_info.held_object
                prep_nav_sub = Subtask(
                    task_name="SchedulerGenerated",
                    name=prep_nav_sub_name,
                    duration=Duration(
                        interval=actual_prep_nav_duration, type="Controllable"
                    ),
                    execution=Execution(
                        objects=None, primitive_actions=prep_nav_actions
                    ),
                    decomposed=True,
                    subtask_type="Navigation",
                    repetition=1,
                )
            else:
                prep_nav_sub_success = False
                log.warning(
                    f"  prep_nav_sub simulation failed for {original_task_name}."
                )
        else:
            log.debug(f"  No partial navigation actions for {original_task_name}.")

        current_time_after_prep_nav = curr_state.current_time + actual_prep_nav_duration

        # 5. `pure_wait_sub` 생성 및 시뮬레이션
        pure_wait_duration_needed = (
            target_interaction_abs_time - current_time_after_prep_nav
        )
        pure_wait_sub_actions = []
        actual_pure_wait_duration = 0.0
        pure_wait_sub_success = (
            True  # pure_wait_duration_needed <= EPSILON 이면 성공으로 간주
        )
        pure_wait_sub: Optional[Subtask] = None
        scene_positions_after_pure_wait = scene_positions_after_prep_nav
        held_object_after_pure_wait = held_object_after_prep_nav

        if pure_wait_duration_needed > EPSILON:
            pure_wait_sub_actions.append(f"WAIT {pure_wait_duration_needed:.2f}")
            pure_wait_sub_name = f"PureWaitAfterNavFor_{original_task_name}"
            log.debug(
                f"  Creating pure_wait_sub: {pure_wait_sub_name} for duration {pure_wait_duration_needed:.2f}"
            )

            # pure_wait_sub 시뮬레이션을 위한 임시 상태
            state_before_pure_wait = SchedulerState(
                subtask=prep_nav_sub,
                current_time=current_time_after_prep_nav,
                scene_positions=scene_positions_after_prep_nav,
                held_object=held_object_after_prep_nav,
                completed_entries=curr_state.completed_entries
                + (
                    [
                        CompletedEntry(
                            subtask=prep_nav_sub,
                            schedule_start_time=curr_state.current_time,
                            schedule_end_time=current_time_after_prep_nav,
                            success=prep_nav_sub_success,
                        )
                    ]
                    if prep_nav_sub
                    else []
                ),
                remaining_subtasks=curr_state.remaining_subtasks,
                constraints=curr_state.constraints,
            )
            node_before_pure_wait = SimulationNode(
                parent_node=curr_node,
                state=state_before_pure_wait,
                heuristic_cost=0,
                depth=depth,
                tie_breaker=0,
            )

            executed_pure_wait_info = self.action_handler.get_actions_info(
                node_before_pure_wait, pure_wait_sub_actions
            )
            if executed_pure_wait_info and executed_pure_wait_info.success:
                actual_pure_wait_duration = (
                    executed_pure_wait_info.action_duration
                )  # WAIT은 단일 액션
                # WAIT은 scene_positions, held_object 변경 없음
                pure_wait_sub = Subtask(
                    task_name="SchedulerGenerated",
                    name=pure_wait_sub_name,
                    duration=Duration(
                        interval=actual_pure_wait_duration, type="Controllable"
                    ),
                    execution=Execution(
                        objects=None, primitive_actions=pure_wait_sub_actions
                    ),
                    decomposed=True,
                    subtask_type="Wait",
                    repetition=1,
                )
            else:
                pure_wait_sub_success = False
                log.warning(
                    f"  pure_wait_sub simulation failed for {original_task_name}."
                )
        elif pure_wait_duration_needed < -EPSILON:  # 이미 목표 시간 지남
            log.warning(
                f"  Target interaction time {target_interaction_abs_time:.2f} already passed after prep_nav for {original_task_name}. No pure wait needed, but schedule might be late."
            )
            actual_pure_wait_duration = 0.0  # 음수 대기는 없음
        else:  # pure_wait_duration_needed가 EPSILON 이하 (거의 0)
            log.debug(
                f"  No significant pure wait needed after prep_nav for {original_task_name}."
            )
            actual_pure_wait_duration = 0.0

        # 6. CompletedEntry 생성
        new_completed_entries = list(curr_state.completed_entries)
        if prep_nav_sub:
            new_completed_entries.append(
                CompletedEntry(
                    subtask=prep_nav_sub,
                    schedule_start_time=curr_state.current_time,
                    schedule_end_time=current_time_after_prep_nav,
                    success=prep_nav_sub_success,
                )
            )
        if pure_wait_sub:
            pure_wait_start_time = current_time_after_prep_nav
            pure_wait_end_time = pure_wait_start_time + actual_pure_wait_duration
            new_completed_entries.append(
                CompletedEntry(
                    subtask=pure_wait_sub,
                    schedule_start_time=pure_wait_start_time,
                    schedule_end_time=pure_wait_end_time,
                    success=pure_wait_sub_success,
                )
            )

        # 7. 제약 조건 업데이트
        new_constraints = copy.deepcopy(curr_state.constraints)
        last_prep_activity_sub_name = (
            curr_state.subtask.name
        )  # 이전 스텝에서 완료된 태스크, 만약 없다면?

        # 7.1. (prep_nav_sub 존재 시) -> pure_wait_sub (존재 시)
        if prep_nav_sub and prep_nav_sub_success:
            last_prep_activity_sub_name = prep_nav_sub.name
            if not new_constraints.has_node(prep_nav_sub.name):
                new_constraints.add_node(prep_nav_sub.name)
            if (
                pure_wait_sub and pure_wait_sub_success
            ):  # pure_wait_sub가 있고 성공해야 연결
                if not new_constraints.has_node(pure_wait_sub.name):
                    new_constraints.add_node(pure_wait_sub.name)
                new_constraints.add_edge(
                    prep_nav_sub.name,
                    pure_wait_sub.name,
                    info={"Interval": 0.0, "IsCritical": False},
                )  # prep에서 wait는 critical하지 않을 수 있음
                last_prep_activity_sub_name = (
                    pure_wait_sub.name
                )  # 마지막 활동은 pure_wait

        # 7.2. 마지막 준비 활동 (prep_nav 또는 pure_wait) -> candidate.subtask
        if not new_constraints.has_node(original_task_name):
            log.warning(
                f"Original task {original_task_name} not in constraints. Adding node for linking."
            )
            new_constraints.add_node(original_task_name)

        # Interval은 0이 되어야 함. 이미 target_interaction_abs_time에 맞춰 prep_nav과 pure_wait을 수행했기 때문.
        # 만약 오차가 있다면 로깅.
        final_completion_time_of_prep_sequence = (
            current_time_after_prep_nav + actual_pure_wait_duration
        )
        interval_to_candidate = (
            target_interaction_abs_time - final_completion_time_of_prep_sequence
        )
        if abs(interval_to_candidate) > EPSILON * 5:  # 약간의 오차 허용
            log.warning(
                f"  Expected interaction start {target_interaction_abs_time:.2f} vs actual prep completion "
                f"{final_completion_time_of_prep_sequence:.2f} for {original_task_name} has discrepancy {interval_to_candidate:.2f}. Setting interval to 0."
            )
        # interval_to_candidate = max(0, interval_to_candidate) # 일반적으로 0에 가까워야 함

        # last_prep_activity_sub_name이 curr_state.subtask.name으로 남아있고, prep_nav/pure_wait이 없었던 경우,
        # 이전 완료 태스크에서 original_task_name으로 직접 연결.
        # 그러나 이 함수는 "대기"를 확장하므로, prep_nav 또는 pure_wait 중 적어도 하나는 수행되는 것을 가정.
        # 만약 둘 다 없다면 (available_total_idle_time <= EPSILON), 이 확장은 거의 의미가 없음.
        # 이 경우, 원래 _expand_wait_wo_monitoring (아주 짧은 WAIT만 하는 버전)으로 fallback 할 수도 있음.

        if prep_nav_sub or pure_wait_sub:  # 준비 활동이 하나라도 있었으면
            if not new_constraints.has_node(last_prep_activity_sub_name):
                new_constraints.add_node(last_prep_activity_sub_name)
            new_constraints.add_edge(
                last_prep_activity_sub_name,
                original_task_name,
                info={"Interval": 0.0, "IsCritical": candidate.is_critical},
            )
        else:  # 아무 준비 활동도 없었으면 (즉, available_total_idle_time이 매우 작았으면)
            # 이 경우는 사실상 이 확장을 할 필요가 없거나, curr_state.subtask에서 original_task_name으로 직접 연결하는 일반적인 제약이 이미 있어야 함.
            # 여기서는 이 확장이 "무언가를 해서 기다리는 것"에 초점이 맞춰져 있으므로, 아무것도 안했다면 제약 추가는 생략 가능.
            # 단, 이 경우 new_state의 current_time이 target_interaction_abs_time에 매우 가까워야 함.
            log.debug(
                f"No prep_nav or pure_wait performed for {original_task_name}. No new constraint edge from prep activities added."
            )

        # 8. 새로운 SchedulerState 생성
        final_completed_subtask_for_state = (
            pure_wait_sub if pure_wait_sub else prep_nav_sub
        )  # 마지막으로 완료된 준비 작업
        final_current_time_for_state = (
            current_time_after_prep_nav + actual_pure_wait_duration
        )
        final_scene_positions_for_state = scene_positions_after_pure_wait
        final_held_object_for_state = held_object_after_pure_wait

        # 만약 final_completed_subtask_for_state가 None이면 (아무 준비 작업도 안 함)
        # 이는 available_total_idle_time이 매우 작아서 발생.
        # 이 경우, new_state의 subtask는 curr_state.subtask, current_time은 target_interaction_abs_time이 되어야 함.
        # 하지만 이 함수는 "대기 확장"이므로, 최소한의 WAIT이라도 수행하는 것이 자연스러움.
        # 맨 처음 available_total_idle_time < 0 (또는 EPSILON)일 때 바로 return None 처리하는 것도 방법.
        if final_completed_subtask_for_state is None:
            # 이 경우는 available_total_idle_time이 매우 작아 prep_nav도 pure_wait도 생성 안됨
            # 사실상 curr_state에서 시간이 거의 흐르지 않고 candidate를 바로 시작해야 하는 상황과 유사
            # 하지만 이 함수는 "대기 확장"이므로, 이렇게 아무것도 안하는 경우는 위에서 필터링되거나
            # 아니면 아주 짧은 WAIT 하나라도 만들어야 함.
            # 현재 로직에서는 prep_nav_actions, pure_wait_sub_actions가 모두 비면 아무 subtask도 안 만들어짐.
            # 이럴 경우, SimulationNode를 반환하지 않거나 (None), 비용을 높이는 것이 적절.
            log.warning(
                f"No preparatory subtask (nav or wait) was created for {original_task_name}. This expansion might be invalid or redundant."
            )
            # return None # 또는 아래 new_heuristic_cost를 float('inf')로

        new_remaining_subtasks = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]
        if not any(r.name == original_task_name for r in new_remaining_subtasks):
            new_remaining_subtasks.append(candidate.subtask)

        new_state = SchedulerState(
            subtask=final_completed_subtask_for_state,  # None일 수 있음에 유의
            completed_entries=new_completed_entries,
            remaining_subtasks=new_remaining_subtasks,
            constraints=new_constraints,
            current_time=final_current_time_for_state,
            scene_positions=final_scene_positions_for_state,
            held_object=final_held_object_for_state,
        )

        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_heuristic_cost = curr_cost + step_cost

        if (
            not prep_nav_sub_success
            or not pure_wait_sub_success
            or final_completed_subtask_for_state is None
        ):
            log.warning(
                f"Failure in prep_nav/pure_wait or no prep activity for {original_task_name}. Increasing cost."
            )
            new_heuristic_cost = float("inf")

        log.info(
            f"Expanded wait for {original_task_name} (wo_monitoring):\n"
            f"  PrepNav: {prep_nav_sub.name if prep_nav_sub else 'None'} (Dur: {actual_prep_nav_duration:.2f}, Success: {prep_nav_sub_success})\n"
            f"  PureWait: {pure_wait_sub.name if pure_wait_sub else 'None'} (Dur: {actual_pure_wait_duration:.2f}, Success: {pure_wait_sub_success})\n"
            f"  Completion: {final_current_time_for_state:.2f}, Target Interaction: {target_interaction_abs_time:.2f}\n"
            f"  Cost: +{step_cost:.2f} -> Total: {new_heuristic_cost:.2f}. Depth: {depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_heuristic_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
