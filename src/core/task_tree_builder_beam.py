import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.task import Subtask
from task_management import ConstraintHandler, CostCalculator, NavigationManager
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.dataclass import CompletedEntry, SchedulerState, SimulationNode, TimeSlot
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class Scheduler:
    """
    Beam Search (lookahead depth=N)로 Subtask 스케줄링하는 예시 코드.
    복잡한 로직(기다림, leftover_manager 등)은 제거하고,
    SimulationState를 일관성 있게 사용하도록 정리.
    """

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

    def extract_state(
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

        # 가장 최근(마지막) CompletedEntry 하나만 선택 or 여러개?
        # 여기서는 하나만 있다고 가정
        new_entry = new_entries[
            0
        ]  # CompletedEntry(subtask=..., start_time=..., end_time=...)
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

        # candidate_subtask의 out-edge 중 최소 interval만 사용
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

        return self.extract_state(parent_state, child_node.state)

    # ------------------------------------------------
    #   1) Time Slot 기반 간단 탐색
    # ------------------------------------------------
    def _simulate_time_slot(
        self,
        current_state: SchedulerState,
        temporal_constraint: TimeSlot,
    ) -> Optional[SimulationNode]:
        """
        separation_interval(temporal_constraint.interval) 시간 동안
        실행할 수 있는 Subtask들을 우선순위 큐로 탐색.
        (예: 'Critical'이면 꼭 이 시간 안에 끝내야 한다, 등)
        """

        queue = PriorityQueue()
        # 초기 노드
        queue.put(
            SimulationNode(
                heuristic_cost=0.0,
                depth=0,
                leftover=0.0,
                tie_breaker=next(self._counter),
                state=current_state,  # state는 SchedulerState
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
            curr_elapsed_time = curr_node.leftover

            # "현재 시점" 가져오기
            curr_state = curr_node.state
            leftover = separation_interval - curr_elapsed_time

            if curr_depth >= self.simulation_depth:
                # 탐색 제한
                collected_solutions.append(curr_node)
                continue

            # 현재 상태에서 실행 가능한 subtask들
            expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_node
            )
            if not expandable_subtasks:
                # 더 이상 확장 불가
                collected_solutions.append(curr_node)
                continue

            filtered_expandable_subtasks = []
            # Critical/Non-Critical leftover 조건 걸러내기
            for sub in expandable_subtasks:
                if sub.name == related_subtask_name:
                    # critical -> leftover == 0
                    if is_critical and leftover != 0:
                        continue
                    # non-critical -> leftover <= 0
                    if (not is_critical) and leftover > 0:
                        continue
                filtered_expandable_subtasks.append(sub)

            is_expanded_curr_step = False

            for sub in filtered_expandable_subtasks:
                nav_time, agent_location = self.nav_manager.compute_navigation_time(
                    curr_node, sub
                )

                copied_sub = copy.deepcopy(sub)
                copied_sub.duration.interval += nav_time

                # 실행 시간
                sub_start_time = curr_state.current_time

                sub_end_time = sub_start_time + copied_sub.duration.interval
                # 새 CompletedEntry
                new_completed_entry = CompletedEntry(
                    subtask=copied_sub,
                    start_time=sub_start_time,
                    end_time=sub_end_time,
                )

                # separation_interval 내에 실행 불가(critical 한정) 체크
                if (
                    copied_sub.duration.interval > leftover
                    and leftover > 0
                    and is_critical
                ):
                    continue

                # 비용 계산
                new_heuristic = self.cost_calculator.calc_heuristic_cost(
                    curr_node, sub, nav_time
                )
                new_heuristic_cost = curr_heuristic_cost + new_heuristic

                new_depth = curr_depth + 1
                new_elapsed_time = curr_elapsed_time + copied_sub.duration.interval

                # completed_subtasks 갱신 (Subtask 객체 자체에는 시간 안 넣음)
                new_completed_entry = CompletedEntry(
                    subtask=copied_sub,
                    start_time=sub_start_time,
                    end_time=sub_end_time,
                )
                updated_completed = curr_state.completed_subtasks + [
                    new_completed_entry
                ]

                # remaining_subtasks에서 이번에 쓴 sub 빼기
                new_remain_subtasks = [
                    r for r in curr_state.remaining_subtasks if r.name != sub.name
                ]

                # 새 SchedulerState
                new_scheduler_state = SchedulerState(
                    subtask=copied_sub,
                    completed_subtasks=updated_completed,
                    remaining_subtasks=new_remain_subtasks,
                    agent_location=agent_location,
                    current_time=sub_end_time,  # 현재 시간 = sub_end_time
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        leftover=new_elapsed_time,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )
                is_expanded_curr_step = True

            # 만약 leftover > 0 & critical 이거나, 아무것도 확장 못 했다면 "Wait Subtask" 추가
            if (leftover > 0 and is_critical) or not is_expanded_curr_step:
                wait_sub = Subtask(
                    task_name=None,
                    name=f"Wait for {related_subtask_name}",
                    duration=leftover,
                    repetition=1,
                    type="Wait",
                    execution=None,
                    temporal_constraints=None,
                )

                new_heuristic_cost = curr_heuristic_cost + leftover
                new_elapsed_time = curr_elapsed_time + leftover
                new_depth = curr_depth + 1

                # Wait subtask 의 start/end 계산
                wait_start_time = curr_state.current_time
                wait_end_time = wait_start_time + leftover

                wait_entry = CompletedEntry(
                    subtask=wait_sub,
                    start_time=wait_start_time,
                    end_time=wait_end_time,
                )
                new_completed_subtasks = curr_state.completed_subtasks + [wait_entry]

                new_scheduler_state = SchedulerState(
                    subtask=wait_sub,
                    completed_subtasks=new_completed_subtasks,
                    remaining_subtasks=curr_state.remaining_subtasks,  # 대기만 했으니 남은거 그대로
                    agent_location=curr_state.agent_location,
                    current_time=wait_end_time,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        leftover=new_elapsed_time,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )

        if not collected_solutions:
            return None

        # 비용 기준 내림차순 정렬 -> 첫 번째를 best
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
                leftover=0.0,
                tie_breaker=next(self._counter),
                state=init_state,
            )
        )

        collected_solutions: List[SimulationNode] = []

        while not queue.empty():
            curr_node = queue.get()

            curr_state = curr_node.state
            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_elapsed_time = curr_node.leftover

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
                # 실행 시간 계산
                sub_start_time = curr_state.current_time
                sub_end_time = sub_start_time + sub.duration.interval + nav_time

                new_heuristic = self.cost_calculator.calc_heuristic_cost(
                    curr_node, sub, nav_time
                )
                copied_sub = copy.deepcopy(sub)
                copied_sub.duration.interval += nav_time

                # 새 CompletedEntry
                new_completed_entry = CompletedEntry(
                    subtask=copied_sub,
                    start_time=sub_start_time,
                    end_time=sub_end_time,
                )

                new_heuristic += curr_heuristic
                new_depth = curr_depth + 1
                new_elapsed_time = curr_elapsed_time + copied_sub.duration.interval
                updated_completed = curr_node.state.completed_subtasks + [
                    new_completed_entry
                ]
                updated_remain = [
                    r
                    for r in curr_node.state.remaining_subtasks
                    if r.name != copied_sub.name
                ]

                new_scheduler_state = SchedulerState(
                    copied_sub,
                    updated_completed,
                    updated_remain,
                    sub_end_time,
                    agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic,
                        depth=new_depth,
                        leftover=new_elapsed_time,
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
