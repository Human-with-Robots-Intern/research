import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
from scheduler.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from utils import BEAM_WIDTH, SIMULATION_DEPTH, create_module_logger
from utils.constants import BAYESIAN_CRITERIA, EPSILON, LOG_ROUND, RED, RESET
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

            # (1) 종료 조건
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # (2) 실행 가능/아직 시작 안 된 subtasks 구하기
            feasible_candidates, not_yet_candidates = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )
            if not feasible_candidates and not not_yet_candidates:
                # 확장 불가능 → infeasible branch
                continue

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth+1} / Current Time : {round(curr_state.current_time,2)}\n"
                f"Completed_subs ={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs ={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[c for c in feasible_candidates]},\n"
                f"Not_yet_feasible_subs={[c for c in not_yet_candidates]}\n"
                f"========================================\n"
            )

            expanded_nodes: List[SimulationNode] = []
            is_expanded = False

            # (2-1) Feasible candidates 확장
            #  - earliest_start_time이 큰 것부터(reverse=True)
            sorted_feasible = sorted(
                feasible_candidates, key=lambda x: x.earliest_start_time, reverse=True
            )

            for candidate in sorted_feasible:
                new_node = self._expand_single_subtask(curr_node, candidate)
                if new_node is not None:
                    expanded_nodes.append(new_node)
                    is_expanded = True
                    # (A) critical & 즉시 시작해야 하는 subtask는 1개만 선택하고 break
                    if (
                        candidate.is_critical
                        and abs(candidate.earliest_start_time - curr_state.current_time)
                        < EPSILON
                    ):
                        break

            # (2-2) 모두 확장 실패(즉시 실행할 게 없다면) → 아직 시간 안 된 subtasks 처리 = Wait
            if not is_expanded and not_yet_candidates:
                sorted_not_yet = sorted(
                    not_yet_candidates, key=lambda x: x.earliest_start_time
                )
                # 하나만 Wait
                wait_candidate = sorted_not_yet[0]
                wait_node = self._expand_wait_subtask(curr_node, wait_candidate)
                expanded_nodes.append(wait_node)

            # (2-3) Local Beam pruning: 비용 낮은 상위 K개만 삽입
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):
                if i < self.search:
                    queue.put(nd)
                else:
                    break

        # (3) best_solutions 중 최소 비용 노드
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
        '첫 번째 step(깊이1)' 노드의 state만 추출해 반환.
        """
        if child_node is None:
            log.error("[_extract_state] child_node is None")
            return None

        # 루트까지 경로를 만든 뒤 reverse
        path = []
        curr = child_node
        while curr is not None:
            path.append(curr)
            curr = curr.parent_node
        path.reverse()

        # 깊이가 0(루트)만 있는 경우(즉 path 길이=1)
        if len(path) < 2:
            return path[0].state if path else None

        # 첫번째 step 노드 = path[1]
        return path[1].state

    # --------------------------------------------------------------------------
    #               (중복로직 최소화) 서브태스크 확장을 담당하는 단일 함수
    # --------------------------------------------------------------------------
    def _expand_single_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        주어진 candidate(subtask)를 하나 확장해서,
        1) 모니터링 필요 여부 판단
        2) 모니터링 / 비모니터링 확장 중 하나를 수행
        3) 실패 시 None 반환
        """
        # 만약 deadline에 의해 이미 infeasible 하면 None
        if candidate.deadline.due_date < (curr_node.state.current_time):
            return None

        # 모니터링 필요한지 결정
        use_monitoring = self._should_expand_with_monitoring(curr_node, candidate)
        if use_monitoring:
            return self._expand_subtask_with_monitoring(curr_node, candidate)
        else:
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

    def _should_expand_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> bool:
        """
        모니터링 분할(early_sub - monitoring_sub - remain_sub)이 필요한지 여부를 간단히 판단한다.
        - 조건 예시:
          1) deadline이 무한대가 아님
          2) subtask가 아직 분해되지 않음(decomposed=False)
          3) 모니터링 cut-off 시점 전에 subtask가 모두 끝나지 않는지 확인
        """
        # (1) deadline 없는 경우 => 모니터링 필요 X
        if candidate.deadline.due_date == float("inf"):
            return False

        # (2) 이미 분해된 subtask => 모니터링 필요 X
        if candidate.subtask.decomposed:
            return False

        # (3) critical_start_time + early_cutoff > subtask 종료 시점인지 판단
        #     => subtask가 모니터링 시점 이전에 다 끝나버리면 굳이 모니터링 분할 필요 X
        curr_state = curr_node.state
        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        total_duration = nav_time + candidate.subtask.duration.interval
        subtask_end_time = curr_state.current_time + total_duration

        # constraint에서 critical 관련 정보를 가져와야 함
        # (원래 _expand_subtask_with_monitoring 안에서 하던 작업을 간소화)
        constraints_start_names = self.constraint_handler.get_time_slots(
            candidate.deadline.subtask_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            return False  # critical slot이 없으면 모니터링 무의미

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name = max_critical.related_subtask_name
        max_critical_interval = max_critical.interval

        # critical_start_time 구하기
        critical_start_time = 0.0
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_start_time = ce.end_time
                break

        early_cutoff = max_critical_interval * BAYESIAN_CRITERIA
        monitoring_start_time = critical_start_time + early_cutoff

        # 만약 모니터링 시작 시점이 subtask가 끝난 후라면 => 모니터링 불필요
        if monitoring_start_time > subtask_end_time:
            return False

        # 위 조건 모두 통과 시 => 모니터링 분할 적용
        return True

    # --------------------------------------------------------------------------
    #                   실제 확장 메서드들 (모니터링 / 일반 / 대기)
    # --------------------------------------------------------------------------
    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[SimulationNode]:
        """
        time-critical Subtask를 모니터링 분할:
         early_sub -> monitoring_sub(0.1s) -> remain_sub
         (이동시간 nav_time 포함, deadline 고려)
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        # --- 모니터링 분할에 필요한 정보(critical_start_time, early_cutoff 등) ---
        # 대부분은 _should_expand_with_monitoring()에서 1차로 검사했으나,
        # 실제 분할에 필요한 값들을 다시 한번 가져옴 (또는 캐싱/인자로 넘길 수도 있음)
        # ------------------------------------------------------------------------
        deadline_due, deadline_sub_name = (
            candidate.deadline.due_date,
            candidate.deadline.subtask_name,
        )
        constraints_start_names = self.constraint_handler.get_time_slots(
            deadline_sub_name, curr_state.constraints, "in"
        )
        critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
        if not critical_slots:
            return None  # 혹시나

        max_critical = max(critical_slots, key=lambda x: x.interval)
        critical_start_sub_name = max_critical.related_subtask_name
        max_critical_interval = max_critical.interval

        critical_start_time = 0.0
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == critical_start_sub_name:
                critical_start_time = ce.end_time
                break

        early_cutoff = max_critical_interval * BAYESIAN_CRITERIA

        # 전체 duration
        nav_time, new_location = self.nav_manager.compute_total_navigation_time(
            curr_node, candidate.subtask
        )
        total_duration = nav_time + candidate.subtask.duration.interval

        # cutoff보다 subtask가 더 일찍 끝나면 모니터링 필요X => None
        # (여기서도 guard-clause로 한 번 더 체크)
        if (critical_start_time + early_cutoff) > (
            curr_state.current_time + total_duration
        ):
            return self._expand_subtask_wo_monitoring(curr_node, candidate)

        # monitoring 할 객체 뽑기

        # ------------------------------------------------------------------------
        # 1) Monitoring 서브태스크로 분할
        early_sub, mon_sub, remain_sub = split_subtask_for_monitoring(
            curr_node=curr_node,
            candidate=candidate,
            nav_manager=self.nav_manager,
            early_cutoff=early_cutoff,
        )
        print(f"Critical Constraints : {critical_start_sub_name} ~ {deadline_sub_name}")
        print(f"original execution time : {total_duration}")
        print(f"early cutoff time : {early_cutoff}")
        print(f"early_sub execution time : {early_sub.duration.interval}")
        print(f"mon_sub execution time : {mon_sub.duration.interval}")
        print(f"remain_sub execution time : {remain_sub.duration.interval}")
        
        nav_start_to_critical_end = self.nav_manager.get_last_location(curr_node, early_sub)
        nav_end_to_critical_end = candidate.subtask.execution.primitive_actions[0].split(" ")[-1]
        primitive_0 = candidate.subtask.execution.primitive_actions[0]
        nav_time_to_critical_end = self.nav_manager.get_specific_nav_time(nav_start_to_critical_end, nav_end_to_critical_end)
        
        # deadline 체크 시 이동시간도 포함하여 검사
        if deadline_due < (curr_state.current_time + early_sub.duration.interval + nav_time_to_critical_end):
            # deadline 넘어가면 확장 무의미
            return None

        # 3) Constraints 그래프 복제/수정
        old_name = candidate.subtask.name
        new_constraints = copy.deepcopy(curr_state.constraints)
        if new_constraints.has_node(old_name):
            in_edges = list(new_constraints.in_edges(old_name, data=True))
            out_edges = list(new_constraints.out_edges(old_name, data=True))
            new_constraints.remove_node(old_name)
        else:
            in_edges, out_edges = [], []

        for pred, _, data in in_edges:
            new_constraints.add_edge(
                pred, early_sub.name, info=copy.deepcopy(data["info"])
            )
        for _, succ, data in out_edges:
            new_constraints.add_edge(
                remain_sub.name, succ, info=copy.deepcopy(data["info"])
            )

        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        # 모니터링 edge 추가
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

        # 4) Remaining subtasks 업데이트
        new_remaining = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        new_remaining.extend([mon_sub, remain_sub])

        # 5) 비용 계산
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, 0)
        new_cost = curr_heuristic + step_cost

        # 6) Completed Subtasks
        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=curr_state.current_time,
            end_time=curr_state.current_time + early_sub.duration.interval,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=curr_state.current_time + early_sub.duration.interval,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_subtask_with_monitoring] {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost,LOG_ROUND)}, Interval={round(completed_entry.start_time,2)}~{round(completed_entry.end_time,2)}\n"
            f"  -> remain={[r.name for r in new_remaining]}"
        )

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
        일반(Non-monitoring) Subtask 실행
        - 이동시간 + Subtask.duration만큼 소요
        - deadline 체크
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
            return None

        # Subtask 복사(실행시간 반영)
        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = exec_time

        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, 0)
        new_cost = curr_heuristic + step_cost

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
            f"[_expand_subtask_wo_monitoring] {candidate.subtask.name}\n"
            f"  -> Score={round(new_cost,LOG_ROUND)}, Interval={round(start_time,2)}~{round(end_time,2)}\n"
            f"  -> remain={[r.name for r in new_remaining]}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )

    def _expand_wait_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> SimulationNode:
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해 'Wait'를 추가
        - Wait 시간 = candidate.earliest_start_time - current_time
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        # 여기서는 nav_time을 거의 0으로 처리(Wait 위치 이동 없음 가정)
        # nav_time = self.nav_manager.compute_total_navigation_time(
        #     curr_node, candidate.subtask
        # )
        #new_location = self.nav_manager.get_last_location(curr_node, candidate.subtask)
        wait_start_time = curr_state.current_time
        wait_duration = candidate.earliest_start_time - curr_state.current_time
        if wait_duration < 0:
            wait_duration = 0  # 혹시 음수면 0으로



        nav_start_to_critical_end = curr_node.state.agent_location
        nav_end_to_critical_end = candidate.subtask.execution.primitive_actions[0].split(" ")[-1]
        nav_time_to_critical_end = self.nav_manager.get_specific_nav_time(nav_start_to_critical_end, nav_end_to_critical_end)
        new_location = nav_end_to_critical_end
        
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
                    f"Wait {wait_duration-nav_time_to_critical_end}",
                ],
            ),
            temporal_constraints=None,
        )

        new_completed = curr_state.completed_subtasks + [
            CompletedEntry(
                subtask=wait_sub,
                start_time=wait_start_time,
                end_time=wait_start_time + wait_duration,
            )
        ]
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=wait_start_time + wait_duration,
            agent_location=new_location,
        )

        # 휴리스틱 계산
        wait_candidate = Candidate(
            subtask=wait_sub,
            earliest_start_time=new_state.current_time,
            is_critical=False,
        )
        step_cost = self.cost_calculator.calc_heuristic(curr_node, wait_candidate, 0)
        new_cost = curr_heuristic + step_cost

        log.info(
            f"[_expand_wait_subtask] {wait_sub.name}\n"
            f"  -> Score={round(new_cost,LOG_ROUND)}, Interval={round(wait_start_time,2)}~{round(wait_start_time+wait_duration,2)}\n"
            f"  -> remain={[r.name for r in curr_state.remaining_subtasks]}"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
        )


# TODO WAIT Partial Wait by Monitoring
# TODO Wait하고 있을 때에는 ground truth값이 됐을 때 바로 그 wait를 종료하고 critical end subtask를 실행하면 좋을 것 같아요
