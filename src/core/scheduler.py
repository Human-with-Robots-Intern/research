import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.agent import Agent
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
from scheduler.dataclass import CompletedEntry, SchedulerState, SimulationNode
from utils import DEFAULT_BEAM_WIDTH, SIMULATION_DEPTH, create_module_logger
from utils.constants import BAYESIAN_CRITERIA, MONITORING_DURATION
from utils.task import get_monitoring_subtask
from utils.task.task_util import (
    make_early_subtask,
    make_monitoring_subtask,
    make_remain_subtask,
)

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Scheduler:

    def __init__(
        self,
        agent: Agent,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):
        self.agent = agent
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler(self.nav_manager)
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
        self,
        parent_state: SchedulerState,
    ) -> Optional[SchedulerState]:
        child_state = self._simulate_beam_search(parent_state)
        return self._extract_state(parent_state, child_state)

    def _simulate_beam_search(
        self,
        init_state: SchedulerState,
    ) -> Optional[SchedulerState]:

        queue = PriorityQueue()
        counter = itertools.count()

        init_node = SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=next(counter),
            state=init_state,
        )
        queue.put(init_node)
        best_solutions = []

        while not queue.empty():
            curr_node = queue.get()
            curr_state = curr_node.state
            curr_depth = curr_node.depth

            expanded_nodes: List[SimulationNode] = []

            # 직전 subtask가 time-critical 제약을 시작한다면, monitoring subtask가 추가되어야 함.
            out_slot = self.constraint_handler.get_temporal_constraints(
                curr_state.subtask.name, curr_state.constraints, "out"
            )

            # 만약 이미 모든 서브태스크를 끝냈거나, 시뮬레이션 깊이에 도달했다면
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "즉시 실행 가능한" 서브태스크 찾기
            # 제약에 들어갈 수 있는 서브태스크인지 확인 필요
            feasible_subs, not_yet_feasible_subs = (
                self.constraint_handler.get_feasible_subtasks(curr_node)
            )

            # "early_sub" 직후라면 => monitoring_sub가 우선 실행
            if curr_state.pending_monitoring:
                feasible_subs = [curr_state.pending_monitoring]
                not_yet_feasible_subs = []

            # --- (2) 즉시 실행 가능한 각 서브태스크 확장 ---
            for candidate_sub in feasible_subs:
                # TODO 급조된 분기 로직이라... 맞는지 모르겠음
                if (
                    out_slot.is_critical
                    and not candidate_sub.decomposed
                    and not curr_node.state.subtask.decomposed
                ):
                    # time-critical인 경우 -> monitoring subtask으로 분할
                    new_node = self._expand_subtask_with_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )
                else:
                    # time-critical이 아닌 경우 -> 일반적인 subtask 실행
                    new_node = self._expand_subtask_wo_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )

            # (3) 아직 시작 시간이 되지 않은 서브태스크(not_yet_feasible_subs)에 대해, wait 고려
            # is_critical : candidate_sub에 time_critical 제약이 있는지 여부
            for (
                candidate_sub,
                earliest_start_time,
                is_critical,
            ) in sorted(not_yet_feasible_subs, key=lambda x: x[1]):
                if (
                    out_slot.is_critical
                    and not candidate_sub.decomposed
                    and not curr_node.state.subtask.decomposed
                ):
                    # time-critical인 경우 -> monitoring subtask으로 분할
                    new_node = self._expand_wait_subtasks_with_monitoring(
                        curr_node, candidate_sub, counter, earliest_start_time
                    )
                else:
                    new_node = self._expand_wait_subtasks(
                        curr_node, candidate_sub, counter, earliest_start_time
                    )

            expanded_nodes.append(new_node)

            # --- (4) Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):
                if i < self.beam_width:
                    queue.put(nd)
                else:
                    break

        # --- (5) 모두 확장 완료 후, best_solutions에서 비용 최소 해를 선정 ---
        if not best_solutions:
            print("No feasible solution found.")
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        best_node = best_solutions[0]  # 최소 비용 해

        return best_node.state

    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
    ) -> SimulationNode:
        """
        time-critical subtask -> early, monitoring, remain
        + DAG에서 ordering dependency: early -> mon -> remain
        + 첫 단계에서는 early_sub만 실행(1-step)
        """

        curr_state = curr_node.state

        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        _, _, related_sub_name = self.constraint_handler.get_temporal_constraints(
            curr_state.subtask.name, curr_constraints, "out"
        )

        # (1) 이동 시간 계산
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )

        # (2) 실제 Subtask 실행 시간
        subtask_start_time = curr_state.current_time
        subtask_end_time = (
            subtask_start_time + candidate_sub.duration.interval + nav_time
        )

        # (3) 모니터링 시점 계산 (예: subtask_start_time + 0.7 * (subtask duration))
        monitoring_timing = (
            subtask_start_time
            + (nav_time + candidate_sub.duration.interval) * BAYESIAN_CRITERIA
        )

        # TODO Monitoring에 의해 subtask가 쪼개지는 경우, Primitive action을 어떻게 끊을까?
        # Monitoring Subtask 생성에 따른 DAG 업데이트
        new_constraints = copy.deepcopy(curr_constraints)
        # 원본 subtask 제거
        if new_constraints.has_node(candidate_sub.name):
            new_constraints.remove_node(candidate_sub.name)

        # early_sub, mon_sub, remain_sub 생성
        early_dur = monitoring_timing - subtask_start_time
        remain_dur = subtask_end_time - monitoring_timing

        early_sub = make_early_subtask(candidate_sub, early_dur)
        mon_sub = make_monitoring_subtask(related_sub_name)
        remain_sub = make_remain_subtask(candidate_sub, remain_dur)

        # DAG에 add_node
        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        # 분할하여 얻게 된 ordering dependency 추가
        # (1) early -> mon_sub
        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        # (2) mon_sub -> remain_sub
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        # 원본 subtask의 in/out edge 정보 가져오기
        in_edges = curr_constraints.in_edges(candidate_sub.name, data=True)
        out_edges = curr_constraints.out_edges(candidate_sub.name, data=True)
        for pred, _, data in in_edges:
            new_constraints.add_edge(pred, early_sub.name, info=data.get("info", {}))
        for _, succ, data in out_edges:
            new_constraints.add_edge(remain_sub.name, succ, info=data.get("info", {}))

        # remaining_subtasks 업데이트:
        # 기존 candidate_sub 제거 후, early_sub를 즉시 실행 대상으로,
        # mon_sub와 remain_sub는 이후 단계에서 실행되도록 remaining_subtasks에 추가.
        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate_sub.name
        ]

        new_remaining.append(mon_sub)
        new_remaining.append(remain_sub)

        # (8) early_sub 1-step 실행: 실제로 early_sub만 실행 (나머지는 이후에 Beam Search 확장을 통해 실행)
        start_time = curr_state.current_time
        end_time = (
            start_time + early_sub.duration.interval
        )  # early_sub 실행 시간 (nav_time 포함)
        step_cost = self.cost_calculator.calc_heuristic_cost(
            curr_node, early_sub, nav_time
        )
        new_cost = curr_heuristic + step_cost

        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # (9) 새 SchedulerState 생성: constraints는 업데이트된 new_constraints를 사용
        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=mon_sub,
            constraints=new_constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )

        return new_node

    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: int,
    ) -> SimulationNode:
        """
        Subtask 1개에 포함된 기존 primitive action 전체를 수행하는 노드 확장
        (Monitoring subtask에 의해 쪼개지지 않는 경우?!)
        """
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        # subtask 수행 시간 계산 (이동 시간 포함)
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )
        exec_time = candidate_sub.duration.interval + nav_time
        start_time = curr_state.current_time
        end_time = start_time + exec_time

        # 원본 데이터 값 임의 수정 방지용 subtask 객체 복사
        copied_sub = copy.deepcopy(candidate_sub)
        copied_sub.duration.interval = exec_time

        # Heuristic cost 계산
        new_heuristic_cost = self.cost_calculator.calc_heuristic_cost(
            curr_node, candidate_sub, nav_time
        )
        new_cost = curr_heuristic + new_heuristic_cost

        # 완료 정보 업데이트
        new_completed = curr_state.completed_subtasks + [
            CompletedEntry(
                subtask=copied_sub,
                start_time=start_time,
                end_time=end_time,
            )
        ]
        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate_sub.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=None,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtasks_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
        earliest_start_time: float,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 서브태스크에 대해
        1) 일반 Wait (earliest_start_time까지)
        2) time-critical이면 모니터링 시점에 맞춘 partial Wait
        등을 고려하여 노드를 확장.
        """

        curr_state = curr_node.state

        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        _, _, related_sub_name = self.constraint_handler.get_temporal_constraints(
            curr_state.subtask.name, curr_constraints, "out"
        )

        # (1) 이동 시간 계산
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )

        # (2) 실제 Subtask 실행 시간
        # TODO Wait는 목표 subtask 위치까지 가서 기다려야 하는거 아니야? Nav time이 필요한지 확인
        monitoring_timing = (
            curr_state.current_time
            + (earliest_start_time - curr_state.current_time) * BAYESIAN_CRITERIA
        )

        wait_duration = (
            monitoring_timing - curr_state.current_time - MONITORING_DURATION
        )

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate_sub.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None, primitive_actions=[f"Wait {wait_duration}"]
            ),
            temporal_constraints=None,
        )

        mon_sub = make_monitoring_subtask(related_sub_name)

        # (8) early_sub 1-step 실행: 실제로 early_sub만 실행 (나머지는 이후에 Beam Search 확장을 통해 실행)
        start_time = curr_state.current_time
        end_time = (
            start_time + wait_sub.duration.interval
        )  # early_sub 실행 시간 (nav_time 포함)
        step_cost = self.cost_calculator.calc_heuristic_cost(
            curr_node, wait_sub, nav_time
        )
        new_cost = curr_heuristic + step_cost

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_remaining = curr_state.remaining_subtasks + [mon_sub]
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # (9) 새 SchedulerState 생성: constraints는 업데이트된 new_constraints를 사용
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=mon_sub,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )

        return new_node

    def _expand_wait_subtasks(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
        earliest_start_time: float,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해
        'Wait Subtask'를 생성하여 해당 시간을 대기하는 노드를 확장
        """
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        wait_time = earliest_start_time - curr_state.current_time

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate_sub.name}",
            duration=Duration(interval=wait_time, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(objects=None, primitive_actions=[f"Wait {wait_time}"]),
            temporal_constraints=None,
        )

        new_completed = curr_state.completed_subtasks + [
            CompletedEntry(
                subtask=wait_sub,
                start_time=curr_state.current_time,
                end_time=curr_state.current_time + wait_time,
            )
        ]
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            pending_monitoring=None,
            constraints=curr_state.constraints,
            current_time=curr_state.current_time + wait_time,
            agent_location=curr_state.agent_location,
        )

        new_node = SimulationNode(
            heuristic_cost=curr_heuristic
            + self.cost_calculator.calc_heuristic_cost(curr_node, wait_sub, 0),
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> Optional[SchedulerState]:
        """
        beam search로 확장된 state(자식)에서 '새로 실행된 1-step'만 parent_state에 반영
        """
        if child_state is None:
            return None

        # 이전 상태에서 이미 완료된 서브태스크 이름 집합
        parent_completed_set = {
            ce.subtask.name for ce in parent_state.completed_subtasks
        }
        # 새로운 상태에서 완료된 서브태스크 리스트
        child_plan = child_state.completed_subtasks

        # 새로운 상태에서 완료된 서브태스크 중, 이번에 새로 추가된 subtask만 추출
        new_entries = [
            ce for ce in child_plan if ce.subtask.name not in parent_completed_set
        ]
        if not new_entries:
            return child_state

        # 새로 추가된 subtask 중 첫 번째 것만 가져옴
        new_entry = new_entries[0]
        new_subtask = new_entry.subtask
        new_completed_subtasks = parent_state.completed_subtasks + [new_entry]

        # 만약 이번에 새로 추가되는 subtask가 time critical을 시작한다면, 부모의 제약 조건을 사용.
        if not new_subtask.decomposed:
            new_constraints = parent_state.constraints
            new_remaining_subtasks = [
                r for r in parent_state.remaining_subtasks if r.name != new_subtask.name
            ]

        else:
            new_constraints = child_state.constraints
            additional_remaining_subtasks = [
                new_entry.subtask for new_entry in new_entries[1:]
            ]

            # 최종 결과 리스트
            new_remaining_subtasks = []

            # 중복 방지를 위한 집합
            added_names = set()

            for new_completed_sub in new_completed_subtasks:
                added_names.add(new_completed_sub.subtask.name)

            # 1️⃣ child_state.remaining_subtasks에서 중복되지 않는 값 추가
            for sub in child_state.remaining_subtasks:
                if sub.name not in added_names:
                    new_remaining_subtasks.append(sub)
                    added_names.add(sub.name)

            # 2️⃣ additional_remaining_subtasks에서도 유니크한 값 추가
            for sub in additional_remaining_subtasks:
                if sub.name not in added_names:
                    new_remaining_subtasks.append(sub)
                    added_names.add(sub.name)  # 추가된 이름을 중복 방지 집합에 저장

        # pending_monitoring이 있었는데, 새로 추가된 subtask가 monitoring이었다면 제거
        if (
            parent_state.pending_monitoring is not None
            and new_subtask.name == parent_state.pending_monitoring.name
        ):
            next_pending_monitoring = None
        else:
            # 그 외의 경우는 기존 자식 state의 pending_monitoring 그대로
            next_pending_monitoring = child_state.pending_monitoring

        # parent_state에 pending_monitoring이 있었다면 그대로 가져감
        next_state = SchedulerState(
            subtask=new_subtask,
            completed_subtasks=new_completed_subtasks,
            remaining_subtasks=new_remaining_subtasks,
            pending_monitoring=next_pending_monitoring,
            constraints=new_constraints,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )

        return next_state
