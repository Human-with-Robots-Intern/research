import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.agent import Agent
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
from scheduler.dataclass import CompletedEntry, SchedulerState, SimulationNode
from utils import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH, create_module_logger
from utils.constants import BAYESIAN_CRITERIA, MONITORING_DURATION
from utils.task import get_monitoring_subtask

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Scheduler:

    def __init__(
        self,
        agent: Agent,
        init_constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
    ):
        self.agent = agent
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler(init_constraints, self.nav_manager)
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
        self,
        parent_state: SchedulerState,
        current_constraints: nx.DiGraph,
    ) -> Optional[SchedulerState]:

        # 제약 갱신
        self.constraint_handler.constraints = current_constraints

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
            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth

            # 만약 이미 모든 서브태스크를 끝냈거나(remaining_subtasks가 없음)
            # 혹은 depth가 한계(simulation_depth) 도달하면
            # 더 이상 확장하지 않고 best_solutions에 저장
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "즉시 실행 가능한" 서브태스크 찾기
            # 제약에 들어갈 수 있는 서브태스크인지 확인 필요
            feasible_subs, not_yet_feasible_subs = (
                self.constraint_handler.get_feasible_subtasks(curr_node)
            )

            # --- (2) 즉시 실행 어려운 경우가 있다면, => '대기(Wait)' 로직 ---
            self._expand_wait_subtasks(not_yet_feasible_subs, curr_node, queue, counter)

            # --- (3) 즉시 실행 가능한 각 서브태스크 확장 ---
            expanded_nodes: List[SimulationNode] = []
            for candidate_sub in feasible_subs:
                # Critical constraint에 의해 Monitoring subtask로 쪼개지는 경우가 결정 됨.
                out_slot = self.constraint_handler.get_temporal_constraints(
                    curr_state.subtask.name, "out"
                )
                if out_slot.is_critical:
                    # time-critical인 경우 -> 반드시 분할
                    partial_nodes = self._expand_subtask_with_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )
                    expanded_nodes.extend(partial_nodes)
                else:
                    new_node = self._expand_subtask_wo_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )
                    expanded_nodes.append(new_node)

            # --- (4) Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
            for i, nd in enumerate(expanded_nodes):
                if i < self.beam_width:
                    queue.put(nd)
                else:
                    break

        # --- (5) 모두 확장 완료 후, best_solutions에서 비용 최대 해를 선정 ---
        if not best_solutions:
            print(curr_node.state.completed_subtasks)
            print("No feasible solution found.")
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
        best_node = best_solutions[0]  # 최대 비용 해

        return best_node.state

    def _expand_wait_subtasks(
        self,
        not_yet_feasible_subs: List,
        curr_node: SimulationNode,
        queue: PriorityQueue,
        counter: itertools.count,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해
        'Wait Subtask'를 생성하여 해당 시간을 대기하는 노드를 확장
        """
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        for sub, earliest_start_time, is_critical in sorted(
            not_yet_feasible_subs, key=lambda x: x[1]
        ):
            wait_time = earliest_start_time - curr_state.current_time
            if wait_time <= 1e-9:
                continue

            wait_sub = Subtask(
                task_name=None,
                name=f"Wait for {sub.name}",
                duration=Duration(interval=wait_time, type="Controllable"),
                repetition=1,
                type="Wait",
                execution=Execution(
                    objects=None, primitive_actions=[f"Wait {wait_time}"]
                ),
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
                current_time=curr_state.current_time + wait_time,
                agent_location=curr_state.agent_location,
            )

            new_cost = curr_heuristic + wait_time
            new_node = SimulationNode(
                heuristic_cost=new_cost,
                depth=curr_depth + 1,
                tie_breaker=next(counter),
                state=new_state,
            )
            queue.put(new_node)

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

    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
    ) -> List[SimulationNode]:
        """
        time-critical subtask에 대하여,
        'subtask_start_time < monitoring_timing < subtask_end_time'일 때
        -> early + monitoring + remain
        """

        new_nodes = []

        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

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

        # 실제로 "subtask_start_time < monitoring_timing < subtask_end_time"인지 확인
        if (
            monitoring_timing <= subtask_start_time
            or monitoring_timing >= subtask_end_time
        ):
            # 모니터링 분할 불가능 → 그냥 fallback
            log.debug("Monitoring timing not in the middle => skip partial expansion.")
            return []  # 빈 리스트 -> 해당 subtask 확장 안함

        # --------------------------------------------------------
        # A) Early part
        # TODO Monitoring에 의해 subtask가 쪼개지는 경우, Primitive action을 어떻게 끊을까?
        early_duration = monitoring_timing - subtask_start_time
        early_exec_time = early_duration  # nav_time은 처음에 합쳐도 무방.
        early_end = subtask_start_time + early_exec_time

        sub_early = copy.deepcopy(candidate_sub)
        sub_early.name += "_early"
        sub_early.duration.interval = early_exec_time

        cost_early = self.cost_calculator.calc_heuristic_cost(
            curr_node,
            sub_early,
            nav_time,
        )
        cost_after_early = curr_heuristic + cost_early

        completed_early = CompletedEntry(
            subtask=sub_early,
            start_time=subtask_start_time,
            end_time=early_end,
        )
        after_early_completed = curr_state.completed_subtasks + [completed_early]

        # --------------------------------------------------------
        # B) Monitoring Subtask
        mon_sub = get_monitoring_subtask()
        mon_sub.name = candidate_sub.name + "_monitoring"
        mon_start = early_end
        mon_end = mon_start + MONITORING_DURATION

        cost_mon = self.cost_calculator.calc_heuristic_cost(curr_node, mon_sub, 0.0)
        cost_after_mon = cost_after_early + cost_mon

        completed_monitoring = CompletedEntry(
            subtask=mon_sub,
            start_time=mon_start,
            end_time=mon_end,
        )
        after_mon_completed = after_early_completed + [completed_monitoring]

        # --------------------------------------------------------
        # C) Remain part
        remain_duration = subtask_end_time - monitoring_timing
        remain_start = mon_end
        remain_end = remain_start + remain_duration

        sub_remain = copy.deepcopy(candidate_sub)
        sub_remain.name += "_remain"
        sub_remain.duration.interval = remain_duration

        cost_remain = self.cost_calculator.calc_heuristic_cost(
            curr_node, sub_remain, 0.0
        )
        final_cost = cost_after_mon + cost_remain

        completed_remain = CompletedEntry(
            subtask=sub_remain,
            start_time=remain_start,
            end_time=remain_end,
        )
        final_completed = after_mon_completed + [completed_remain]

        # 남은 서브태스크: 원본 candidate_sub는 끝났다고 처리
        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate_sub.name
        ]

        final_state = SchedulerState(
            subtask=sub_remain,  # 마지막으로 완료된 subtask
            completed_subtasks=final_completed,
            remaining_subtasks=new_remaining,
            current_time=remain_end,
            agent_location=new_location,
        )

        partial_node = SimulationNode(
            heuristic_cost=final_cost,
            depth=curr_depth + 3,  # early + monitoring + remain => 3번 실행
            tie_breaker=next(counter),
            state=final_state,
        )
        new_nodes.append(partial_node)

        return new_nodes

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> SchedulerState:

        parent_completed_set = {
            ce.subtask.name for ce in parent_state.completed_subtasks
        }
        child_plan = child_state.completed_subtasks

        # 자식 노드에서 새로 추가된 CompletedEntry들(=부모엔 없던 subtask)
        new_entries = [
            ce for ce in child_plan if ce.subtask.name not in parent_completed_set
        ]
        if not new_entries:
            return child_state

        new_entry = new_entries[0]
        new_subtask = new_entry.subtask
        new_completed_subtasks = parent_state.completed_subtasks + [new_entry]
        new_remaining_subtasks = [
            r for r in parent_state.remaining_subtasks if r.name != new_subtask.name
        ]

        return SchedulerState(
            subtask=new_subtask,
            completed_subtasks=new_completed_subtasks,
            remaining_subtasks=new_remaining_subtasks,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )
