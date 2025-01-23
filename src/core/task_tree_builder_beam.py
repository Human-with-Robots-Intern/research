import copy
import itertools
from queue import PriorityQueue
from typing import List, NamedTuple, Optional

import networkx as nx

from core.task import SchedulerState, Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management import ConstraintHandler 
from task_management.task_tree import TaskTree
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.task_io import load_navigation_times
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class SimulationState(NamedTuple):
    """
    우선순위 큐에서 사용할 탐색 노드.
    - heuristic_cost: 지금까지 누적된 비용 (낮을수록 우선)
    - depth: 현재 탐색 깊이
    - leftover: time_slot 등에서 남은 시간(필요하면 사용)
    - tie_breaker: 우선순위가 같을 때 순서 결정용
    - state: 실제 스케줄 상태 (SchedulerState)
    """

    heuristic_cost: float
    depth: int
    leftover: float
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
        self.tree = TaskTree()
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

    def get_new_state(
        self,
        current_state: SchedulerState,
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
        temporal_constraint = self.constraint_handler.get_temporal_constraints(
            current_state.subtask.name,
            direction="out",
        )

        if temporal_constraint.interval > 0:
            best_result = self._simulate_time_slot(current_state, temporal_constraint)
        else:
            best_result = self._simulate_lookahead(current_state)

        if not best_result:
            log.warning("No valid next step found.")
            return None

        final_state = best_result.state

        return final_state

    # ------------------------------------------------
    #   1) Time Slot 기반 간단 탐색
    # ------------------------------------------------
    def _simulate_time_slot(
        self,
        init_state: SchedulerState,
        separation_interval: ,
    ) -> Optional[SimulationState]:
        """
        separation_interval 시간 동안 실행할 수 있는 Subtask들을
        우선순위 큐로 탐색. (여기서는 간단히 모든 조합이 아닌,
        '하나씩'만 골라보는 방식)
        """
        queue = PriorityQueue()
        # 초기 상태 삽입
        queue.put(
            SimulationState(
                heuristic_cost=0.0,
                depth=0,
                leftover=separation_interval,
                tie_breaker=next(self._counter),
                state=init_state,
            )
        )

        best_solutions = []

        while not queue.empty():
            current_node = queue.get()
            curr_cost = current_node.heuristic_cost
            curr_depth = current_node.depth
            leftover = current_node.leftover
            curr_state = current_node.state

            # 현재 leftover에서 실행 가능한 subtask 조회
            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_state
            )
            expanded_any = False

            for sub in feasible_subtasks:
                nav_time = self.nav_manager.calc_time(curr_state, sub)
                total_dur = sub.duration.interval + nav_time
                if total_dur <= leftover:
                    # 확장 가능
                    new_cost = curr_cost + total_dur
                    new_depth = curr_depth + 1
                    new_leftover = leftover - total_dur

                    # partial_plan + sub
                    updated_plan = curr_state.completed_subtasks + [sub]
                    updated_remain = [
                        r for r in curr_state.remaining_subtasks if r.name != sub.name
                    ]
                    new_scheduler_state = SchedulerState(
                        sub.name, updated_plan, updated_remain
                    )

                    queue.put(
                        SimulationState(
                            heuristic_cost=new_cost,
                            depth=new_depth,
                            leftover=new_leftover,
                            tie_breaker=next(self._counter),
                            state=new_scheduler_state,
                        )
                    )
                    expanded_any = True

            if not expanded_any:
                # 더 이상 확장 불가능 -> 현 상태를 결과로 기록
                best_solutions.append(current_node)

        if not best_solutions:
            return None

        # 비용 오름차순, depth 내림차순 등으로 정렬
        sorted_candidates = sorted(
            best_solutions, key=lambda x: (x.heuristic_cost, -x.depth)
        )
        # beam_width 만큼만 추림
        pruned = sorted_candidates[: self.beam_width]

        # 그중 cost 최소, depth 최대인 것을 베스트로 선정
        best_result = pruned[0]
        return best_result

    # ------------------------------------------------
    #   2) Lookahead (depth=simulation_depth) 기반 탐색
    # ------------------------------------------------
    def _simulate_lookahead(
        self,
        init_state: SchedulerState,
    ) -> Optional[SimulationState]:
        """
        lookahead(깊이=simulation_depth)까지 확장하는
        Beam Search 예시.
        """
        queue = PriorityQueue()
        # 초기 상태
        queue.put(
            SimulationState(
                heuristic_cost=0.0,
                depth=0,
                leftover=0.0,  # 여기서는 사용 안 함
                tie_breaker=next(self._counter),
                state=init_state,
            )
        )

        final_results: List[SimulationState] = []

        while not queue.empty():
            current_node = queue.get()
            curr_cost = current_node.heuristic_cost
            curr_depth = current_node.depth
            curr_state = current_node.state

            if curr_depth >= self.simulation_depth:
                # 탐색 제한 도달
                final_results.append(current_node)
                continue

            # 현재 상태에서 실행 가능한 subtask들
            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_state
            )
            if not feasible_subtasks:
                # 더 이상 확장 불가
                final_results.append(current_node)
                continue

            # 각 candidate에 대해 확장
            for sub in feasible_subtasks:
                nav_time = self.nav_manager.calc_time(curr_state, sub)
                cost_val = self.cost_calculator.calc_heuristic_cost(
                    curr_state, sub, nav_time
                )

                new_cost = curr_cost + cost_val
                new_depth = curr_depth + 1

                updated_plan = curr_state.completed_subtasks + [sub]
                updated_remain = [
                    r for r in curr_state.remaining_subtasks if r.name != sub.name
                ]
                new_scheduler_state = SchedulerState(
                    sub.name,
                    updated_plan,
                    updated_remain,
                )

                queue.put(
                    SimulationState(
                        heuristic_cost=new_cost,
                        depth=new_depth,
                        leftover=0.0,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )

        if not final_results:
            return None

        # 비용 오름차순으로 정렬 -> 상위 beam_width만 추려서, 그중 최소 cost를 best
        sorted_paths = sorted(final_results, key=lambda x: x.heuristic_cost)
        pruned = sorted_paths[: self.beam_width]
        best_result = pruned[0] if pruned else None

        return best_result
