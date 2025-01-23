import copy
import itertools
from queue import PriorityQueue
from typing import List, NamedTuple, Optional, Tuple

import networkx as nx
from anytree import Node

from core.task import SchedulerState, Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management.rule import ConstraintHandler
from task_management.task_tree import TaskTree
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.task_io import load_navigation_times
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class PQItem(NamedTuple):
    """
    PriorityQueue에 들어가는 아이템(스케줄 탐색 노드).
    """

    heuristic_cost: float  # 누적 비용(오름차순 정렬 기준 1)
    depth: int  # 현재 탐색 깊이(lookahead용)
    leftover: float  # time_slot에서 남은 시간 (일반 케이스는 0.0)
    tie_breaker: int  # 동일 우선순위 시 순서 결정 (itertools.count() 사용)
    state: "SchedulerState"  # 스케줄링/시뮬레이션 상태 (current_state)


class Scheduler:
    """
    Beam Search(lookahead depth=3)로 Subtask를 확정해 나가는 로직.
    """

    def __init__(
        self,
        init_subtasks: List[Subtask],
        init_constraints: nx.DiGraph,
    ):
        self.tree = TaskTree()
        self.beam_width = DEFAULT_BEAM_WIDTH
        self.simulation_depth = DEFAULT_SIMULATION_DEPTH

        # 핸들러
        self.subtasks_info = copy.deepcopy(init_subtasks)
        self.constraint_handler = ConstraintHandler(init_constraints)

        # 부품 모듈들
        self.cost_calculator = CostCalculator()
        self.nav_manager = NavigationManager(
            navigation_times=load_navigation_times(),
            all_subtasks_info=self.subtasks_info,
        )

        self._counter = itertools.count()  # tie-breaker for PriorityQueue ordering

    def get_new_state(
        self,
        current_state: SchedulerState,
        current_constraints: nx.graph,
    ) -> Node:
        """3-depth lookahead로 Subtask를 확정해 나가는 로직.

        Args:
            tasks (List[Subtask]): _description_
            constraints (nx.graph): _description_

        Returns:
            Subtask
        """
        self.constraint_handler.update_constraints(current_constraints)

        separation_interval, _, _ = self.constraint_handler.get_temporal_constraints(
            current_state.subtask.name, direction="out"
        )

        if separation_interval > 0:
            next_subtask = self._simulate_time_slot(current_state)
        else:
            next_subtask = self._simulate_lookahead(current_state)

        # 다음에 올 subtask 내부에 있는 navigation time을 계산
        # "Navigate to"를 기준으로 판단할 것
        nav_time = self.nav_manager.calc_time(current_state, next_subtask)
        new_remaining = [
            s for s in current_state.remaining_subtasks if s.name != next_subtask.name
        ]
        new_plan = current_state.completed_subtasks + [next_subtask]

        return SchedulerState(next_subtask.name, new_plan, new_remaining)

    # ------------------------------------------------
    #   Lookahead (depth=simulation_depth)
    # ------------------------------------------------
    def _simulate_time_slot(self, current_state: SchedulerState):
        """
        init_state 부터 time_slot 채울 때까지 확장.
        PriorityQueue 를 사용하여 cost 오름차순으로 탐색.

        Returns:
            List of tuples:
                (total_cost, count, last_subtask, remaining_subtasks, partial_plan)
        """
        separation_interval, is_critical, related_subtask = (
            self.constraint_handler.get_temporal_constraints(
                current_state.subtask, direction="out"
            )
        )

        queue = PriorityQueue()
        # total_cost, count, order, state
        queue.put(
            PQItem(
                heuristic_cost=0.0,
                depth=0,
                leftover=separation_interval,
                tie_breaker=next(self._counter),
                state=current_state,
            )
        )

        results: List[
            Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]
        ] = []

        while not queue.empty():
            curr_cost, curr_count, _, curr_state = queue.get()
            leftover = separation_interval - curr_cost

            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_state
            )
            expandable_subtasks = []

            # 1) leftover 안에 들어갈 수 있는 subtask 목록 탐색
            for feasible_subtask in feasible_subtasks:
                if feasible_subtask.name == related_subtask:
                    continue

                # Calculate navigation time (from current_subtask_name to candidate)
                nav_time = self.nav_manager.calc_time(
                    curr_state.name, current_state.completed_subtasks, feasible_subtask
                )
                return_nav_time = self.nav_manager.calc_time(
                    curr_state.name, current_state.completed_subtasks, related_subtask
                )
                total_dur = feasible_subtask.duration.interval + nav_time
                if is_critical:
                    total_dur += return_nav_time

                # leftover 안에 들어가는지 체크
                if total_dur <= leftover:
                    expandable_subtasks.append((feasible_subtask, total_dur))

            if expandable_subtasks:
                # 2) 더 들어갈 수 있는 subtask가 있으면 확장
                for candidate_subtask, actual_dur in expandable_subtasks:
                    new_cost = curr_cost + actual_dur
                    new_count = curr_count + 1
                    new_plan = curr_state.partial_plan + [candidate_subtask]
                    new_remain = [
                        r
                        for r in curr_state.remaining_subtasks
                        if r.name != candidate_subtask.name
                    ]
                    new_state = SchedulerState(
                        candidate_subtask.name, new_plan, new_remain
                    )

                    queue.put((new_cost, new_count, next(self._counter), new_state))
            else:
                # 3) leftover가 남아 있는지?
                if leftover > 0:
                    # is_critical이면, 남은 시간을 기다리는 Subtask (Wait for related_subtask) 추가
                    # leftover를 그냥 '기다리는 시간'으로 소비
                    if is_critical:
                        wait_sub = Subtask(
                            task_name=None,
                            name=(
                                f"Wait for {related_subtask}"
                                if related_subtask
                                else "Idle"
                            ),
                            duration=leftover,
                            repetition=1,
                            type="Monitor",
                            execution=None,
                            temporal_constraints=None,
                        )
                        new_cost = curr_cost + leftover  # 남은 시간을 대기하는 것이므로
                        new_count = curr_count + 1

                        new_plan = curr_state.partial_plan + [wait_sub]
                        new_remain = (
                            curr_state.remaining_subtasks
                        )  # Wait는 새로운 subtask가 아니므로 remain 그대로

                        new_state = SchedulerState(wait_sub.name, new_plan, new_remain)

                        results.append(
                            (
                                new_cost,
                                new_count,
                                new_state.subtask,
                                new_state.remaining_subtasks,
                                new_state.completed_subtasks,
                            )
                        )
                    else:
                        # is_critical이 아닌 경우
                        # leftover란, 그저 related subtask가 시작할 수 있는 시간까지 남은 시간임
                        # 위의 로직에서 leftover에 들어갈 수 있는 작은 subtask들을 대부분 찾았음.
                        # 잔여 leftover 동안 가장 많은 subtask를 실행 할 수 있는 subtask 조합을 찾으면 됨
                        # subtask들의 합이 leftover를 초과하는 것도 가능하되, 최소한으로 넘치게 채워야 함.

                        if current_state.remaining_subtasks:
                            best_combination, combo_cost, combo_count = (
                                self.leftover_manager.find_best_combination(
                                    curr_state=current_state,
                                    leftover=leftover,
                                    curr_cost=curr_cost,
                                    curr_count=curr_count,
                                )
                            )
                            if best_combination:
                                new_cost = curr_cost + combo_cost
                                new_count = combo_count
                                new_plan = (
                                    current_state.completed_subtasks + best_combination
                                )
                                new_remain = [
                                    r
                                    for r in current_state.remaining_subtasks
                                    if r not in best_combination
                                ]
                                new_state = SchedulerState(
                                    best_combination[-1].name, new_plan, new_remain
                                )

                                queue.put(
                                    (
                                        new_cost,
                                        new_count,
                                        next(self._counter),
                                        new_state,
                                    )
                                )
                        else:
                            results.append(
                                (
                                    curr_cost,
                                    curr_count,
                                    curr_state.name,
                                    curr_state.remaining_subtasks,
                                    curr_state.partial_plan,
                                )
                            )

                else:
                    results.append(
                        (
                            curr_cost,
                            curr_count,
                            curr_state.name,
                            curr_state.remaining_subtasks,
                            curr_state.partial_plan,
                        )
                    )

        best_candidates = sorted(results, key=lambda x: (x[0], -x[1]))[
            : self.beam_width
        ]
        # 그 중 best 1개만 리턴
        if not best_candidates:
            return None  # or some default
        best_path = best_candidates[0]  # (cost, count, last_subtask, remain, plan)
        return best_path  # cost ascending, count descending

    def _simulate_lookahead(
        self, init_state: SchedulerState
    ) -> List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]]:
        """
        init_state 부터 depth=simulation_depth까지 확장.
        PriorityQueue 를 사용하여 cost 오름차순으로 탐색.

        Returns:
            List of tuples:
                (total_cost, depth, last_subtask, remaining_subtasks, partial_plan)
        """
        queue = PriorityQueue()
        # total_cost, depth, order, state; depth가 3이고, total cost가 최소인 것을 가장 앞에 두는 자료구조
        queue.put(
            PQItem(
                heuristic_cost=0.0,
                depth=0,
                leftover=0.0,  # 사용 안 함
                tie_breaker=next(self._counter),
                state=init_state,
            )
        )

        results: List[
            Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]
        ] = []

        while not queue.empty():
            curr_cost, curr_depth, _, curr_state = queue.get()

            # depth 제한에 도달 -> 결과로 바로 저장
            if curr_depth >= self.simulation_depth:
                last_subtask = (
                    curr_state.partial_plan[-1] if curr_state.partial_plan else None
                )
                results.append(
                    (
                        curr_cost,
                        curr_depth,
                        last_subtask,
                        curr_state.remaining_subtasks,
                        curr_state.partial_plan,
                    )
                )
                continue

            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_state
            )
            for feasible_subtask in feasible_subtasks:
                cost_val, updated_remain = self._expand_subtask(
                    total_cost=curr_cost,
                    current_depth=curr_depth,
                    current_state=curr_state,
                    candidate_subtask=feasible_subtask,
                )
                new_cost = curr_cost + cost_val
                new_depth = curr_depth + 1
                new_plan = curr_state.partial_plan + [feasible_subtask]

                if new_depth < self.simulation_depth:
                    new_state = SchedulerState(
                        feasible_subtask.name, new_plan, updated_remain
                    )
                    queue.put((new_cost, new_depth, next(self._counter), new_state))
                else:
                    results.append(
                        (
                            new_cost,
                            new_depth,
                            feasible_subtask,
                            updated_remain,
                            new_plan,
                        )
                    )
        if not results:
            log.warning("No valid paths found. Stopping expansion.")

        # 2) 후보들을 cost 오름차순 정렬 -> 상위 1개 선택
        best_path, _ = self._prune_simulated_paths(results)
        if not best_path:
            log.warning("All expansions invalid. Stopping.")

        return best_path

    def _expand_subtask(
        self,
        total_cost: float,
        current_depth: int,
        current_state: SchedulerState,
        candidate_subtask: Subtask,
    ) -> Tuple[float, List[Subtask]]:
        """
        Subtask 확장 시 비용 계산(heuristic) 후, remaining_subtasks 갱신.
        """  # TODO 복수의 time constraint handle
        # Get constraints for candidate_subtask
        incoming_ts = self.constraint_handler.get_temporal_constraints(
            candidate_subtask.name, direction="in"
        )
        outgoing_ts = self.constraint_handler.get_temporal_constraints(
            candidate_subtask.name, direction="out"
        )

        # Calculate navigation time
        nav_time = self.nav_manager.calc_time(
            current_state.subtask, current_state.completed_subtasks, candidate_subtask
        )

        # Calculate heuristic cost
        cost_val = self.cost_calculator.calc_heuristic_cost(
            current_depth, candidate_subtask, nav_time, incoming_ts, outgoing_ts
        )

        # Filter out the chosen subtask from remaining
        new_remaining = [
            s
            for s in current_state.remaining_subtasks
            if s.name != candidate_subtask.name
        ]

        return cost_val, new_remaining

    # ------------------------------------------------
    #   BEAM PRUNE
    # ------------------------------------------------
    def _prune_simulated_paths(
        self,
        paths: List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
    ) -> Tuple[
        Optional[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
        List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
    ]:
        """
        (cost, depth, last_subtask, remain, plan)을 cost 기준으로 정렬 후
        beam_width만큼 살리고 그중 최소 cost를 best_path로 선정.
        """
        if not paths:
            return None, []

        sorted_paths = sorted(paths, key=lambda x: x[0])  # cost ascending
        pruned = sorted_paths[: self.beam_width]

        best_path = pruned[0] if pruned else None
        return best_path, pruned
