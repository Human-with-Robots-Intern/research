import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

from core.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager
from scheduler.action_handler import ActionHandler
from utils.common import create_module_logger
from utils.config import BAYESIAN_CRITERIA, EPSILON, MONITORING_DURATION, RED, RESET
from utils.task import TaskUtil

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
        self.constraint_handler = ConstraintHandler()
        self.cost_calculator = HeuristicManager(self.constraint_handler)

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
            # --- 수정: 데드라인 할당 로직 호출 추가 ---
            # feasible 후보들에게 다음 critical task를 기준으로 데드라인 할당
            # _assign_deadlines는 feasible_candidates 리스트를 직접 수정함
            self.constraint_handler._assign_deadlines(
                feasible_candidates, not_yet_candidates, curr_node
            )
            # --- 수정 끝 ---
            log.debug(
                f"[_simulate_search] Expanding {len(feasible_candidates)} feasible candidates "
                f"and {len(not_yet_candidates)} not-yet-feasible candidates.\n"
            )
            if not feasible_candidates and not not_yet_candidates:
                # No expansions possible => infeasible branch
                log.warning("[_simulate_search] No expansions => branch ends.")
                continue

            log.debug(
                f"========================================\n"
                f"Depth = {curr_depth} (expanding to {curr_depth + 1})\n"
                f"Current Time : {round(curr_state.current_time,2)}\n\n"
                f"Completed_subs={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[c.subtask.name for c in feasible_candidates]},\n\n"
                f"Not_yet_feasible_subs={[c.subtask.name for c in not_yet_candidates]}\n\n"
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
        """
        Expand the current node for both feasible and not-yet-feasible subtasks.

        - Feasible candidates are sorted by earliest_start_time (ascending),
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
        # * earliest_start_time 오름차순으로 정렬하여 가장 빨리 시작 가능한 후보부터 고려
        sorted_feasible = sorted(
            feasible_candidates, key=lambda c: c.earliest_start_time
        )
        for candidate in sorted_feasible:
            log.debug(
                f"[_expand_candidates] Attempting to expand feasible subtask: {candidate.subtask.name}.\n"
            )
            child_node = self._expand_single_subtask(curr_node, candidate)
            if child_node is not None:
                expansions.append(child_node)
                is_expanded = True

        # * (B) If we have not expanded any feasible subtask,
        # *     then we do a single Wait expansion (pick earliest not-yet-feasible)
        if not is_expanded and not_yet_candidates:
            sorted_not_feasible = sorted(
                not_yet_candidates, key=lambda c: c.earliest_start_time
            )
            wait_candidate = sorted_not_feasible[0]
            log.debug(
                f"[_expand_candidates] No feasible expansions done. Waiting for subtask: {wait_candidate.subtask.name}.\n"
            )
            wait_node = self._expand_single_wait(curr_node, wait_candidate)
            if wait_node:  # wait_node가 None이 아닐 경우에만 추가
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

        # * (2) subtask 종료 시각이 deadline보다 느리면 infeasible (부동소수점 오차 고려)
        if candidate.deadline.due_date < end_time - EPSILON:
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

        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
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
        # ! ------------------- Check conditions for splitting -------------------
        # * 1) Identify the relevant "critical" slot for the subtask's deadline
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        # Critical constraint를 끝내는 Subtask를 향하는 모든 critical constraints를 찾는다
        constraints_start_names = self.constraint_handler.get_time_slots(
            deadline_sub_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]

        # _should_expand_with_monitoring 에서 이미 critical constraint end가 아님을 확인했을 것이므로,
        # 여기서 critical_slots가 비어있는 경우는 드물 것으로 예상됨.
        # 하지만 방어적으로 코딩. 비어있다면 모니터링 불필요.
        if not critical_slots:
            # 이전 검사(should_expand)와 불일치 발생 가능성. 경고 대신 에러 로깅.
            log.error(
                f"[_expand_subtask_with_monitoring] Inconsistency: No critical constraints found for {deadline_sub_name} "
                f"despite being flagged for monitoring. Check _should_expand_with_monitoring and get_time_slots logic. "
                f"Falling back to normal subtask expansion for {candidate.subtask.name}."
            )
            # fallback 대신 None을 반환하여 이 경로가 유효하지 않음을 명확히 할 수도 있으나,
            # 우선은 기존 로직대로 fallback 유지. 필요시 변경 가능.
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name, max_critical_interval = (
            max_critical.related_subtask_name,
            max_critical.interval,
        )

        # * 2) Calculate the early cutoff based on Bayesian criteria
        # Bayesian Criteria는 critical interval 시작 시점부터 모니터링 시작 시점까지의 *간격* 비율을 의미한다고 가정
        monitoring_start_offset = max_critical_interval * BAYESIAN_CRITERIA

        # * 3) Find monitoring obj and the time at which the critical constraint starts
        critical_constraint_start_time = 0.0
        critical_constraint_start_sub_objs = None
        found_start_time = False
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_constraint_start_time = ce.end_time
                critical_constraint_start_sub_objs = ce.subtask.execution.objects
                found_start_time = True
                break

        if not found_start_time:
            # Critical 시작 subtask가 완료 목록에 없는 경우 (e.g., 가장 첫 subtask인 경우)
            # 이 경우 모니터링 분할 로직을 안전하게 진행하기 어려움. 에러 로그 남기고 fallback.
            log.error(
                f"[_expand_subtask_with_monitoring] Critical start subtask '{critical_start_sub_name}' "
                f"not found in completed tasks. Cannot reliably determine monitoring start time. "
                f"Falling back to non-monitoring expansion for {candidate.subtask.name}."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # 예상 모니터링 시작 시각 (절대 시간)
        expected_monitoring_start_timing = (
            critical_constraint_start_time + monitoring_start_offset
        )

        # * 4) Check if the entire subtask ends before the monitoring cutoff
        last_action_info = self.action_handler.get_actions_info(
            curr_node, candidate.subtask.execution.primitive_actions
        )
        exec_time = last_action_info.time_used
        subtask_end_time = curr_state.current_time + exec_time

        # 부동소수점 오차 고려: 모니터링 시작 시간이 subtask 종료 시간보다 명확히 빠를 때만 분할
        if expected_monitoring_start_timing > subtask_end_time - EPSILON:
            log.debug(
                f"[_expand_subtask_with_monitoring] Entire subtask (ends at {round(subtask_end_time, 2)}) "
                f"finishes before or very close to expected monitoring start time ({round(expected_monitoring_start_timing, 2)}) "
                f"=> No split needed."
            )
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # ! ------------------- Proceed with actual splitting -------------------
        # * (1) split_subtask_for_monitoring
        # 모니터링 시작 시점까지 남은 시간 (현재 시간 기준)
        # split_time은 split_subtask_by_cutoff_time에 전달되어, 현재 시점부터 얼마 후 분할할지를 결정
        time_until_monitoring_start = (
            expected_monitoring_start_timing - curr_state.current_time
        )

        # 남은 시간이 음수거나 매우 작으면 (이미 지났거나 거의 동시), 즉시 분할 (split_time=EPSILON)
        # (위의 4번 체크에서 이미 걸러졌어야 하지만, 방어적으로 처리)
        split_time = max(EPSILON, time_until_monitoring_start)

        log.debug(
            f"[_expand_subtask_with_monitoring] Calculated split_time (duration from now): {round(split_time, 2)}"
        )

        # --- 수정: ActionHandler의 분할 결과가 ActionResult의 튜플이라고 가정 ---
        pre_actions_info: Optional[ActionResult] = None
        post_actions_info: Optional[ActionResult] = None
        # --- 수정 끝 ---
        try:
            # --- 수정: split_subtask_by_cutoff_time 반환 타입 변경 반영 및 예외 처리 추가 ---
            split_result = self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                split_time,
            )
            if split_result is None:
                log.error(
                    f"[_expand_subtask_with_monitoring] ActionHandler failed to split actions for {candidate.subtask.name}. Aborting split."
                )
                return None  # 분할 실패 시 None 반환

            pre_actions_info, post_actions_info = split_result
            # --- 수정 끝 ---

            # 분할 결과 유효성 검사 (ActionHandler가 None 대신 빈 ActionResult를 반환할 수도 있음)
            if not pre_actions_info or not pre_actions_info.actions:
                log.warning(
                    f"[_expand_subtask_with_monitoring] Splitting resulted in empty pre_actions. "
                    f"This might happen if split_time is too small. "
                    f"Falling back to non-monitoring expansion for {candidate.subtask.name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

            # post_actions_info가 없거나 비어있는 경우 (모든 액션이 split_time 전에 끝남)
            if not post_actions_info or not post_actions_info.actions:
                log.warning(
                    f"[_expand_subtask_with_monitoring] Splitting resulted in empty post_actions. "
                    f"Entire subtask seems to end before monitoring cutoff despite earlier checks. "
                    f"Falling back to non-monitoring expansion for {candidate.subtask.name}."
                )
                return self._expand_subtask_wo_monitoring(curr_node, candidate)

        except (ValueError, NotImplementedError) as e_split:
            log.error(
                f"[_expand_subtask_with_monitoring] Error during action splitting for {candidate.subtask.name}: {e_split}. Aborting split.",
                exc_info=True,
            )
            return None  # 분할 중 오류 발생 시 None 반환
        except Exception as e_generic_split:
            log.error(
                f"[_expand_subtask_with_monitoring] Unexpected error during action splitting for {candidate.subtask.name}: {e_generic_split}. Aborting split.",
                exc_info=True,
            )
            return None

        early_sub = copy.deepcopy(candidate.subtask)
        early_sub.name += "_early"
        # --- 수정: ActionHandler 반환값 사용 ---
        early_sub.execution.primitive_actions = pre_actions_info.actions
        early_sub.duration.interval = (
            pre_actions_info.time_used
        )  # 분할된 액션의 실제 소요 시간 사용
        # --- 수정 끝 ---
        early_sub.decomposed = True

        remain_sub = copy.deepcopy(candidate.subtask)
        remain_sub.name += "_remain"
        # --- 수정: ActionHandler 반환값 사용 ---
        remain_sub.execution.primitive_actions = post_actions_info.actions
        # remain_sub의 duration은 post_actions의 실제 실행 시간
        remain_sub.duration.interval = (
            post_actions_info.action_duration
        )  # post_actions_info.time_used는 누적 시간일 수 있으므로, 개별 액션 시간 합계 또는 ActionHandler가 제공하는 순수 실행 시간 사용 필요
        # --- 수정 끝 ---
        remain_sub.decomposed = True

        # --- 수정: critical_start_sub_objs가 None인 경우 처리 ---
        # 모니터링 대상 객체 이름 확인 필요 (이전에 확인했지만 방어적으로 한번 더)
        if not critical_constraint_start_sub_objs:
            log.error(
                f"[_expand_subtask_with_monitoring] Cannot determine monitoring target object for {critical_start_sub_name} (previously checked). Aborting split."
            )
            return None  # 오류 명시
        # --- 수정 끝 ---

        monitoring_target_obj = list(critical_constraint_start_sub_objs.keys())[-1]

        # --- 수정: mon_sub 생성 시 이름 명확화 (원래 deadline subtask 이름 사용) ---
        mon_sub = TaskUtil.create_monitoring_subtask(
            # name=deadline_sub_name, obj=monitoring_target_obj # 이전 로직
            name=f"Monitor_{candidate.subtask.name}",  # 모니터링 대상 태스크 이름 포함
            obj=monitoring_target_obj,
        )
        # --- 수정 끝 ---

        log.debug(
            f"[_expand_subtask_with_monitoring] Created early_sub={early_sub.name} (dur: {early_sub.duration.interval:.2f}), "
            f"mon_sub={mon_sub.name} (dur: {MONITORING_DURATION}), remain_sub={remain_sub.name} (dur: {remain_sub.duration.interval:.2f})"
        )

        # * (B) Check feasibility against deadline for the early part
        start_time = curr_state.current_time
        # --- 수정: early_sub의 duration 사용 ---
        end_time = (
            start_time + early_sub.duration.interval
        )  # early_sub의 실제 실행 시간
        # --- 수정 끝 ---

        # early_sub 완료 시점 기준으로 deadline 체크 (부동소수점 오차 고려)
        if deadline_due < end_time - EPSILON:
            log.debug(
                f"[_expand_subtask_with_monitoring] Deadline {deadline_due} < "
                f"early_sub finish time {end_time}"
                f"=> Infeasible.\n"
            )
            return None

        # * (C) Update the state with the new subtasks
        old_name = candidate.subtask.name
        completed_entry = CompletedEntry(early_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]
        # early_sub 실행 후 상태 업데이트
        # --- 수정: ActionHandler 반환값 사용 ---
        new_held_obj = pre_actions_info.held_object
        new_scene_positions = pre_actions_info.scene_positions
        # --- 수정 끝 ---
        new_remain = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        # mon_sub과 remain_sub은 아직 실행되지 않았으므로 remaining에 추가
        new_remain.extend([mon_sub, remain_sub])

        # ! ------------------- Constraints Update -------------------
        new_constraints = copy.deepcopy(curr_state.constraints)
        # 모니터링 노드 추가 (아직 실행 전이지만 제약 조건 연결 위해 필요)
        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)

        # 네비게이션 Subtask 노드 추가 (완료되었으므로 필요)
        if not new_constraints.has_node(early_sub.name):
            new_constraints.add_node(early_sub.name)

        # 네비게이션 완료 후 모니터링 시작 (critical)
        # navigate_sub -> mon_sub 연결
        new_constraints.add_edge(
            early_sub.name,  # 네비게이션 완료 후
            mon_sub.name,
            info={"Interval": 0, "IsCritical": True},  # 즉시 모니터링 시작
        )

        # 모니터링 완료 후 원래 기다리던 subtask 시작 (critical)
        # Interval = 총 대기 시간 - 네비게이션 시간 - 모니터링 시간
        time_after_nav_and_mon = time_until_monitoring_start - MONITORING_DURATION
        # 남은 시간이 음수면 안됨 -> 경로 폐기 (infeasible) - 이전 단계에서 처리됨
        if time_after_nav_and_mon < -EPSILON:
            log.error(
                f"[_expand_subtask_with_monitoring] Negative interval after nav/mon ({round(time_after_nav_and_mon,2)}). Should have been caught earlier. Infeasible."
            )
            return None

        # 기다리던 후보 태스크 노드가 그래프에 있는지 확인
        if not new_constraints.has_node(candidate.subtask.name):
            log.error(
                f"Target candidate node '{candidate.subtask.name}' not found in constraint graph during wait expansion. Cannot add edge."
            )
            return None  # 제약 조건 오류

        # mon_sub -> candidate.subtask.name 제약 추가
        new_constraints.add_edge(
            mon_sub.name,
            candidate.subtask.name,
            info={
                "Interval": time_after_nav_and_mon,  # 계산된 남은 시간 사용
                "IsCritical": True,
            },
        )
        log.debug(
            f"[_expand_subtask_with_monitoring] Added constraint: {mon_sub.name} -> {candidate.subtask.name} with interval {round(time_after_nav_and_mon, 2)}"
        )

        # 최종 상태 생성 (네비게이션 완료 시점)
        new_state = SchedulerState(
            subtask=early_sub,  # 현재 실행 완료된 것은 early_sub
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=end_time,  # early_sub 완료 시점
            scene_positions=new_scene_positions,  # early_sub 완료 후 위치
            held_object=new_held_obj,  # early_sub 완료 후 손 상태
        )

        # 휴리스틱 비용 계산은 원래 candidate 기준으로 수행 (분할 전 subtask의 중요도 반영)
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
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
    ) -> Optional[SimulationNode]:  # 반환 타입을 Optional로 변경
        """
        Inserts a "Wait" involving partial navigation and monitoring preparation.

        - Calculates how much navigation can be done during the wait time.
        - Creates a "Navigate" subtask for this partial movement.
        - Creates a "Monitoring" subtask to be executed after navigation.
        - Updates constraints to link the sequence and critical timing.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for and need to monitor.

        Returns:
            Optional[SimulationNode]: The child node representing the state after partial navigation,
                                     or None if calculation fails or path is infeasible.
        """
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        # 총 대기 시간 (현재 시간부터 후보 subtask의 earliest_start_time까지)
        total_wait_duration = candidate.earliest_start_time - curr_state.current_time
        if (
            total_wait_duration < -EPSILON
        ):  # 음수 대기 시간 허용 불가 (부동소수점 오차 고려)
            log.error(
                f"[_expand_wait_with_monitoring] Negative wait duration calculated: {round(total_wait_duration, 3)}. "
                f"Candidate start: {round(candidate.earliest_start_time, 3)}, Current time: {round(curr_state.current_time, 3)}. "
                f"This path is infeasible."
            )
            return None  # 오류 발생 시 None 반환

        # total_wait_duration이 MONITORING_DURATION보다 작으면 네비게이션 없이 모니터링만 할 시간도 없음
        if total_wait_duration < MONITORING_DURATION - EPSILON:
            log.debug(
                f"[_expand_wait_with_monitoring] Total wait duration ({round(total_wait_duration, 2)}) is less than "
                f"monitoring duration ({MONITORING_DURATION}). Cannot perform monitoring wait. Skipping."
            )
            return None  # 모니터링 대기 불가능

        target_obj = candidate.subtask.execution.primitive_actions[0].split()[1]
        # 목표 지점까지의 전체 네비게이션 시간 계산
        full_nav_time_info = self.action_handler.get_actions_info(
            curr_node, [f"NAVIGATE_TO {target_obj}"]
        )
        full_nav_time = full_nav_time_info.action_duration

        # --- Partial Navigation Time Calculation ---
        # 모니터링 시간 제외하고 네비게이션에 쓸 수 있는 최대 시간
        available_time_for_nav = max(0, total_wait_duration - MONITORING_DURATION)

        # ActionHandler가 NAV_STEP_DURATION 단위로만 이동한다고 가정하는 로직 (기존)
        # discrete_nav_steps = int(available_time_for_nav // NAV_STEP_DURATION)
        # calculated_partial_nav_time = discrete_nav_steps * NAV_STEP_DURATION

        # ActionHandler가 임의 시간 이동 가능하다고 가정하는 로직 (개선)
        # 네비게이션에 가용한 시간만큼 이동 시도
        calculated_partial_nav_time = available_time_for_nav

        # 실제 네비게이션 시간은 계산된 시간과 전체 네비게이션 시간 중 작은 값이어야 함
        partial_nav_time = min(calculated_partial_nav_time, full_nav_time)

        # 네비게이션 시간이 너무 짧으면 (EPSILON 이하) 의미있는 이동이 어려울 수 있음
        # 이전: fallback / 현재: 에러 로깅 후 None 반환 (모니터링 준비 네비게이션 실패 간주)
        if partial_nav_time <= EPSILON:
            log.error(
                f"[_expand_wait_with_monitoring] Partial navigation time ({round(partial_nav_time, 3)}) is negligible. "
                f"Cannot prepare for monitoring wait for {candidate.subtask.name} via navigation. Skipping expansion."
            )
            # 이전 로직: 비-모니터링 Wait으로 fallback (의미상 불일치 가능성)
            # return self._expand_wait_wo_monitoring(curr_node, candidate)
            return None  # 네비게이션 기반 모니터링 준비 실패

        log.debug(
            f"[_expand_wait_with_monitoring] Wait for {candidate.subtask.name}. Total wait: {round(total_wait_duration,2)}. "
            f"Full nav time: {round(full_nav_time,2)}. Available for nav: {round(available_time_for_nav, 2)}. "
            # f"Discrete steps: {discrete_nav_steps}. Calculated partial nav (discrete): {round(discrete_nav_steps * NAV_STEP_DURATION, 2)}. " # 이전 로직 로그
            f"Calculated partial nav (available): {round(calculated_partial_nav_time, 2)}. "
            f"Final partial nav (min): {round(partial_nav_time, 2)}."
        )

        # 네비게이션 액션 정의 (ActionHandler가 이 형식과 시간을 처리할 수 있어야 함)
        nav_action = [f"NAVIGATE_TO {target_obj} {partial_nav_time}"]

        # partial_nav_time 만큼 네비게이션 실행 정보 얻기
        nav_action_info = self.action_handler.get_actions_info(curr_node, nav_action)
        actual_nav_time_used = nav_action_info.time_used  # 실제 소요 시간

        # 실제 소요 시간이 할당된 시간(partial_nav_time)과 크게 다르면 경고 (ActionHandler 동작 확인 필요)
        if abs(actual_nav_time_used - partial_nav_time) > EPSILON:
            log.warning(
                f"[_expand_wait_with_monitoring] Actual nav time used ({round(actual_nav_time_used,3)}) differs significantly from "
                f"requested partial nav time ({round(partial_nav_time, 3)}). Check ActionHandler."
            )
            # 경우에 따라서는 이 경로를 infeasible 처리할 수도 있음 (e.g., 시간이 더 걸린 경우)
            # 여기서는 경고만 로깅하고 진행

        new_scene_positions = nav_action_info.scene_positions
        new_held_obj = nav_action_info.held_object

        # 네비게이션 Subtask 생성
        navigate_sub = Subtask(
            task_name=None,  # Wait의 일부이므로 task_name 없음
            name=f"Navigate towards {target_obj} for {round(actual_nav_time_used, 2)}s (Wait Monitor Prep)",
            duration=Duration(interval=actual_nav_time_used, type="Controllable"),
            repetition=1,
            type="Navigation",  # 명확한 타입 부여
            execution=Execution(
                objects=None, primitive_actions=nav_action
            ),  # 실제 실행된 액션
            temporal_constraints=None,
        )

        # 모니터링 Subtask 생성 (아직 실행 전, remaining에 추가됨)
        mon_sub = TaskUtil.create_monitoring_subtask(
            name=candidate.subtask.name,
            obj=target_obj,  # 모니터링 대상은 기다리는 subtask의 목표
        )

        # 상태 업데이트 (네비게이션 완료 시점 기준)
        new_remain = [r for r in curr_state.remaining_subtasks]
        new_remain.append(mon_sub)  # 모니터링 subtask 추가

        start_time = curr_state.current_time
        end_time = start_time + actual_nav_time_used  # 네비게이션 완료 시간

        completed_entry = CompletedEntry(navigate_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # ! ------------------- Constraints Update -------------------
        new_constraints = copy.deepcopy(curr_state.constraints)
        # 모니터링 노드 추가 (아직 실행 전이지만 제약 조건 연결 위해 필요)
        if not new_constraints.has_node(mon_sub.name):
            new_constraints.add_node(mon_sub.name)

        # 네비게이션 Subtask 노드 추가 (완료되었으므로 필요)
        if not new_constraints.has_node(navigate_sub.name):
            new_constraints.add_node(navigate_sub.name)

        # 네비게이션 완료 후 모니터링 시작 (critical)
        # navigate_sub -> mon_sub 연결
        new_constraints.add_edge(
            navigate_sub.name,  # 네비게이션 완료 후
            mon_sub.name,
            info={"Interval": 0, "IsCritical": True},  # 즉시 모니터링 시작
        )

        # 모니터링 완료 후 원래 기다리던 subtask 시작 (critical)
        # Interval = 총 대기 시간 - 네비게이션 시간 - 모니터링 시간
        time_after_nav_and_mon = (
            total_wait_duration - actual_nav_time_used - MONITORING_DURATION
        )
        # 남은 시간이 음수면 안됨 -> 경로 폐기 (infeasible) - 이전 단계에서 처리됨
        if time_after_nav_and_mon < -EPSILON:
            log.error(
                f"[_expand_wait_with_monitoring] Negative interval after nav/mon ({round(time_after_nav_and_mon,2)}). Should have been caught earlier. Infeasible."
            )
            return None

        # 기다리던 후보 태스크 노드가 그래프에 있는지 확인
        if not new_constraints.has_node(candidate.subtask.name):
            log.error(
                f"Target candidate node '{candidate.subtask.name}' not found in constraint graph during wait expansion. Cannot add edge."
            )
            return None  # 제약 조건 오류

        # mon_sub -> candidate.subtask.name 제약 추가
        new_constraints.add_edge(
            mon_sub.name,
            candidate.subtask.name,
            info={
                "Interval": time_after_nav_and_mon,  # 계산된 남은 시간 사용
                "IsCritical": True,
            },
        )
        log.debug(
            f"[_expand_wait_with_monitoring] Added constraint: {mon_sub.name} -> {candidate.subtask.name} with interval {round(time_after_nav_and_mon, 2)}"
        )

        # 최종 상태 생성 (네비게이션 완료 시점)
        new_state = SchedulerState(
            subtask=navigate_sub,  # 방금 완료된 subtask는 네비게이션
            completed_subtasks=new_completed,
            remaining_subtasks=new_remain,
            constraints=new_constraints,
            current_time=end_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # 휴리스틱 비용 계산 (원래 기다리려던 candidate 기준)
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_with_monitoring] Executed partial navigation: {navigate_sub.name}\n"
            f"  -> Prepares for monitoring {mon_sub.name} and waiting for {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost, 2)}, Nav Interval={round(start_time,2)}~{round(end_time,2)}\n"
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
    ) -> Optional[SimulationNode]:  # 반환 타입을 Optional로 변경
        """
        Inserts a simple "Wait" action until the candidate's earliest_start_time.

        - No navigation or monitoring involved.
        - Creates a "Wait" subtask.

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.

        Returns:
            Optional[SimulationNode]: The child node representing the new state after waiting,
                                     or None if wait duration is invalid.
        """
        curr_state = curr_node.state
        curr_cost = curr_node.heuristic_cost
        depth = curr_node.depth

        total_wait_duration = candidate.earliest_start_time - curr_state.current_time

        # 음수 또는 매우 작은 대기 시간은 의미 없음
        if total_wait_duration < EPSILON:
            log.debug(
                f"[_expand_wait_wo_monitoring] Wait duration ({round(total_wait_duration, 3)}) is negligible or negative. Skipping wait expansion."
            )
            return None

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name} ({round(total_wait_duration, 2)}s)",
            duration=Duration(interval=total_wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",  # 명확한 타입 부여
            execution=Execution(
                objects=None, primitive_actions=[f"WAIT {total_wait_duration}"]
            ),
            temporal_constraints=None,
        )

        start_time = curr_state.current_time
        end_time = curr_state.current_time + total_wait_duration

        completed_entry = CompletedEntry(wait_sub, start_time, end_time)
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # Wait 동안에는 scene_positions, held_object 변경 없음
        new_state = SchedulerState(
            subtask=wait_sub,  # 방금 완료된 subtask는 Wait
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,  # remaining은 변경 없음
            constraints=curr_state.constraints,  # 제약조건 변경 없음
            current_time=end_time,
            scene_positions=curr_state.scene_positions,
            held_object=curr_state.held_object,
        )

        # 휴리스틱 비용 계산 (원래 기다리려던 candidate 기준)
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate)
        new_cost = curr_cost + step_cost

        log.info(
            f"[_expand_wait_wo_monitoring] WAIT subtask for {candidate.subtask.name}\n"
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
        3) The subtask is NOT the end point of a critical constraint chain itself.
           (Monitoring applies to tasks LEADING TO a critical deadline, not the deadline task itself).

        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The subtask candidate to check.

        Returns:
            bool: True if we should expand the subtask with monitoring, False otherwise.
        """
        # (1) If there's no finite deadline => no monitoring needed
        if candidate.deadline.due_date == float("inf"):
            # log.debug(f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} has no finite deadline => No monitoring.")
            return False

        # (2) If subtask is already decomposed => no monitoring needed
        if candidate.subtask.decomposed:
            # log.debug(f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is already decomposed => No monitoring.")
            return False

        # (3) If the candidate subtask itself is the END of a critical constraint => no monitoring needed for *this* task
        #     Monitoring is needed for tasks *before* this critical end task.
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        if any(slot.is_critical for slot in in_slots):
            # log.debug(f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} is itself a critical-constraint end => No monitoring for this task.")
            return False

        # All conditions met for potential monitoring-based split
        log.debug(
            f"[_should_expand_with_monitoring] Subtask {candidate.subtask.name} may need monitoring split."
        )
        return True
