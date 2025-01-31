import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.task import Subtask
from task_management import ConstraintHandler, CostCalculator, NavigationManager
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.dataclass import CompletedEntry, SchedulerState, SimulationNode
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class Scheduler:

    def __init__(
        self,
        init_constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
    ):

        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.constraint_handler = ConstraintHandler(init_constraints)
        self.cost_calculator = CostCalculator(self.constraint_handler)
        self.nav_manager = NavigationManager()

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
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
        child_state = self._simulate_beam_search(parent_state)

        if not child_state:
            log.warning("No valid next step found.")
            return None

        return self._extract_state(parent_state, child_state)

    def _simulate_beam_search(
        self,
        init_state: SchedulerState,
    ) -> Optional[SchedulerState]:

        queue = PriorityQueue()
        counter = itertools.count()  # tie-breaker(동점자 처리용)

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
            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_state = curr_node.state

            # 만약 이미 모든 서브태스크를 끝냈거나(remaining_subtasks가 없음)
            # 혹은 depth가 한계(simulation_depth) 도달하면
            # 더 이상 확장하지 않고 best_solutions에 저장
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "즉시 실행 가능한" 서브태스크 찾기
            feasible_subs, not_yet_feasible_subs = (
                self.constraint_handler.get_feasible_subtasks(curr_state)
            )

            # --- (2) 실행 가능한 서브태스크가 없다면 => '대기(Wait)' 로직 ---
            if not feasible_subs:
                if not_yet_feasible_subs:
                    # 각 서브태스크별 earliest_time만 뽑아서 최솟값 찾기
                    next_start_constraints = min(
                        not_yet_feasible_subs, key=lambda x: x[1]
                    )
                    next_start_time = next_start_constraints[1]
                    wait_time = next_start_time - curr_state.current_time

                    if wait_time > 0:
                        wait_sub = Subtask(
                            task_name=None,
                            name="Wait for" + str(next_start_constraints[0].name),
                            duration=wait_time,
                            repetition=1,
                            type="Wait",
                            execution=None,
                            temporal_constraints=None,
                        )
                        new_completed = curr_state.completed_subtasks + [
                            CompletedEntry(
                                subtask=wait_sub,
                                start_time=curr_state.current_time,
                                end_time=curr_state.current_time + wait_time,
                            )
                        ]
                        # 대기 분량만큼 시간만 업데이트한 새 상태
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
                # 다른 서브태스크가 전혀 없어서 not_yet_feasible_subs도 비었다면 => 확장 불가
                continue

            # --- (3) 실행 가능한 각 서브태스크 확장 ---
            expanded_nodes: List[SimulationNode] = []
            for candidate_sub in feasible_subs:
                # 이동 시간(nav_time) 계산
                nav_time, new_location = self.nav_manager.compute_navigation_time(
                    curr_node, candidate_sub
                )
                copied_sub = copy.deepcopy(candidate_sub)

                # 서브태스크 실제 실행 시간 = subtask.duration + nav_time
                # (주의: subtask.duration 자체를 덮어쓰지 않는 편이 안전)
                exec_time = candidate_sub.duration.interval + nav_time
                start_time = curr_state.current_time
                end_time = start_time + exec_time
                copied_sub.duration.interval = exec_time
                # 비용 계산
                step_cost = self.cost_calculator.calc_heuristic_cost(
                    curr_node, candidate_sub, nav_time
                )
                new_cost = curr_heuristic + step_cost

                # 완료 정보 업데이트
                completed_entry = CompletedEntry(
                    subtask=copied_sub,
                    start_time=start_time,
                    end_time=end_time,
                )
                new_completed = curr_state.completed_subtasks + [completed_entry]
                new_remaining = [
                    r
                    for r in curr_state.remaining_subtasks
                    if r.name != candidate_sub.name
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
                expanded_nodes.append(new_node)

            # --- (4) Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
            for i, nd in enumerate(expanded_nodes):
                if i < self.beam_width:
                    queue.put(nd)
                else:
                    break

        # --- (5) 모두 확장 완료 후, best_solutions에서 비용 최소 해를 선정 ---
        if not best_solutions:
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
        best_node = best_solutions[0]  # 최소 비용 해
        return best_node.state

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> SchedulerState:
        # 부모 노드에 있던 subtask 이름 집합
        parent_completed_set = {
            ce.subtask.name for ce in parent_state.completed_subtasks
        }
        # 자식 노드의 completed_subtasks (List[CompletedEntry])
        child_plan = child_state.completed_subtasks

        # 자식 노드에서 새로 추가된 CompletedEntry들(=부모엔 없던 subtask)
        new_entries = [
            ce for ce in child_plan if ce.subtask.name not in parent_completed_set
        ]
        if not new_entries:
            # 새로 추가된 subtask가 없다면, 그냥 child_state 그대로 반환 or 예외 처리
            return child_state

        new_entry = new_entries[0]
        new_subtask = new_entry.subtask

        # 부모 노드의 completed_subtasks에 새 entry 추가
        new_completed_subtasks = parent_state.completed_subtasks + [new_entry]

        # remaining_subtasks에서 이 subtask 제거
        new_remaining_subtasks = [
            r for r in parent_state.remaining_subtasks if r.name != new_subtask.name
        ]

        # 이제 새 SchedulerState 생성
        return SchedulerState(
            subtask=new_subtask,  # 새로 완료된 subtask
            completed_subtasks=new_completed_subtasks,
            remaining_subtasks=new_remaining_subtasks,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )
