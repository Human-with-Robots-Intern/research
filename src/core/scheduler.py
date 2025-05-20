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
    SimulationNode,
)
from src.models.task import Duration, Execution, Subtask
from src.utils.common import create_module_logger
from src.utils.common.decorators import time_logger
from utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from utils.config.constants import BEAM_WIDTH, NAV_STEP_DURATION, SIMULATION_DEPTH
from utils.task import TaskUtil

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
                    # 있을 수 없는 조건, Feasible하면 반드시 LST가 있어야 함 (선행 작업이 완료된 상태니까)
                    log.error(
                        f"Critical candidate {candidate.subtask.name} has None LST. Skipping."
                    )
                    continue

                # 물리적으로 상호작용할 수 있는 가장 이른 시각
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

            return expansions

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
                        # 이미 LST 타이밍을 놓친 경우, actual_interaction_start_time을 물리적 ASAP 시간으로 설정
                        log.warning(
                            f"[_expand_candidates] Policy 3: MISSED CRITICAL {candidate.subtask.name}. "
                            f"Ideal LST: {candidate.logical_interaction_start_time:.2f}. Will perform ASAP at {physical_earliest_interaction_start_time:.2f}."
                        )
                        # AST를 물리적 ASAP 시간으로 설정 (ConstraintHandler가 이미 이렇게 했을 가능성 높음)
                        candidate.actual_interaction_start_time = (
                            physical_earliest_interaction_start_time
                        )

                        candidates_for_stage_2_expansion.append(candidate)

                    # 미래의 Critical (LST >= 물리적 ASAP, 단 정시 조건은 아님) -> LST에 맞춰 수행
                    else:
                        log.debug(
                            f"[_expand_candidates] Future CRITICAL (not on-time): {candidate.subtask.name}. "
                            f"LST: {candidate.logical_interaction_start_time:.2f}, PhysicalEarliest: {physical_earliest_interaction_start_time:.2f}. "
                            f"Scheduling for LST."
                        )
                        # AST를 LST로 설정 (이미 ConstraintHandler가 LST > physical_ASAP일 때 AST=LST로 했을 것임)
                        candidate.actual_interaction_start_time = (
                            candidate.logical_interaction_start_time
                        )

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
        if candidate.subtask.name.startswith("Monitoring"):
            print(candidate.subtask.execution.primitive_actions)
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
            and candidate.scheduling_due.due_date <= planned_subtask_completion_time
        ):
            # 현재 candidate의 완료 시간이 due_date를 넘는 경우에는 Infeasible case; 확장 불가ㄴ
            log.warning(
                f"Scheduling due {candidate.scheduling_due.due_date:.2f} < "
                f"planned_subtask_completion_time {planned_subtask_completion_time:.2f} for {original_task_name}. Infeasible."
            )
            return None

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.total_time = total_subtask_duration_from_sim

        # Tree 확장용으로 CompletedEntry의 execution status를 action_handler sim 결과를 저장하게 함.
        # 또한 저 멤버에는 실제 실행 성공 여부도 포함됨... 음... 이래도 되려나?

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

        # ? 남는 시간을 subtask를 expansion하게 해야 하는거 아닌가?
        if actual_early_sub_duration < duration_for_early_sub_target:
            # return self._expand_subtask_wo_monitoring(curr_node, candidate)
            log.debug(
                f"Early actions for {original_task_name} are too short (duration: {actual_early_sub_duration:.2f}) or empty. Attempting to add WAIT."
            )
            remaining_time_to_fill = (
                duration_for_early_sub_target - actual_early_sub_duration
            )

            if remaining_time_to_fill > EPSILON:
                wait_action_str = f"WAIT {remaining_time_to_fill}"
                early_sub_actions.append(wait_action_str)

                actual_early_sub_duration += remaining_time_to_fill
                log.info(
                    f"Added WAIT action: '{wait_action_str}'. New actual_early_sub_duration approx: {actual_early_sub_duration:.2f}"
                )
            else:
                log.debug(
                    f"No significant time ({remaining_time_to_fill:.2f}) to fill with WAIT for early_sub of {original_task_name}."
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
        if remain_sub_actions:
            remain_sub_task = copy.deepcopy(candidate.subtask)
            remain_sub_task.name = f"REMAIN_{original_task_name}"
            remain_sub_task.execution.primitive_actions = [
                f"NAVIGATE_TO {remain_sub_actions[0].split()[1]}"
            ] + remain_sub_actions
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

        if new_constraints_graph.has_edge(
            critical_start_sub_name, critical_end_sub_name
        ):
            edge_data = new_constraints_graph.get_edge_data(
                critical_start_sub_name, critical_end_sub_name
            )
            if edge_data and edge_data.get("info", {}).get("IsCritical", False):
                new_constraints_graph.remove_edge(
                    critical_start_sub_name, critical_end_sub_name
                )
                log.debug(
                    f"Removed old direct critical edge: '{critical_start_sub_name}' -> '{critical_end_sub_name}'"
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
