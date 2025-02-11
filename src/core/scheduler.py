import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
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
    def __init__(
        self,
        search_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):
        self.search = search_width
        self.simulation_depth = simulation_depth
        log.info(f"{RED}{search_width=}, {simulation_depth=}{RESET}")

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler()
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(self, parent_state: SchedulerState) -> Optional[SchedulerState]:
        """
        parent_state로부터 1스텝(깊이1) 앞서간 자식 state를 구한다.
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

        return new_state

    def _simulate_search(self, init_state: SchedulerState) -> Optional[SimulationNode]:
        """
        Beam Search 기반의 n-step lookahead 시뮬레이션.
        - init_state를 루트로 하여, 최대 simulation_depth까지 탐색.
        - 각 단계에서 feasible/not_yet_feasible 서브태스크 확장을 수행.
        - best_solutions 중 비용이 가장 작은 노드를 반환.
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
            curr_state, curr_depth = curr_node.state, curr_node.depth

            # 1) 종료 조건 체크
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 2) 현재 시점에 실행 가능한 서브태스크, 아직 시작 안 된 서브태스크 구하기
            feasible_candidates, not_yet_candidates = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )

            if (len(feasible_candidates) == 0) and (len(not_yet_candidates) == 0):
                # 확장 불가 → infeasible branch
                continue

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth+1} / Current Time : {round(curr_state.current_time,2)}\n"
                f"Completed_subs ={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs ={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[candidate for candidate in feasible_candidates]},\n"
                f"Not_yet_feasible_subs={[candidate for candidate in not_yet_candidates]}\n"
                f"==================================================\n"
            )

            expanded_nodes: List[SimulationNode] = []
            is_expanded = False

            # --- (2-1) 즉시 실행 가능한 각 서브태스크 확장 ---
            # earliest_start_time이 큰 것부터 시도(reverse=True)
            for candidate in sorted(
                feasible_candidates, key=lambda x: x.earliest_start_time, reverse=True
            ):

                # (A) critical이고, 지금 당장(earliest_start == current_time)에 실행해야 하는 경우
                if (
                    candidate.is_critical
                    and abs(candidate.earliest_start_time - curr_state.current_time)
                    < EPSILON
                ):
                    # 추가할 subtask가 critical 제약 내에 존재하는 경우 (데드라인)
                    # 직전 서브테스크가 분할되지 않았을 때 Monitoring timing 결정
                    if (candidate.deadline.due_date != float("inf")) and (
                        not curr_node.state.subtask.decomposed
                    ):
                        new_node = self._expand_subtask_with_monitoring(
                            curr_node, candidate
                        )
                    else:
                        new_node = self._expand_subtask_wo_monitoring(
                            curr_node, candidate
                        )

                    if new_node is not None:
                        expanded_nodes.append(new_node)
                        is_expanded = True
                        break

                # (B) critical이 아니거나, critical이어도 현재시각이 다를 경우
                else:
                    if (candidate.deadline.due_date != float("inf")) and (
                        not curr_node.state.subtask.decomposed
                    ):
                        new_node = self._expand_subtask_with_monitoring(
                            curr_node, candidate
                        )
                    else:
                        new_node = self._expand_subtask_wo_monitoring(
                            curr_node, candidate
                        )

                    if new_node is not None:
                        expanded_nodes.append(new_node)
                        is_expanded = True

            # --- (2-2) 아직 시간 안 된 서브태스크들은 wait 추가 ---
            if not is_expanded:
                for candidate in not_yet_candidates:
                    new_node = self._expand_wait_subtask(curr_node, candidate)
                    expanded_nodes.append(new_node)
                    # 한 번에 하나의 wait만 생성 → break
                    break

            # --- (2-3) Local Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):
                if i < self.search:
                    queue.put(nd)
                else:
                    break

        # 3) best_solutions가 비었으면 No feasible
        if not best_solutions:
            log.error("[_simulate_search] best_solutions is empty -> No feasible\n")
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        best_node = best_solutions[0]
        log.debug(
            f"[_simulate_search] Found best_node with Subtask={best_node.state.subtask.name}, "
            f"Cost={best_node.heuristic_cost}\n"
        )
        return best_node

    def _extract_state(self, child_node: SimulationNode) -> Optional[SchedulerState]:
        """
        n-step lookahead로 탐색한 best_node(child_node)에서,
        '첫 번째 step(깊이1)' 노드의 state만 추출해 반환한다.
        """
        if child_node is None:
            log.error("[_extract_state] child_node is None\n")
            return None

        # 1) 루트까지 경로를 만든 뒤 reverse
        path = []
        curr = child_node
        while curr is not None:
            path.append(curr)
            curr = curr.parent_node
        path.reverse()  # path[0]이 루트, path[-1]이 child_node

        # 2) 깊이가 0(루트)만 있는 경우(즉 path 길이=1) → 실행할 step 없음
        if len(path) < 2:
            return path[0].state if path else None

        # 3) 첫 번째 step 노드는 path[1]
        first_step_node = path[1]
        return first_step_node.state

    # --------------------------------------------------------------------------
    #                       EXPANSION METHODS
    # --------------------------------------------------------------------------
    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        time-critical Subtask를 모니터링 분할로 처리:
        - early_sub (일정 구간) → monitoring_sub (0.1초) → remain_sub
        - 이동 시간(nav_time) 포함
        - deadline 검사 시, (early+mon+remain) 총합이 deadline 안에 들어야 함
        - Constraints 그래프 수정 시, old_name 제거 후
          in_edges->early_sub, out_edges->remain_sub 연결,
          early_sub->mon_sub->remain_sub 연결
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_time_slots = self.constraint_handler.get_time_slots(
            curr_state.subtask.name,
            curr_state.constraints,
            "out",
            is_critical=True,
        )
        # 부모 노드 (critical edge)의 가장 큰 시간 간격을 찾음
        curr_time_slot = max(curr_time_slots, key=lambda x: x.interval)

        # 가장 빨리 도래할 deadline 정보
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        nav_time, _ = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        # 1) 총 실행 시간 업데이트
        exec_time = candidate.subtask.duration.interval + nav_time

        # 2) Monitoring timing 계산
        monitoring_timing = curr_time_slot.interval * BAYESIAN_CRITERIA

        if monitoring_timing >= exec_time:
            self._expand_subtask_wo_monitoring(curr_node, candidate)

        early_sub, mon_sub, remain_sub = split_subtask_for_monitoring(
            curr_node=curr_node,
            candidate=candidate,
            early_cutoff=monitoring_timing,
            nav_manager=self.nav_manager,
        )

        # deadline 체크 시 이동시간도 포함하여 검사
        if deadline_due < (curr_state.current_time + early_sub.duration.interval):
            # deadline 넘어가면 확장 무의미
            return None

        # 3) Monitoring Subtasks 생성
        old_name = candidate.subtask.name

        # 4) Constraints 그래프 복사 후, 원본 노드 제거 → 분할 노드들 삽입
        new_constraints = copy.deepcopy(curr_state.constraints)
        if new_constraints.has_node(old_name):
            in_edges = list(new_constraints.in_edges(old_name, data=True))
            out_edges = list(new_constraints.out_edges(old_name, data=True))
            new_constraints.remove_node(old_name)
        else:
            in_edges = []
            out_edges = []

        # in_edges → early_sub 연결
        for pred, _, data in in_edges:
            info_copy = copy.deepcopy(data["info"])
            new_constraints.add_edge(pred, early_sub.name, info=info_copy)

        # out_edges → remain_sub 연결
        for _, succ, data in out_edges:
            info_copy = copy.deepcopy(data["info"])
            new_constraints.add_edge(remain_sub.name, succ, info=info_copy)

        # early_sub → mon_sub → remain_sub 연결
        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(remain_sub.name)
        new_constraints.add_node(mon_sub.name)

        new_constraints.add_edge(
            curr_state.subtask.name,
            mon_sub.name,
            info={"Interval": early_sub.duration.interval, "IsCritical": True},
        )
        new_constraints.add_edge(
            mon_sub.name,
            deadline_sub_name,
            info={
                "Interval": deadline_due - early_sub.duration.interval,
                "IsCritical": False,
            },
        )
        new_constraints.add_edge(
            curr_state.subtask.name,
            mon_sub.name,
            info={"Interval": monitoring_timing, "IsCritical": True},
        )
        new_constraints.add_edge(
            mon_sub.name,
            deadline_sub_name,
            info={
                "Interval": curr_time_slot.interval
                - monitoring_timing
                - MONITORING_DURATION,
                "IsCritical": True,
            },
        )
        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        # 5) 남은 Subtasks 갱신
        new_remaining = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        new_remaining.extend([mon_sub, remain_sub])

        # 7) 비용 계산
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, 0)
        new_cost = curr_heuristic + step_cost

        # 8) Completed Subtasks 업데이트
        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=curr_state.current_time,
            end_time=curr_state.current_time + early_sub.duration.interval,
        )

        new_completed = curr_state.completed_subtasks + [completed_entry]
        _, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, early_sub
        )
        # 9) 새 스케줄 상태 생성
        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=curr_state.current_time + early_sub.duration.interval,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_subtask_with_monitoring]\n"
            f"*{candidate.subtask.name}, Score = {round(new_cost,LOG_ROUND)}\n"
            f"Interval = {round(completed_entry.start_time,LOG_ROUND)} ~ {round(completed_entry.end_time,LOG_ROUND)} ({round(early_sub.duration.interval,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        # 10) 새 노드 반환
        new_node = SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
        return new_node

    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        일반(Non-monitoring) Subtask 실행:
        - 이동시간 + Subtask.duration만큼 소요
        - deadline 체크
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        # 이동 시간
        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )

        # 전체 실행시간
        exec_time = candidate.subtask.duration.interval + nav_time
        start_time = curr_state.current_time
        end_time = start_time + exec_time

        # deadline 체크
        if candidate.deadline.due_date < end_time:
            return None

        # Subtask 복사(실행시간 수정)
        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = exec_time

        # 비용 계산
        new_heuristic_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, nav_time
        )
        new_cost = curr_heuristic + new_heuristic_cost

        # 완료 목록 업데이트
        completed_entry = CompletedEntry(
            subtask=copied_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # remaining_subtasks에서 제거
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
            f"[_expand_subtask_wo_monitoring]\n"
            f"*{candidate.subtask.name}, Score = {round(new_cost,LOG_ROUND)}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(exec_time,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        new_node = SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> SimulationNode:
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해
        일정 시간을 기다리는 Wait Subtask를 추가.
        - Wait 시간 = candidate.earliest_start_time - current_time
        - 이동시간(nav_time)은 보통 0 혹은 무시(Wait 자체는 이동 X)
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        # 여기서는 nav_time을 거의 0으로 처리(Wait 위치 이동 없음 가정)
        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        wait_start_time = curr_state.current_time

        wait_duration = candidate.earliest_start_time - curr_state.current_time
        if wait_duration < 0:
            wait_duration = 0  # 혹시 음수면 0으로

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None,
                primitive_actions=[
                    f"NAVIGATE_TO {new_location}",
                    f"Wait {wait_duration-nav_time}",
                ],
            ),
            temporal_constraints=None,
        )

        new_completed = curr_state.completed_subtasks + [
            CompletedEntry(
                subtask=wait_sub,
                start_time=curr_state.current_time,
                end_time=curr_state.current_time + wait_duration,
            )
        ]
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=curr_state.current_time + wait_duration,
            agent_location=new_location,
        )

        # wait_sub 후보를 생성해 휴리스틱 계산
        wait_candidate = Candidate(
            subtask=wait_sub,
            earliest_start_time=curr_state.current_time + wait_duration,
            is_critical=False,
        )
        new_heuristic = self.cost_calculator.calc_heuristic(
            curr_node, wait_candidate, 0
        )
        new_cost = curr_heuristic + new_heuristic

        log.info(
            f"[_expand_wait_subtasks]\n"
            f"*{wait_sub.name}, Score = {round(new_cost,LOG_ROUND)} "
            f"(earliest_start={round(candidate.earliest_start_time,LOG_ROUND)}, "
            f"is_critical={candidate.is_critical})\n"
            f"Interval = {round(wait_start_time,LOG_ROUND)} ~ "
            f"{round(wait_start_time+wait_duration,LOG_ROUND)} ({round(wait_duration,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in curr_state.remaining_subtasks]}\n"
        )

        new_node = SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )
        return new_node
