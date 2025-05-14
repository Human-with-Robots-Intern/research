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
        """
        Expand the current node for both feasible and not-yet-feasible subtasks.

        - Feasible candidates are sorted by actual_interaction_start_time (descending),
          then expanded via `_expand_single_subtask`.
        - If no feasible expansion is done and we have not-yet-feasible tasks,
          we insert a single Wait expansion or Nav + Monitoring + Wait expansion (the earliest not-yet-feasible candidate).
          These approaches are a simplified approach to "waiting" until a subtask becomes feasible.

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
        # * Ascending Order: Critical In 제약이 존재하는 subtask는 actual_interaction_start_time이 0이 아닌 current_time과 근사한 경우임
        sorted_feasible = sorted(
            feasible_candidates,
            key=lambda c: c.actual_interaction_start_time,
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
            candidate.scheduling_due.due_date
            < planned_subtask_completion_time - EPSILON
        ):
            log.warning(
                f"Scheduling due {candidate.scheduling_due.due_date:.2f} < "
                f"planned_subtask_completion_time {planned_subtask_completion_time:.2f} for {original_task_name}. Infeasible."
            )
            return None

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = total_subtask_duration_from_sim

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

        # ! ------------------- Monitoring Necessity & Timing -------------------
        candidate_due_info = candidate.scheduling_due

        # (critical_slots, max_critical, critical_start_sub_name, max_critical_interval 계산 로직은 기존과 동일하다고 가정)
        # 이 부분은 _should_expand_with_monitoring 또는 이 함수의 시작 부분에서 이미 계산되어 있어야 함.
        # 예시로 필요한 변수들만 명시 (실제 코드는 이 변수들을 가져오는 부분이 있어야 함)
        constraints_start_names = self.constraint_handler.get_time_slots(
            (candidate_due_info.due_related_sub_name),  # due_related_sub_name 사용
            curr_state.constraints,
            "in",  #  due_related_sub_name으로 들어오는 제약
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]

        if not critical_slots:
            # 현재 candidate subtask가 critical constraints 영향 하에 있지 않는 경우, fallback to expand subtask without monitoring
            log.debug(
                f"No critical constraints found for {candidate_due_info.due_related_sub_name}. Fallback to non-monitoring for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        max_critical = max(
            critical_slots, key=lambda x: x.interval
        )  # 이 interval이 Bayesian criteria의 기반이 될 수 있음
        critical_start_sub_name = (
            max_critical.related_subtask_name
        )  # 이 critical 제약을 시작시킨 태스크
        max_critical_interval = (
            max_critical.interval
        )  # critical_start_sub_name 완료부터 due_related_sub_name의 Interaction 시작까지의 시간

        critical_constraint_start_time = 0.0
        critical_constraint_start_sub_objs = None  # 모니터링 대상 객체 찾기 위함
        found_crit_start_entry = False
        for ce in curr_state.completed_entries:
            if ce.subtask.name == critical_start_sub_name:
                critical_constraint_start_time = ce.schedule_end_time  # 완료된 시간
                critical_constraint_start_sub_objs = ce.subtask.execution.objects
                found_crit_start_entry = True
                break

        if not found_crit_start_entry:
            log.warning(
                f"Critical start subtask '{critical_start_sub_name}' for {original_task_name}'s monitoring not found in completed_entries. Fallback."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # cutoff은 max_critical_interval (선행 critical 완료 후부터 다음 critical 시작까지의 총 시간)에 Bayesian criteria를 적용
        cutoff = max_critical_interval * BAYESIAN_CRITERIA

        expected_monitoring_start_timing = critical_constraint_start_time + cutoff

        duration_for_early_sub_until_monitoring = (
            expected_monitoring_start_timing - curr_state.current_time
        )

        actual_first_nav_duration_now_for_candidate = 0.0
        if (
            candidate.subtask.execution
            and candidate.subtask.execution.primitive_actions
        ):
            first_action_str = candidate.subtask.execution.primitive_actions[0]
            if first_action_str.upper().startswith("NAVIGATE_TO"):
                nav_info_now = self.action_handler.get_actions_info(
                    curr_node, [first_action_str]
                )
                if nav_info_now and nav_info_now.success:
                    actual_first_nav_duration_now_for_candidate = (
                        nav_info_now.action_duration
                    )
                else:
                    actual_first_nav_duration_now_for_candidate = float(
                        "inf"
                    )  # 실패 시
            # else: first_action이 NAVIGATE_TO가 아니면 네비 시간 0

        if (
            duration_for_early_sub_until_monitoring
            < actual_first_nav_duration_now_for_candidate + EPSILON
        ):
            log.warning(
                f"Fallback: Not enough time for early_sub (needs {actual_first_nav_duration_now_for_candidate:.2f}, has {duration_for_early_sub_until_monitoring:.2f}) "
                f"before monitoring for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        original_subtask_actions = candidate.subtask.execution.primitive_actions
        try:
            # full_candidate_action_info
            full_candidate_action_info: Optional[ActionResult] = (
                self.action_handler.get_actions_info(
                    curr_node, original_subtask_actions
                )
            )
            if (
                full_candidate_action_info is None
                or not full_candidate_action_info.success
            ):  # .success 접근
                log.warning(
                    f"Fallback: Full action sim failed for {original_task_name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

            total_original_subtask_duration = (
                full_candidate_action_info.cumulative_time
            )  # .cumulative_time 접근
            if (
                expected_monitoring_start_timing
                > curr_state.current_time + total_original_subtask_duration - EPSILON
            ):
                log.debug(
                    f"Fallback: Entire subtask {original_task_name} ends before monitoring cutoff at {expected_monitoring_start_timing:.2f}"
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

            # split_subtask_by_cutoff_time은 (ActionSimulationLog, ActionSimulationLog) 반환
            pre_actions_info, post_actions_info = (
                self.action_handler.split_subtask_by_cutoff_time(
                    curr_node,
                    original_subtask_actions,
                    duration_for_early_sub_until_monitoring,
                )
            )
            # pre_actions_info.results는 ActionSimulationLog의 속성이므로 유효
            if not (
                pre_actions_info and pre_actions_info.results and post_actions_info
            ):
                log.warning(
                    f"Fallback: split_subtask_by_cutoff_time failed for {original_task_name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)
            if not post_actions_info.get_actions():
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
        planned_early_sub_nav_start_time = curr_state.current_time
        # pre_actions_info는 ActionSimulationLog이므로, .cumulative_time 없음. .total_time_used() 사용
        duration_of_early_sub_from_sim = 0.0
        if pre_actions_info and pre_actions_info.results:  # 로그에 결과가 있는지 확인
            duration_of_early_sub_from_sim = pre_actions_info.total_time_used()
        else:
            log.warning(
                f"pre_actions_info for {original_task_name} is empty or has no results. Duration set to 0."
            )
            # 이 경우, early_sub가 의미가 없으므로 fallback 또는 실패 처리도 고려 가능

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

        monitoring_target_obj = (
            list(critical_constraint_start_sub_objs.keys())[-1]
            if critical_constraint_start_sub_objs
            else "UnknownTarget"
        )
        # mon_sub 이름 수정 제안: due_related_sub_name을 명시
        due_related_sub_name_for_mon = candidate_due_info.due_related_sub_name
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=due_related_sub_name_for_mon,
            obj=monitoring_target_obj,
        )
        mon_sub.decomposed = True
        planned_mon_sub_start_time = planned_early_sub_completion_time
        planned_mon_sub_completion_time = (
            planned_mon_sub_start_time + MONITORING_DURATION
        )

        remain_sub = copy.deepcopy(candidate.subtask)
        remain_sub.name = f"{original_task_name}_remain"

        # Monitoring Subtask 완료 시점의 가상 State 생성
        state_before_remain_nav_scene_pos = (
            pre_actions_info.results[-1].scene_positions
            if pre_actions_info.results
            else curr_state.scene_positions
        )
        state_before_remain_nav_held_obj = (
            pre_actions_info.results[-1].held_object
            if pre_actions_info.results
            else curr_state.held_object
        )

        state_before_remain_nav = SchedulerState(
            subtask=mon_sub,
            current_time=planned_mon_sub_completion_time,
            scene_positions=state_before_remain_nav_scene_pos,
            held_object=state_before_remain_nav_held_obj,
            completed_entries=curr_state.completed_entries
            + [
                CompletedEntry(
                    early_sub,
                    planned_early_sub_nav_start_time,
                    planned_early_sub_completion_time,
                )
            ],
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
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
        nav_action_for_remain_subtask = f"NAVIGATE_TO {nav_target_for_remain}"
        actual_nav_duration_for_remain = 0.0
        executed_nav_info_for_remain: Optional[ActionResult] = None  # 타입 명시

        # Remain Subtask 생성
        try:
            if post_actions_info.get_actions():
                # executed_nav_info_for_remain
                executed_nav_info_for_remain = self.action_handler.get_actions_info(
                    temp_sim_node_for_remain_nav, [nav_action_for_remain_subtask]
                )
                if (
                    executed_nav_info_for_remain is None
                    or not executed_nav_info_for_remain.success
                ):  # .success 접근
                    log.warning(
                        f"Navigation for remain_sub of {original_task_name} failed."
                    )
                    return None
                actual_nav_duration_for_remain = (
                    executed_nav_info_for_remain.action_duration
                )  # .action_duration 접근
            else:
                log.warning(
                    f"post_actions_info.get_actions() is empty for {original_task_name}, remain_sub will have no actions."
                )
        except ValueError as e:
            log.error(
                f"Path finding for remain_sub of {original_task_name} failed: {e}"
            )
            return None

        pure_interaction_post_actions = []
        original_post_actions_list = (
            post_actions_info.get_actions()
        )  # ActionSimulationLog.get_actions()는 str 리스트 반환
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
            ([nav_action_for_remain_subtask] + pure_interaction_post_actions)
            if actual_nav_duration_for_remain > EPSILON
            else pure_interaction_post_actions
        )
        remain_sub.execution.primitive_actions = final_post_actions

        duration_of_remain_sub_from_sim = 0.0
        if final_post_actions:
            state_after_remain_nav_scene_pos = (
                executed_nav_info_for_remain.scene_positions
                if executed_nav_info_for_remain
                else state_before_remain_nav.scene_positions
            )
            state_after_remain_nav_held_obj = (
                executed_nav_info_for_remain.held_object
                if executed_nav_info_for_remain
                else state_before_remain_nav.held_object
            )

            state_after_remain_nav = SchedulerState(
                current_time=state_before_remain_nav.current_time
                + actual_nav_duration_for_remain,
                scene_positions=state_after_remain_nav_scene_pos,
                held_object=state_after_remain_nav_held_obj,
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
                # get_actions_info는 ActionResult 또는 None 반환
                executed_post_interaction_info: Optional[ActionResult] = (
                    self.action_handler.get_actions_info(
                        temp_node_for_remain_interaction, pure_interaction_post_actions
                    )
                )
                if not (
                    executed_post_interaction_info
                    and executed_post_interaction_info.success
                ):  # .success 직접 사용
                    log.warning(
                        f"Interaction part of remain_sub of {original_task_name} failed."
                    )
                    return None
                duration_of_post_interaction_sim = (
                    executed_post_interaction_info.cumulative_time
                )  # 여러 액션일 수 있으므로 cumulative_time
            duration_of_remain_sub_from_sim = (
                actual_nav_duration_for_remain + duration_of_post_interaction_sim
            )

        remain_sub.duration.interval = duration_of_remain_sub_from_sim
        remain_sub.decomposed = True

        # ! ------------------- Constraints Update (New Logic) -------------------
        new_constraints = copy.deepcopy(curr_state.constraints)
        original_task_name_in_constraints = new_constraints.has_node(original_task_name)

        in_edges_data_for_original = []
        out_edges_data_for_original = []

        if original_task_name_in_constraints:
            log.debug(
                f"Updating constraints for {original_task_name} due to monitoring split."
            )
            in_edges_data_for_original = list(
                new_constraints.in_edges(original_task_name, data=True)
            )
            out_edges_data_for_original = list(
                new_constraints.out_edges(original_task_name, data=True)
            )
            # 1. 원본 태스크 노드 제거
            new_constraints.remove_node(original_task_name)
            log.debug(f"Removed node {original_task_name} from constraints.")
        else:
            log.warning(
                f"Node {original_task_name} not found in constraints. Proceeding to add new subtasks."
            )

        # 2. 새로운 노드들 추가 (early_sub, mon_sub, remain_sub 객체는 이미 생성됨)
        # 이 노드들은 unique한 이름을 가져야 함 (예: original_task_name + "_early")
        if not new_constraints.has_node(early_sub.name):
            new_constraints.add_node(early_sub.name)
            log.debug(f"Added node {early_sub.name} to constraints.")
        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)
            log.debug(f"Added node {mon_sub.name} to constraints.")
        if not new_constraints.has_node(remain_sub.name):
            new_constraints.add_node(remain_sub.name)
            log.debug(f"Added node {remain_sub.name} to constraints.")

        # 3. 원본 태스크로 들어오던 엣지들을 early_sub로 연결
        for pred_name, _, data in in_edges_data_for_original:
            # 분할된 태스크들로부터의 내부 연결은 아래에서 별도 처리하므로, 여기서는 외부 predecessor만 고려
            if pred_name in [early_sub.name, mon_sub.name, remain_sub.name]:
                log.debug(
                    f"Skipping rerouting for already internal predecessor {pred_name} to {early_sub.name}."
                )
                continue

            edge_info = copy.deepcopy(data["info"])  # 기존 제약 정보 유지
            if new_constraints.has_edge(pred_name, early_sub.name):
                new_constraints.edges[pred_name, early_sub.name]["info"].update(
                    edge_info
                )
                log.debug(
                    f"Updated edge from {pred_name} to {early_sub.name} with info: {edge_info}"
                )
            else:
                new_constraints.add_edge(pred_name, early_sub.name, info=edge_info)
                log.debug(
                    f"Rerouted incoming edge from {pred_name} to {early_sub.name} with info: {edge_info}"
                )

        # 4. 원본 태스크에서 나가던 엣지들을 remain_sub에서 시작하도록 연결
        for _, succ_name, data in out_edges_data_for_original:
            # 분할된 태스크들로의 내부 연결은 아래에서 별도 처리
            if succ_name in [early_sub.name, mon_sub.name, remain_sub.name]:
                log.debug(
                    f"Skipping rerouting for already internal successor {succ_name} from {remain_sub.name}."
                )
                continue

            edge_info = copy.deepcopy(data["info"])  # 기존 제약 정보 유지
            if new_constraints.has_edge(remain_sub.name, succ_name):
                new_constraints.edges[remain_sub.name, succ_name]["info"].update(
                    edge_info
                )
                log.debug(
                    f"Updated edge from {remain_sub.name} to {succ_name} with info: {edge_info}"
                )
            else:
                new_constraints.add_edge(remain_sub.name, succ_name, info=edge_info)
                log.debug(
                    f"Rerouted outgoing edge from {remain_sub.name} to {succ_name} with info: {edge_info}"
                )

        # 5. early_sub -> mon_sub -> remain_sub 순차 연결
        # 5.1. early_sub -> mon_sub
        info_early_to_mon = {"Interval": 0.0, "IsCritical": True}
        if new_constraints.has_edge(early_sub.name, mon_sub.name):
            new_constraints.edges[early_sub.name, mon_sub.name]["info"].update(
                info_early_to_mon
            )
        else:
            new_constraints.add_edge(
                early_sub.name, mon_sub.name, info=info_early_to_mon
            )
        log.debug(
            f"Added internal edge from {early_sub.name} to {mon_sub.name} with info: {info_early_to_mon}"
        )

        # 5.2. mon_sub -> remain_sub
        info_mon_to_remain = {"Interval": 0.0, "IsCritical": False}
        if new_constraints.has_edge(mon_sub.name, remain_sub.name):
            new_constraints.edges[mon_sub.name, remain_sub.name]["info"].update(
                info_mon_to_remain
            )
        else:
            new_constraints.add_edge(
                mon_sub.name, remain_sub.name, info=info_mon_to_remain
            )
        log.debug(
            f"Added internal edge from {mon_sub.name} to {remain_sub.name} with info: {info_mon_to_remain}"
        )

        # --- 제약 조건 업데이트 로직 끝 ---

        # SchedulerState 생성 부분
        new_completed_for_state = curr_state.completed_entries + [
            CompletedEntry(
                subtask=early_sub,
                schedule_start_time=planned_early_sub_nav_start_time,
                schedule_end_time=planned_early_sub_completion_time,
                execution_status=(
                    True
                    if pre_actions_info  # pre_actions_info가 None이 아니고, 그 내부 결과가 성공적일 때
                    and pre_actions_info.results  # ActionSimulationLog에는 results가 있음 (ActionLog 리스트)
                    and all(
                        r.success for r in pre_actions_info.results if r is not None
                    )  # 각 ActionLog의 성공 여부
                    else False
                ),
            )
        ]
        # remaining_subtasks 업데이트: original_task_name은 제거되었고, mon_sub와 remain_sub가 새로 관리됨
        new_remain_for_state = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]
        # mon_sub와 remain_sub를 remaining_subtasks에 추가해야 함.
        # 이때, candidate.subtask가 original_task_name을 가리키므로, 이를 직접 추가하는 대신 remain_sub를 추가.
        # mon_sub와 remain_sub가 현재 depth에서 바로 실행될 후보는 아니지만, 미래에 스케줄링될 수 있도록 remaining_subtasks에 포함되어야 함.

        # remaining_subtasks에 mon_sub와 remain_sub (업데이트된 정보로)를 추가합니다.
        # 주의: candidate.subtask는 original_task_name을 참조하므로, 이를 그대로 사용하면 안됩니다.
        # remain_sub 객체를 사용해야 합니다.
        temp_remaining_map = {r.name: r for r in new_remain_for_state}
        if mon_sub.name not in temp_remaining_map:
            new_remain_for_state.append(mon_sub)
        if remain_sub.name not in temp_remaining_map:
            new_remain_for_state.append(remain_sub)

        new_state = SchedulerState(
            subtask=early_sub,  # 방금 완료한 것은 early_sub
            completed_entries=new_completed_for_state,
            remaining_subtasks=new_remain_for_state,
            constraints=new_constraints,  # 수정된 제약조건 사용
            current_time=planned_early_sub_completion_time,
            scene_positions=state_before_remain_nav_scene_pos,  # pre_actions_info.results[-1] 에서 가져온 값
            held_object=state_before_remain_nav_held_obj,  # pre_actions_info.results[-1] 에서 가져온 값
        )
        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate
        )  # 비용은 원본 candidate 기준으로
        new_cost = curr_cost + step_cost
        log.info(
            f"Expanded {original_task_name} with monitoring: early_sub='{early_sub.name}', mon_sub='{mon_sub.name}', remain_sub='{remain_sub.name}'."
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
            f"[_expand_wait_with_monitoring] Attempting partial nav + monitoring for {original_task_name}."
        )

        # 1. 시간 계산
        target_interaction_abs_time = candidate.actual_interaction_start_time
        if (
            target_interaction_abs_time is None
        ):  # Not-yet candidate 중 logical_start_time이 None인 경우 등
            log.warning(
                f"Candidate {original_task_name} has no valid actual_interaction_start_time. Cannot expand with wait_monitoring."
            )
            return None

        available_total_idle_time = (
            target_interaction_abs_time - curr_state.current_time
        )
        if available_total_idle_time < 0:  # 이미 늦음
            # 이미 늦었지만, 모니터링이라도 수행해야 하는가? 아니면 이 경로를 포기해야 하는가?
            # 여기서는 일단 진행하되, pure_wait_duration_after_monitoring이 음수가 될 수 있음을 인지.
            log.warning(
                f"Available idle time for {original_task_name} is negative ({available_total_idle_time:.2f}). Target may be missed."
            )
            # available_total_idle_time = 0 # 또는 포기 return None

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
            # nav_target_obj가 None이거나 빈 문자열일 경우 action_handler.get_actions_info에서 오류 발생 방지
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
                    f"  Failed to get full_nav_duration from current pos for {nav_target_obj}. Assuming unreachable for nav."
                )
                # full_nav_duration_from_current_pos는 이미 float('inf')
        else:
            log.debug(
                f"  No NAVIGATE_TO action found for {original_task_name} or nav_target_obj is invalid. No navigation planned for prep_nav_sub."
            )
            full_nav_duration_from_current_pos = 0.0  # 네비게이션이 없으므로 0

        # 3. 부분 네비게이션 시간 결정
        time_for_nav_before_monitoring = available_total_idle_time - MONITORING_DURATION
        calculated_partial_nav_time = 0.0
        if (
            time_for_nav_before_monitoring > EPSILON
            and full_nav_duration_from_current_pos > EPSILON
        ):  # 네비게이션 할 시간과 목표가 있을 때
            calculated_partial_nav_time = max(
                0.0,
                min(
                    (time_for_nav_before_monitoring // NAV_STEP_DURATION)
                    * NAV_STEP_DURATION,
                    full_nav_duration_from_current_pos,
                ),
            )
        log.debug(
            f"  Available for nav: {time_for_nav_before_monitoring:.2f}, Full nav needed: {full_nav_duration_from_current_pos:.2f}, Calculated partial nav: {calculated_partial_nav_time:.2f}"
        )

        # 4. `prep_nav_sub` 생성 및 시뮬레이션
        prep_nav_actions = []
        if calculated_partial_nav_time > EPSILON and nav_target_obj:
            prep_nav_actions.append(
                f"NAVIGATE_TO {nav_target_obj} {calculated_partial_nav_time:.2f}"
            )

        actual_prep_nav_duration = 0.0
        scene_positions_after_prep_nav = curr_state.scene_positions  # 기본값: 현재 위치
        held_object_after_prep_nav = curr_state.held_object  # 기본값: 현재 물건
        prep_nav_sub_success = True  # prep_nav_actions가 없으면 성공으로 간주

        prep_nav_sub: Optional[Subtask] = (
            None  # prep_nav_sub가 실제로 생성되었는지 추적
        )

        if prep_nav_actions:  # 부분 네비게이션 액션이 있을 경우에만 Subtask 생성
            prep_nav_sub_name = f"NavigatePartialFor_{original_task_name}_Mon"
            log.debug(
                f"  Creating prep_nav_sub: {prep_nav_sub_name} with actions: {prep_nav_actions}"
            )
            # 임시 SimulationNode를 만들지 않고, curr_node를 직접 사용 (action_handler가 내부적으로 복사)
            executed_prep_nav_info = self.action_handler.get_actions_info(
                curr_node, prep_nav_actions
            )
            if executed_prep_nav_info and executed_prep_nav_info.success:
                actual_prep_nav_duration = (
                    executed_prep_nav_info.cumulative_time
                )  # 단일 액션이므로 action_duration과 같을 수 있음
                scene_positions_after_prep_nav = executed_prep_nav_info.scene_positions
                held_object_after_prep_nav = executed_prep_nav_info.held_object
                prep_nav_sub = Subtask(  # 성공 시에만 Subtask 객체 생성
                    task_name="SchedulerGenerated",
                    name=prep_nav_sub_name,
                    duration=Duration(
                        interval=actual_prep_nav_duration, type="Controllable"
                    ),
                    execution=Execution(
                        objects=None, primitive_actions=prep_nav_actions
                    ),
                    decomposed=True,  # 분할된 작업의 일부
                    subtask_type="Navigation",
                    repetition=1,
                )
            else:
                prep_nav_sub_success = False
                log.warning(
                    f"  prep_nav_sub simulation failed for {original_task_name}."
                )
                # 사용자 결정 2: 비용을 높여 이 경로 회피
                # new_cost를 매우 높게 설정하거나, None 반환. 여기서는 일단 진행하고 new_cost에서 처리.
        else:
            log.debug(
                f"  No partial navigation actions for {original_task_name}. actual_prep_nav_duration = 0."
            )
            # prep_nav_actions가 없으므로 prep_nav_sub는 생성되지 않음 (None 유지)

        # 5. `mon_sub` 생성 및 시뮬레이션
        # 모니터링 대상은 candidate의 네비게이션 타겟 또는 candidate 자체일 수 있음. 여기서는 nav_target_obj 사용.
        # nav_target_obj가 없으면 candidate.subtask.name을 모니터링 대상으로 할 수도 있음.
        monitoring_target_for_mon_sub = (
            nav_target_obj if nav_target_obj else original_task_name
        )

        mon_sub_name_prefix = (
            candidate.scheduling_due.due_related_sub_name
            if candidate.scheduling_due
            and candidate.scheduling_due.due_related_sub_name
            else original_task_name
        )

        mon_sub = TaskUtil.create_monitoring_subtask(
            name=f"MonitorFor_{mon_sub_name_prefix}",  # 이름 명확히
            obj=monitoring_target_for_mon_sub,
        )
        mon_sub.decomposed = True  # 분할된 작업의 일부

        # mon_sub 시뮬레이션을 위한 임시 상태 (prep_nav 완료 후)
        state_before_mon = SchedulerState(
            subtask=prep_nav_sub,  # 이전 완료 작업 (None일 수 있음)
            current_time=curr_state.current_time + actual_prep_nav_duration,
            scene_positions=scene_positions_after_prep_nav,
            held_object=held_object_after_prep_nav,
            completed_entries=curr_state.completed_entries
            + (
                [
                    CompletedEntry(
                        prep_nav_sub,
                        curr_state.current_time,
                        curr_state.current_time + actual_prep_nav_duration,
                        prep_nav_sub_success,
                    )
                ]
                if prep_nav_sub
                else []
            ),
            remaining_subtasks=curr_state.remaining_subtasks,  # 임시 상태이므로 중요하지 않음
            constraints=curr_state.constraints,  # 임시 상태이므로 중요하지 않음
        )
        # ActionHandler는 SimulationNode를 받으므로 임시 노드 생성
        node_before_mon = SimulationNode(
            parent_node=curr_node,
            state=state_before_mon,
            heuristic_cost=0,
            depth=curr_node.depth,
            tie_breaker=0,
        )

        executed_mon_info = self.action_handler.get_actions_info(
            node_before_mon, mon_sub.execution.primitive_actions
        )
        mon_sub_success = False
        actual_mon_duration = MONITORING_DURATION  # 기본값
        if executed_mon_info and executed_mon_info.success:
            actual_mon_duration = (
                executed_mon_info.action_duration
            )  # 보통 MONITORING_DURATION
            mon_sub_success = True
            # 모니터링 후 scene_positions, held_object 변경은 없다고 가정 (시간만 흐름)
        else:
            log.warning(f"  mon_sub simulation failed for {original_task_name}.")
            # 사용자 결정: mon_sub 실패 시 이 경로 회피 (new_cost에서 처리)

        # 6. CompletedEntry 생성 및 상태 업데이트 준비
        new_completed_entries = list(curr_state.completed_entries)  # 복사해서 사용

        prep_nav_start_time = curr_state.current_time
        prep_nav_end_time = prep_nav_start_time + actual_prep_nav_duration
        if (
            prep_nav_sub
        ):  # prep_nav_sub가 실제로 생성되었을 때만 completed_entries에 추가
            new_completed_entries.append(
                CompletedEntry(
                    subtask=prep_nav_sub,
                    schedule_start_time=prep_nav_start_time,
                    schedule_end_time=prep_nav_end_time,
                    execution_status=prep_nav_sub_success,
                )
            )

        mon_sub_start_time = prep_nav_end_time
        mon_sub_end_time = mon_sub_start_time + actual_mon_duration
        new_completed_entries.append(
            CompletedEntry(
                subtask=mon_sub,
                schedule_start_time=mon_sub_start_time,
                schedule_end_time=mon_sub_end_time,
                execution_status=mon_sub_success,
            )
        )

        # 7. 제약 조건 업데이트
        new_constraints = copy.deepcopy(curr_state.constraints)
        # original_task_name이 제약 그래프에 있는지 확인 (없으면 추가는 하지 않음, 연결만 시도)

        # 7.1. prep_nav_sub -> mon_sub (prep_nav_sub가 존재하고 성공했을 때)
        if prep_nav_sub and prep_nav_sub_success:
            if not new_constraints.has_node(prep_nav_sub.name):
                new_constraints.add_node(prep_nav_sub.name)
            if not new_constraints.has_node(mon_sub.name):
                new_constraints.add_node(mon_sub.name)
            new_constraints.add_edge(
                prep_nav_sub.name,
                mon_sub.name,
                info={"Interval": 0.0, "IsCritical": True},
            )

        # 7.2. mon_sub -> candidate.subtask (original_task_name)
        interval_to_candidate = target_interaction_abs_time - mon_sub_end_time
        if interval_to_candidate < -EPSILON:  # 이미 늦었음
            log.warning(
                f"  Target interaction time for {original_task_name} ({target_interaction_abs_time:.2f}) "
                f"is already passed after monitoring ({mon_sub_end_time:.2f}). Interval set to 0."
            )
        interval_to_candidate = max(0, interval_to_candidate)  # 사용자 결정 3

        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)
        # candidate.subtask.name은 original_task_name. 그래프에 없을 수도 있음.
        if not new_constraints.has_node(original_task_name):
            log.warning(
                f"Original task {original_task_name} not in constraints. Adding node for linking from {mon_sub.name}."
            )
            new_constraints.add_node(original_task_name)

        new_constraints.add_edge(
            mon_sub.name,
            original_task_name,
            info={
                "Interval": interval_to_candidate,
                "IsCritical": candidate.is_critical,
            },
        )

        # 7.3. 기존 Critical 제약 재연결 (candidate.subtask로 향하던 제약들)
        #    이 부분은 기존 _expand_wait_with_monitoring의 제약 업데이트 로직을 참고하여,
        #    연결 대상을 mon_sub (또는 상황에 따라 prep_nav_sub)로 변경하고, Interval 재계산 필요.
        #    (이 부분은 복잡하여 기존 코드 로직의 상세한 이해와 수정이 필요합니다)
        #    간단화 버전: original_task_name으로 들어오던 critical edge를 mon_sub로 옮긴다고 가정.
        if new_constraints.has_node(original_task_name):  # 원래 노드가 있어야 이전 가능
            in_edges_data_original = list(
                new_constraints.in_edges(original_task_name, data=True)
            )
            for pred, _, data in in_edges_data_original:
                if pred == mon_sub.name or (prep_nav_sub and pred == prep_nav_sub.name):
                    continue  # 자기 자신 또는 내부 연결 방지

                edge_info = data.get("info", {})
                if edge_info.get("IsCritical"):
                    # 이 pred에서 mon_sub (또는 prep_nav_sub)까지의 새로운 Interval 계산 필요
                    # 여기서는 예시로 기존 Interval 유지, 실제로는 재계산 필요
                    log.debug(
                        f"  Rerouting critical constraint from {pred} to {mon_sub.name} (was to {original_task_name})"
                    )
                    if new_constraints.has_edge(pred, original_task_name):
                        new_constraints.remove_edge(pred, original_task_name)

                    # 연결 대상 결정: prep_nav_sub가 있었고 성공했다면 prep_nav_sub, 아니면 mon_sub
                    actual_reroute_target_for_pred = mon_sub.name
                    new_interval_from_pred = (
                        mon_sub_start_time  # 기본적으로 mon_sub 시작시간 기준
                    )
                    if prep_nav_sub and prep_nav_sub_success:
                        actual_reroute_target_for_pred = prep_nav_sub.name
                        new_interval_from_pred = prep_nav_start_time

                    # pred_entry 찾아서 정확한 interval 계산 (기존 _expand_wait_with_monitoring 참고)
                    pred_entry = next(
                        (
                            ce
                            for ce in reversed(new_completed_entries)
                            if ce.subtask.name == pred
                        ),
                        None,
                    )  # 가장 최근 완료된 pred
                    if (
                        not pred_entry
                    ):  # 만약 pred가 아직 new_completed_entries에 없다면 (curr_node.state.completed_entries 에서 찾아야 함)
                        pred_entry = next(
                            (
                                ce
                                for ce in reversed(curr_state.completed_entries)
                                if ce.subtask.name == pred
                            ),
                            None,
                        )

                    if pred_entry:
                        calculated_interval = (
                            new_interval_from_pred - pred_entry.schedule_end_time
                        )
                        # calculated_interval = max(0, calculated_interval) # 음수 방지
                    else:  # pred_entry 못찾으면 기존 interval 사용 (부정확할 수 있음)
                        calculated_interval = edge_info.get("Interval", 0)
                        log.warning(
                            f"Predecessor {pred} for critical constraint not found in completed entries. Using original interval {calculated_interval} for rerouting."
                        )

                    rerouted_edge_info = {
                        "Interval": max(0, calculated_interval),
                        "IsCritical": True,
                    }
                    if not new_constraints.has_edge(
                        pred, actual_reroute_target_for_pred
                    ):
                        new_constraints.add_edge(
                            pred,
                            actual_reroute_target_for_pred,
                            info=rerouted_edge_info,
                        )
                    else:  # 이미 엣지가 있다면 (다른 이유로), 정보 업데이트 (더 보수적인 값으로 등)
                        new_constraints.edges[pred, actual_reroute_target_for_pred][
                            "info"
                        ].update(rerouted_edge_info)

        # 8. 새로운 SchedulerState 생성
        # 최종 완료된 subtask는 mon_sub
        final_completed_subtask_for_state = mon_sub
        final_current_time_for_state = mon_sub_end_time
        final_scene_positions_for_state = (
            scene_positions_after_prep_nav  # mon_sub는 위치 변경 없다고 가정
        )
        final_held_object_for_state = (
            held_object_after_prep_nav  # mon_sub는 물건 변경 없다고 가정
        )

        new_remaining_subtasks = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]
        # mon_sub는 completed로 갔으므로, candidate.subtask (original_task_name)를 remaining에 추가해야 함.
        # prep_nav_sub도 completed.
        # 주의: candidate.subtask는 아직 처리 안된 것이므로 remaining에 있어야 함.
        # 만약 original_task_name을 사용하는 다른 Subtask 객체가 있다면 (예: decomposed된 다른 조각), 그것도 유지.
        # 여기서는 candidate.subtask 객체 자체를 추가.
        if not any(r.name == original_task_name for r in new_remaining_subtasks):
            new_remaining_subtasks.append(candidate.subtask)

        new_state = SchedulerState(
            subtask=final_completed_subtask_for_state,
            completed_entries=new_completed_entries,
            remaining_subtasks=new_remaining_subtasks,
            constraints=new_constraints,
            current_time=final_current_time_for_state,
            scene_positions=final_scene_positions_for_state,
            held_object=final_held_object_for_state,
        )

        step_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate
        )  # 비용은 원본 candidate 기준으로
        new_cost = curr_cost + step_cost
        log.info(
            f"Expanded wait for {original_task_name} with monitoring:\n"
            f"  PrepNav: {prep_nav_sub.name if prep_nav_sub else 'None'} (Dur: {actual_prep_nav_duration:.2f}, Success: {prep_nav_sub_success})\n"
            f"  Monitor: {mon_sub.name} (Dur: {actual_mon_duration:.2f}, Success: {mon_sub_success})\n"
            f"  Completion: {final_current_time_for_state:.2f}, Target Interaction: {target_interaction_abs_time:.2f}\n"
            f"  Cost: +{step_cost:.2f} -> Total: {new_cost:.2f}. Depth: {depth + 1}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
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
            prep_nav_sub_name = f"NavigatePartialFor_{original_task_name}_Wait"
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
                            prep_nav_sub,
                            curr_state.current_time,
                            current_time_after_prep_nav,
                            prep_nav_sub_success,
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
                    prep_nav_sub,
                    curr_state.current_time,
                    current_time_after_prep_nav,
                    prep_nav_sub_success,
                )
            )
        if pure_wait_sub:
            pure_wait_start_time = current_time_after_prep_nav
            pure_wait_end_time = pure_wait_start_time + actual_pure_wait_duration
            new_completed_entries.append(
                CompletedEntry(
                    pure_wait_sub,
                    pure_wait_start_time,
                    pure_wait_end_time,
                    pure_wait_sub_success,
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
