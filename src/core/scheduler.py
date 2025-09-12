from __future__ import annotations

import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, List, Optional

from src.models.dataclass import (
    ActionResult,
    ActionSimulationLog,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from src.models.task import Duration, Execution, Subtask
from src.utils.common import create_module_logger
from src.utils.common.decorators import time_logger
from src.utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from src.utils.config.constants import (
    BEAM_WIDTH,
    NAV_STEP_DURATION,
    ON_TIME_CRITICAL_TOLERANCE,  # TIMING_TOLERANCE 대신 사용
    SIMULATION_DEPTH,
    TASK_SPLIT_TIMING_TOLERANCE,
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
            log.debug(
                f"[_simulate_search] Expanded {len(expanded_nodes)} nodes from current node."
            )

            # (3) Local Beam Pruning: Keep only the top-K expansions
            pruned_nodes = 0
            for i, nd in enumerate(expanded_nodes):
                if i < self.search_width:
                    queue.put(nd)
                else:
                    pruned_nodes += 1
                    # No need to process further if we've filled the beam
            if pruned_nodes > 0:
                log.debug(
                    f"[_simulate_search] Kept {self.search_width} best nodes, pruned {pruned_nodes} nodes."
                )

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
        is_expanded_from_feasible = False

        # --- 단계 1: 정책 1 - 정시(On-time) CRITICAL 서브태스크 우선 처리 ---
        # "즉시 실행 가능한 Time-critical" 후보를 찾아, 있다면 그것 하나만 확장하고 즉시 반환.
        # "정시(On-time)"란, 물리적으로 가장 빨리 상호작용을 시작할 수 있는 시간과
        # 논리적으로 계획된 상호작용 시작 시간(LST)의 차이가 거의 없는 경우를 의미.
        on_time_critical_candidate_to_expand: Optional[Candidate] = None

        for candidate in feasible_candidates:
            if candidate.is_critical:
                if candidate.logical_interaction_start_time is None:
                    log.error(
                        f"Critical candidate {candidate.subtask.name} has None LST. Skipping."
                    )
                    continue
                candidate.logical_interaction_start_time = max(
                    EPSILON, candidate.logical_interaction_start_time
                )
                physical_earliest_interaction_start_time = (
                    curr_node.state.current_time
                    + candidate.estimated_first_nav_duration
                )

                if (
                    abs(
                        candidate.logical_interaction_start_time
                        - physical_earliest_interaction_start_time
                    )
                    < ON_TIME_CRITICAL_TOLERANCE
                ):
                    # 정시성 조건이 충족된 경우
                    log.debug(
                        f"[_expand_candidates] Policy 1: Found ON-TIME CRITICAL candidate: {candidate.subtask.name}."
                    )
                    candidate.actual_interaction_start_time = (
                        candidate.logical_interaction_start_time
                    )
                    on_time_critical_candidate_to_expand = candidate
                    break

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
                return expansions  # 정시 Critical 확장 시 즉시 반환
            else:
                log.warning(
                    f"On-time critical candidate '{on_time_critical_candidate_to_expand.subtask.name}' "
                    f"was found to be infeasible during expansion. "
                    f"Proceeding to evaluate other candidates or WAIT policy."
                )

        # --- 단계 1에서 정시 Critical 확장이 없었던 경우 다음 단계로 진행 ---
        # is_expanded 플래그를 사용하여 작업 수행 확장이 일어났는지 추적
        is_expanded_from_feasible = False

        # --- 단계 2.1: 놓친 CRITICAL 서브태스크 우선 처리 ---
        # LST(논리적 시작 시간)가 이미 물리적으로 가능한 가장 빠른 시작 시간을 지난 경우 "놓친(MISSED)" 것으로 간주.
        # 이런 태스크들은 지연을 최소화하기 위해 즉시 실행(ASAP) 대상으로 우선 확장.
        urgent_criticals_to_expand: List[Candidate] = []
        other_feasible_candidates_for_later: List[Candidate] = []

        if feasible_candidates:  # feasible_candidates가 있을 때만 이 로직 수행
            for candidate in feasible_candidates:
                physical_earliest_interaction_start_time = (
                    curr_node.state.current_time
                    + candidate.estimated_first_nav_duration
                )
                if candidate.is_critical:
                    if candidate.logical_interaction_start_time is None:
                        log.error(
                            f"Critical candidate {candidate.subtask.name} (Urgent Check) has None LST. Adding to others."
                        )
                        other_feasible_candidates_for_later.append(
                            candidate
                        )  # LST 없는 Critical은 일단 other로
                        continue

                    # "놓친 Critical" 작업만 식별
                    is_missed_critical = (
                        candidate.logical_interaction_start_time
                        < physical_earliest_interaction_start_time
                    )

                    if is_missed_critical:
                        log.warning(
                            f"[_expand_candidates] Prioritizing MISSED CRITICAL: {candidate.subtask.name}. "
                            f"LST: {candidate.logical_interaction_start_time:.2f}, PhysicalEarliest: {physical_earliest_interaction_start_time:.2f}. Will perform ASAP."
                        )
                        candidate.actual_interaction_start_time = (
                            physical_earliest_interaction_start_time
                        )
                        urgent_criticals_to_expand.append(candidate)
                    # "임박한 Critical" 조건 제거됨. 놓치지 않은 모든 Critical은 other_feasible_candidates_for_later로.
                    else:  # Not MISSED CRITICAL (i.e., LST >= physical_earliest_interaction_start_time)
                        log.debug(
                            f"[_expand_candidates] Future (non-missed) CRITICAL: {candidate.subtask.name}. "
                            f"LST: {candidate.logical_interaction_start_time:.2f}. Will be scheduled for LST in later stage if not expanded now."
                        )
                        candidate.actual_interaction_start_time = (
                            candidate.logical_interaction_start_time
                        )  # LST에 수행 예정
                        other_feasible_candidates_for_later.append(candidate)
                else:  # Non-CRITICAL 후보
                    if candidate.logical_interaction_start_time is None:
                        log.error(
                            f"Non-critical candidate {candidate.subtask.name} has None LST. Skipping for now."
                        )
                        continue

                    expected_actual_start_time = max(
                        candidate.logical_interaction_start_time,
                        physical_earliest_interaction_start_time,
                    )
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
                    other_feasible_candidates_for_later.append(candidate)

            if urgent_criticals_to_expand:
                log.debug(
                    f"[_expand_candidates] Stage 2.1: Expanding {len(urgent_criticals_to_expand)} MISSED critical candidate(s)."
                )
                # 놓친 Critical 작업들은 가능한 빨리 시작해야 하므로 AST(즉, 물리적 ASAP) 순으로 정렬
                urgent_criticals_to_expand.sort(
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
                        ),  # Tie-breaker
                    )
                )
                for urgent_candidate in urgent_criticals_to_expand:
                    child_node = self._expand_single_subtask(
                        curr_node, urgent_candidate
                    )
                    if child_node is not None:
                        expansions.append(child_node)
                        is_expanded_from_feasible = True

        # --- 단계 2.2: 나머지 FEASIBLE (Non-CRITICAL 및 미래 CRITICAL) 서브태스크 처리 ---
        # 놓친 Critical 작업이 확장되지 않았을 경우에만 실행 (또는 놓친 Critical 작업이 없었을 경우)
        if not is_expanded_from_feasible and other_feasible_candidates_for_later:
            log.debug(
                f"[_expand_candidates] Stage 2.2: No MISSED criticals expanded or none found. Processing {len(other_feasible_candidates_for_later)} other feasible candidates."
            )
            other_feasible_candidates_for_later.sort(
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
            for other_candidate in other_feasible_candidates_for_later:
                # AST 설정은 위에서 이미 처리되었을 것임 (Future Critical, Non-Critical 모두)
                log.debug(
                    f"[_expand_candidates] Stage 2.2: Expanding candidate: {other_candidate.subtask.name} "
                    f"at AST: {other_candidate.actual_interaction_start_time:.2f} "
                    f"(LST: {other_candidate.logical_interaction_start_time:.2f}, Critical: {other_candidate.is_critical})."
                )
                child_node = self._expand_single_subtask(curr_node, other_candidate)
                if child_node is not None:
                    expansions.append(child_node)
                    is_expanded_from_feasible = True

        # --- 단계 3: 정책 2 - WAIT 서브태스크 확장 ---
        # 단계 1과 단계 2 (2.1, 2.2 모두 포함)에서 어떤 작업 수행 확장도 일어나지 않았을 경우에만 실행.
        if not is_expanded_from_feasible and not_yet_candidates:
            log.debug(
                f"[_expand_candidates] Policy WAIT: No task-performing subtask expanded. Considering WAIT."
            )
            # not_yet_candidates 정렬 키 개선: 유효한 미래 시간 우선
            # 1. ConstraintHandler가 계산한 예상 실제 시작 시간 (미래인 경우)
            # 2. 1번이 없으면, 논리적 시작 시간 (미래인 경우)
            # 3. 둘 다 없거나 과거 시간이면 우선순위를 낮춤 (inf)
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
                or (  # AST가 없는 경우 LST로 판단
                    sorted_not_feasible[0].actual_interaction_start_time
                    is None  # AST가 없을 때 LST를 사용하기 위한 조건 추가
                    and sorted_not_feasible[0].logical_interaction_start_time
                    is not None
                    and sorted_not_feasible[0].logical_interaction_start_time
                    > curr_node.state.current_time + EPSILON
                )
            ):

                wait_candidate = sorted_not_feasible[0]
                # Wait 대상의 AST가 없다면 LST를 사용하도록 명시 (실제로는 ConstraintHandler가 AST를 채워줄 것으로 예상)
                wait_target_time_for_log = (
                    wait_candidate.actual_interaction_start_time
                    if wait_candidate.actual_interaction_start_time is not None
                    else wait_candidate.logical_interaction_start_time
                )
                log.debug(
                    f"[_expand_candidates] Waiting for subtask: {wait_candidate.subtask.name} "
                    f"(Target Time for Wait: {wait_target_time_for_log}, LST: {wait_candidate.logical_interaction_start_time})."
                )
                wait_node = self._expand_single_wait(curr_node, wait_candidate)
                if wait_node:
                    expansions.append(wait_node)
            else:
                log.debug(
                    f"[_expand_candidates] No task-performing subtask expanded, and no suitable not_yet_candidates to wait for (or all targets are in the past/too soon)."
                )

        # expansions 리스트는 _simulate_search로 전달되어 정렬 및 Beam Pruning 대상이 됨.
        return expansions

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
        # if candidate.subtask.name.startswith("Monitoring"):
        #     print(candidate.subtask.execution.primitive_actions)
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
        if candidate.subtask.name.startswith("Monitoring"):
            print(candidate.subtask.execution.primitive_actions)
        target_obj_id = candidate.subtask.execution.primitive_actions[0].split()[1]
        nav_time = self.action_handler.get_actions_info(
            curr_node,
            [f"NAVIGATE_TO {target_obj_id}"],
        ).action_duration
        log.debug(
            f"[_expand_single_wait] Subtask {candidate.subtask.name}'s navigation time: {nav_time}. ({target_obj_id})"
        )

        # Critical 태스크를 기다릴 때, 이동 시간이 길다면(e.g., 0.5초 이상)
        # 중간에 세상의 상태가 변할 수 있다는 불확실성을 고려하여 모니터링을 포함한 대기(wait)를 수행.
        if nav_time > 0.5 and candidate.is_critical:
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
        # if candidate.subtask.decomposed:
        #     log.debug(
        #         f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is already decomposed => No monitoring."
        #     )
        #     return False

        # (3) critical-constraint end => no
        # in_slots = self.constraint_handler.get_time_slots(
        #     candidate.subtask.name, curr_node.state.constraints, direction="in"
        # )
        # if any(slot.is_critical for slot in in_slots):
        #     log.debug(
        #         f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is a critical-constraint end => No monitoring."
        #     )
        #     return False

        # 현재 로직에서는 유한한 due_date를 가진 모든 태스크가 모니터링 분할 대상이 됨.
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

        # due_date(마감 시간)가 설정된 경우, 태스크 완료 예상 시간이 마감 시간을 넘지 않는지 확인.
        if (
            candidate.scheduling_due
            and candidate.scheduling_due.due_date <= planned_subtask_completion_time
        ):
            # 현재 candidate의 완료 시간이 due_date를 넘는 경우에는 Infeasible case; 확장 불가
            log.warning(
                f"Scheduling due {candidate.scheduling_due.due_date:.2f} < "
                f"planned_subtask_completion_time {planned_subtask_completion_time:.2f} for {original_task_name}. Infeasible."
            )
            return None

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
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
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
        # Critical Subtask가 Not yet에 없는 경우에는 Monitoring할 필요가 없음
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

        monitoring_target_obj = next(
            remain_sub.execution.primitive_actions[0].split()[1]
            for remain_sub in curr_node.state.remaining_subtasks
            if remain_sub.name == critical_end_sub_name
        )

        if not monitoring_target_obj:
            log.warning(
                f"Could not determine last interacted object for critical_start_subtask '{critical_start_sub_name}'. "
                f"Monitoring subtask cannot be created correctly. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

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
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        candidate_expected_completion_time_wo_split = (
            curr_state.current_time + full_candidate_action_info_check.cumulative_time
        )

        should_even_try_split = (
            curr_state.current_time < original_absolute_monitoring_trigger_time
            and candidate_expected_completion_time_wo_split
            > original_absolute_monitoring_trigger_time
        )

        log.info(f"{original_absolute_monitoring_trigger_time=}")
        log.info(f"{candidate_expected_completion_time_wo_split=}")

        if not should_even_try_split:
            log.debug(
                f"Candidate {original_task_name} (expected_completion: {candidate_expected_completion_time_wo_split:.2f}) "
                f"does not warrant splitting based on original monitoring trigger {original_absolute_monitoring_trigger_time:.2f}. Fallback."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # 액션 핸들러를 통해 현재 태스크를 모니터링 시점을 기준으로 두 부분(pre/post)으로 나눔.
        pre_actions_log, post_actions_log, split_successful, pre_ends_holding_object = (
            self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                duration_for_early_sub_target,
            )
        )

        if not split_successful or pre_ends_holding_object:
            log.warning(
                f"Failed to split {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. Will try to add WAIT or fallback."
            )
            return None

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
                f"Failed to get valid early_actions from split for {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. Will try to add WAIT or fallback."
            )
            return None

        ideal_early_sub_duration = duration_for_early_sub_target

        lower_bound = ideal_early_sub_duration * (1 - TASK_SPLIT_TIMING_TOLERANCE)
        upper_bound = ideal_early_sub_duration * (1 + TASK_SPLIT_TIMING_TOLERANCE)

        if not (lower_bound <= actual_early_sub_duration <= upper_bound):
            log.info(
                f"[_expand_subtask_with_monitoring] Subtask '{original_task_name}' (actual early_duration: {actual_early_sub_duration:.2f}) "
                f"does not meet timing tolerance for ideal early_duration ({ideal_early_sub_duration:.2f}, bounds: [{lower_bound:.2f}, {upper_bound:.2f}]). "
                f"Skipping monitoring split for this candidate."
            )
            return None

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
            obj=monitoring_target_obj,
        )
        mon_sub_task_for_main_interval.decomposed = True

        remain_sub_task: Optional[Subtask] = None
        remain_sub_actions = (
            post_actions_log.get_actions()
            if post_actions_log and post_actions_log.results
            else []
        )
        if not remain_sub_actions[0].startswith("NAVIGATE_TO"):
            if remain_sub_actions[0].split()[1] in curr_state.scene_positions:
                remain_sub_actions = [
                    f"NAVIGATE_TO {remain_sub_actions[0].split()[1]}"
                ] + remain_sub_actions
            else:
                remain_sub_actions = [
                    f"NAVIGATE_TO {remain_sub_actions[1].split()[1]}"
                ] + remain_sub_actions
        elif remain_sub_actions[0].startswith("WAIT"):
            remain_sub_actions = [
                f"NAVIGATE_TO {remain_sub_actions[1].split()[1]}"
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
        # 분할된 태스크(early, mon, remain)들을 제약조건 그래프에 통합.
        # 기존 태스크 노드를 제거하고, 분할된 새 노드들을 추가한 뒤, 의존 관계를 재설정.
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

        # 5-1. 기존 태스크로 들어오던 엣지들을 early_sub로 연결
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

        # 5-2. 기존 태스크에서 나가던 엣지들을 가장 마지막 태스크(remain_sub 또는 mon_sub)에서 나가도록 연결
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

        # 5-3. 분할된 태스크들 간의 내부 순서 제약조건 추가 (early -> mon -> remain)
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

        # 5-4. 메인 Critical Interval 제약조건을 모니터링 태스크 기준으로 재설정
        # (CritStart -> mon_sub)
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

        # (mon_sub -> CritEnd)
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

        # 5-5. remaining_subtasks 리스트 업데이트
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
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> SimulationNode:
        """
        Inserts a single "Wait" action until the candidate's actual_interaction_start_time.

        - If actual_interaction_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with Navigation, Monitoring and Wait actions.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            SimulationNode: The child node representing the new state after waiting.
        """
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        total_wait_duration = (
            candidate.actual_interaction_start_time - curr_state.current_time
        )
        if total_wait_duration < 0:
            raise ValueError(
                f"[_expand_wait_with_monitoring] Negative wait duration: {total_wait_duration}"
            )
        target_obj = candidate.subtask.execution.primitive_actions[0].split()[1]
        full_nav_time = self.action_handler.get_actions_info(
            curr_node, [f"NAVIGATE_TO {target_obj}"]
        ).action_duration
        #!  Refactoring 필요
        # 대기 시간 동안 가능한 만큼 미리 이동(partial navigation)하는 시간을 계산.
        # NAV_STEP_DURATION 단위로 시간을 양자화하여, 대기 시간 내에 끝낼 수 있는 최대 이동 시간을 구함.
        partial_nav_time = min(
            (
                int(
                    (candidate.actual_interaction_start_time - curr_state.current_time)
                    // NAV_STEP_DURATION
                )
                * NAV_STEP_DURATION
            ),
            full_nav_time,
        )
        log.warning(
            f"Partial Navigation Time: {partial_nav_time} / {candidate.actual_interaction_start_time - curr_state.current_time}"
        )
        if partial_nav_time < 0:
            raise ValueError(
                f"[_expand_wait_with_monitoring] Negative partial navigation time: {partial_nav_time}"
            )

        nav_action = [f"NAVIGATE_TO {target_obj} {partial_nav_time}"]
        nav_action_info = self.action_handler.get_actions_info(curr_node, nav_action)
        nav_time = nav_action_info.cumulative_time
        new_scene_positions = nav_action_info.scene_positions
        new_held_obj = nav_action_info.held_object

        navigate_sub = Subtask(
            task_name=None,
            name=f"Navigate to {target_obj} during {partial_nav_time}",
            duration=Duration(interval=nav_time, type="Controllable"),
            repetition=1,
            subtask_type="Interaction",
            execution=Execution(objects=None, primitive_actions=nav_action),
            temporal_constraints=None,
        )

        mon_sub = TaskUtil.create_monitoring_subtask(
            name=candidate.subtask.name, obj=target_obj
        )

        new_remain = [r for r in curr_state.remaining_subtasks]
        new_remain.extend([mon_sub])

        start_time = curr_state.current_time
        end_time = start_time + nav_time

        completed_entry = CompletedEntry(
            subtask=navigate_sub,
            schedule_start_time=start_time,
            schedule_end_time=end_time,
            schedule_nav_time=nav_time,
            execution_status=True,
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        # ! ------------------- Constraints Update -------------------
        # 대기 액션으로 인해 생성된 모니터링 태스크를 제약조건 그래프에 추가.
        # 기존 태스크 -> 모니터링 -> 기다리던 태스크 순서로 엣지를 연결하여 의존성 생성.
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
                "Interval": total_wait_duration - MONITORING_DURATION - nav_time,
                "IsCritical": True,
            },
        )

        # Agent position/state 변경은 거의 없음(Wait)
        new_state = SchedulerState(
            subtask=navigate_sub,
            completed_entries=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=end_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_with_monitoring] Subtask {navigate_sub.name}\n"
            f"  -> Score={round(new_cost, 2)}, "
            f"Interval={round(start_time,2)}~{round(end_time,2)}\n"
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

        total_wait_duration = (
            candidate.actual_interaction_start_time - curr_state.current_time
        )

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

        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
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
