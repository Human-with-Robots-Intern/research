import copy
import itertools
from queue import PriorityQueue
from typing import List, NamedTuple, Optional

import networkx as nx

from core.task import SchedulerState, Subtask
from task_management import (
    ConstraintHandler,
    CostCalculator,
    NavigationManager,
    TimeSlot,
)
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.task_io import load_navigation_times
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class SimulationNode(NamedTuple):
    """
    우선순위 큐에서 사용할 탐색 노드.
    - heuristic_cost: 지금까지 누적된 비용 (높을수록 우선)
    - depth: 현재 탐색 깊이
    - leftover: time_slot 등에서 남은 시간(필요하면 사용)
    - tie_breaker: 우선순위가 같을 때 순서 결정용
    - state: 실제 스케줄 상태 (SchedulerState)
    """

    heuristic_cost: float
    depth: int
    elapsed_time: float
    agent_location: str
    tie_breaker: int
    state: SchedulerState


class Scheduler:
    """
    Beam Search (lookahead depth=N)로 Subtask 스케줄링하는 예시 코드.
    복잡한 로직(기다림, leftover_manager 등)은 제거하고,
    SimulationState를 일관성 있게 사용하도록 정리.
    """

    def __init__(
        self,
        init_subtasks: List[Subtask],
        init_constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
    ):

        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.subtasks_info = copy.deepcopy(init_subtasks)
        self.constraint_handler = ConstraintHandler(init_constraints)

        self.cost_calculator = CostCalculator(self.constraint_handler)
        self.nav_manager = NavigationManager(
            navigation_times=load_navigation_times(),
            all_subtasks_info=self.subtasks_info,
        )

        self._counter = itertools.count()  # tie-breaker용

    def extract_state(
        self, state: SchedulerState, node: SimulationNode
    ) -> SchedulerState:
        completed_subtask = node.state.completed_subtasks[1]
        completed_subtasks = state.completed_subtasks + [completed_subtask]
        remaining_subtasks = [
            remaining_subtask
            for remaining_subtask in state.remaining_subtasks
            if remaining_subtask.name != completed_subtask.name
        ]
        return SchedulerState(
            subtask=node.state.completed_subtasks[1],
            completed_subtasks=completed_subtasks,
            remaining_subtasks=remaining_subtasks,
            agent_location=node.state.agent_location,
        )

    def get_new_state(
        self,
        parent_state: SchedulerState,
        current_constraints: nx.DiGraph,
    ) -> Optional[SchedulerState]:
        """
        1) 현재 Subtask에 대한 out-edge(temporal constraint) 확인.
        2) separation_interval > 0이면 time_slot 기반 탐색(_simulate_time_slot),
           아니면 lookahead 기반 탐색(_simulate_lookahead).
        3) 탐색 결과 중 '다음으로 실행할 Subtask'를 골라 SchedulerState로 반환.
        """
        # 제약 갱신
        self.constraint_handler.constraints = current_constraints

        # 간단히, candidate_subtask의 out-edge 중 최소 interval만 사용
        temporal_constraint: TimeSlot = (
            self.constraint_handler.get_temporal_constraints(
                parent_state.subtask.name,
                direction="out",
            )
        )

        if temporal_constraint.interval > 0:
            child_node = self._simulate_time_slot(parent_state, temporal_constraint)
        else:
            child_node = self._simulate_lookahead(parent_state)

        if not child_node:
            log.warning("No valid next step found.")
            return None

        return self.extract_state(parent_state, child_node)

    # ------------------------------------------------
    #   1) Time Slot 기반 간단 탐색
    # ------------------------------------------------
    def _simulate_time_slot(
        self,
        current_state: SchedulerState,
        temporal_constraint: TimeSlot,
    ) -> Optional[SimulationNode]:
        """
        separation_interval 시간 동안 실행할 수 있는 Subtask들을
        우선순위 큐로 탐색. (여기서는 간단히 모든 조합이 아닌,
        '하나씩'만 골라보는 방식)
        """
        queue = PriorityQueue()
        # 초기 상태
        queue.put(
            SimulationNode(
                heuristic_cost=0.0,
                depth=0,
                elapsed_time=0.0,
                tie_breaker=next(self._counter),
                agent_location=current_state.agent_location,
                state=current_state,
            )
        )

        collected_solutions: List[SimulationNode] = []

        separation_interval = temporal_constraint.interval
        is_critical = temporal_constraint.is_critical
        related_subtask_name = temporal_constraint.related_subtask_name

        while not queue.empty():
            curr_node = queue.get()

            curr_heuristic_cost = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_elapsed_time = curr_node.elapsed_time
            leftover = separation_interval - curr_elapsed_time

            if curr_depth >= self.simulation_depth:
                # 탐색 제한 도달
                collected_solutions.append(curr_node)
                continue

            # 현재 상태에서 실행 가능한 subtask들
            expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_node
            )
            if not expandable_subtasks:
                # feasible subtask가 없으므로, 더 이상 확장 불가
                collected_solutions.append(curr_node)
                continue

            # 각 candidate에 대해 확장
            is_expanded_curr_step = False
            for sub in expandable_subtasks:
                if sub.name == related_subtask_name:
                    # critical -> leftover == 0이어야 실행 가능
                    if is_critical and leftover != 0:
                        continue
                    # non-critical -> leftover <= 0이어야 실행 가능
                    if (not is_critical) and leftover > 0:
                        continue
                nav_time, agent_location = self.nav_manager.compute_navigation_time(
                    curr_node, sub
                )
                copied_sub = copy.deepcopy(sub)
                copied_sub.duration.interval += nav_time

                if copied_sub.duration.interval > leftover and leftover > 0:
                    # separation_interval 내에 실행 불가
                    continue

                new_heuristic_cost = self.cost_calculator.calc_heuristic_cost(
                    curr_node, sub, nav_time
                )
                new_heuristic_cost += curr_heuristic_cost
                new_depth = curr_depth + 1
                new_elapsed_time = curr_elapsed_time + copied_sub.duration.interval
                updated_completed = curr_node.state.completed_subtasks + [sub]
                new_remain_subtasks = [
                    r for r in curr_node.state.remaining_subtasks if r.name != sub.name
                ]

                new_scheduler_state = SchedulerState(
                    copied_sub,
                    updated_completed,
                    new_remain_subtasks,
                    curr_node.state.agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        elapsed_time=new_elapsed_time,
                        agent_location=agent_location,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )
                is_expanded_curr_step = True
            if is_critical and leftover > 0 and not is_expanded_curr_step:
                wait_sub = Subtask(
                    task_name=None,
                    name=(f"Wait for {related_subtask_name}"),
                    duration=leftover,
                    repetition=1,
                    type="Wait",
                    execution=None,
                    temporal_constraints=None,
                )

                new_heuristic_cost = curr_heuristic_cost + leftover
                new_elapsed_time = curr_elapsed_time + leftover
                new_depth = curr_depth + 1

                # "부모 node"에서 completed_subtasks 가져오기
                new_completed_subtasks = curr_node.state.completed_subtasks + [wait_sub]
                new_remain_subtasks = curr_node.state.remaining_subtasks

                new_scheduler_state = SchedulerState(
                    subtask=wait_sub,
                    completed_subtasks=new_completed_subtasks,
                    remaining_subtasks=new_remain_subtasks,
                    agent_location=curr_node.state.agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        elapsed_time=new_elapsed_time,
                        agent_location=curr_node.state.agent_location,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )

        if not collected_solutions:
            return None

        # 비용 오름차순으로 정렬 -> 상위 beam_width만 추려서, 그중 최대 cost를 best
        sorted_paths = sorted(
            collected_solutions, key=lambda x: x.heuristic_cost, reverse=True
        )

        best_result = sorted_paths[0] if sorted_paths else None

        return best_result

    # ------------------------------------------------
    #   2) Lookahead (depth=simulation_depth) 기반 탐색
    # ------------------------------------------------
    def _simulate_lookahead(
        self,
        init_state: SchedulerState,  # subtask, completed_subtasks, remaining_subtasks (subtask는 부모 노드, completed_subtasks는 부모 노드의 completed_subtasks (subtask 제외), remaining_subtasks는 부모 노드의 remaining_subtasks)
    ) -> Optional[SimulationNode]:
        """
        lookahead(깊이=simulation_depth)까지 확장하는
        Beam Search 예시.
        """
        queue = PriorityQueue()
        # 초기 상태
        queue.put(
            SimulationNode(
                heuristic_cost=0.0,
                depth=0,
                elapsed_time=0.0,
                tie_breaker=next(self._counter),
                agent_location=init_state.agent_location,
                state=init_state,
            )
        )

        collected_solutions: List[SimulationNode] = []

        while not queue.empty():
            curr_node = queue.get()

            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_elapsed_time = curr_node.elapsed_time

            if curr_depth >= self.simulation_depth:
                # 탐색 제한 도달
                collected_solutions.append(curr_node)
                continue

            # 현재 상태에서 실행 가능한 subtask들
            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_node
            )
            if not feasible_subtasks:
                # feasible subtask가 없으므로, 더 이상 확장 불가
                collected_solutions.append(curr_node)
                continue

            # 각 candidate에 대해 확장
            for sub in feasible_subtasks:
                nav_time, agent_location = self.nav_manager.compute_navigation_time(
                    curr_node, sub
                )
                copied_sub = copy.deepcopy(sub)
                copied_sub.duration.interval += nav_time

                new_heuristic = self.cost_calculator.calc_heuristic_cost(
                    curr_node, sub, nav_time
                )
                new_heuristic += curr_heuristic
                new_depth = curr_depth + 1
                new_elapsed_time = curr_elapsed_time + copied_sub.duration.interval
                updated_completed = curr_node.state.completed_subtasks + [sub]
                updated_remain = [
                    r for r in curr_node.state.remaining_subtasks if r.name != sub.name
                ]

                new_scheduler_state = SchedulerState(
                    copied_sub,
                    updated_completed,
                    updated_remain,
                    curr_node.state.agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic,
                        depth=new_depth,
                        elapsed_time=new_elapsed_time,
                        agent_location=agent_location,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )

        if not collected_solutions:
            return None

        # 비용 오름차순으로 정렬 -> 상위 beam_width만 추려서, 그중 최대 cost를 best
        sorted_paths = sorted(
            collected_solutions, key=lambda x: x.heuristic_cost, reverse=True
        )

        best_result = sorted_paths[0] if sorted_paths else None

        return best_result
