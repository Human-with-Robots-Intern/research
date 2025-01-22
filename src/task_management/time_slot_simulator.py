# leftover_manager.py

import copy
from queue import PriorityQueue
from typing import List, Tuple

from core.task import Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management.rule import ConstraintHandler


class LeftoverManager:
    """
    Non-critical leftover 상황에서,
    leftover 안에 작은 subtasks를 최대한 배치하고,
    leftover를 초과해도 최소 overflow로 최대 subtask를 실행하는 로직 담당.
    """

    def __init__(
        self,
        constraint_handler: ConstraintHandler,
        cost_calculator: CostCalculator,
        navigation_manager: NavigationManager,
        counter,
    ):
        self.constraint_handler = constraint_handler
        self.cost_calculator = cost_calculator
        self.navigation_manager = navigation_manager
        self._counter = counter

    def find_best_combination(
        self,
        curr_state,
        leftover: float,
        curr_cost: float,
        curr_count: int,
    ) -> Tuple[List[Subtask], float, int]:
        """
        PriorityQueue 기반으로 leftover 초과량 최소 + Subtask 개수 최대 조합을 찾는다.

        Return: (best_combination, total_cost_for_combo, total_subtask_count)
        """
        # 우선순위큐: ((overflow, -subtask_count), used_time, chosen_subtasks, remain_subtasks)
        queue_sub = PriorityQueue()

        # 초기 상태
        queue_sub.put(
            ((0, 0), 0.0, next(self._counter), [], curr_state.remaining_subtasks)
        )

        best_overflow = float("inf")
        best_count = 0
        best_combination: List[Subtask] = []

        while not queue_sub.empty():
            (overflow_val, neg_count), used_time, _, chosen_subtasks, remain_subs = (
                queue_sub.get()
            )

            # 갱신
            if (overflow_val < best_overflow) or (
                overflow_val == best_overflow and -neg_count > best_count
            ):
                best_overflow = overflow_val
                best_count = -neg_count
                best_combination = chosen_subtasks[:]

            # 확장
            for sub in remain_subs:
                nav_time = self.navigation_manager.calculate_navigation_time(
                    curr_state.name, curr_state.partial_plan + chosen_subtasks, sub
                )
                dur = sub.duration.interval + nav_time
                new_used_time = used_time + dur
                new_chosen = chosen_subtasks + [sub]
                new_overflow = max(0, new_used_time - leftover)
                new_sub_count = -(len(new_chosen))  # 우선순위 높이려면 음수

                new_remain = [r for r in remain_subs if r != sub]

                queue_sub.put(
                    (
                        (new_overflow, new_sub_count),
                        new_used_time,
                        next(self._counter),
                        new_chosen,
                        new_remain,
                    )
                )

        # best_combination에 대해 실제 소요시간 계산
        total_cost_for_combo = 0.0
        for sub in best_combination:
            nav_time = self.navigation_manager.calculate_navigation_time(
                curr_state.name,
                curr_state.partial_plan + best_combination,  # or chosen?
                sub,
            )
            total_cost_for_combo += sub.duration.interval + nav_time

        total_count = curr_count + len(best_combination)
        return best_combination, total_cost_for_combo, total_count
