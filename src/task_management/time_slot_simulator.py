# time_slot_simulator.py
import heapq
from queue import PriorityQueue
from typing import List, Tuple

from core.task import Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management.rule import ConstraintHandler


class TimeSlotSimulator:
    """
    Time Slot(슬롯) 내에서 여러 Subtask를 배치하는 로직을 전담.
    """

    def __init__(
        self,
        beam_width: int,
        constraint_handler: ConstraintHandler,
        cost_calculator: CostCalculator,
        navigation_manager: NavigationManager,
    ):
        self.beam_width = beam_width
        self.constraint_handler = constraint_handler
        self.cost_calculator = cost_calculator
        self.navigation_manager = navigation_manager

    def simulate_time_slot(
        self,
        total_cost: float,
        current_depth: int,
        current_subtask_name: str,
        partial_plan: List[Subtask],
        remaining_subtasks: List[Subtask],
        separation_interval: int,
        related_subtask_name: str,
    ) -> List[Tuple[int, float, int, List[Subtask], List[Subtask]]]:
        """
        Time Slot 내에서 subtask를 여러 개 배치해볼 수 있는 시나리오를 만든 뒤,
        (subtask_count, final_cost, new_depth, final_plan, remain)을 반환합니다.

        원래 _simulate_time_slot_case 로직을 대부분 이곳에 옮김.
        """
        slot_queue = PriorityQueue()
        # slot_queue 항목: ((-subtask_count, slot_cost), order, leftover, global_cost, plan, remain)
        slot_queue.put(
            (
                (0, 0.0),  # subtask_count=0, slot 내 비용=0
                0,  # tie-breaker order
                separation_interval,
                total_cost,
                partial_plan[:],
                remaining_subtasks[:],
            )
        )

        slot_scenarios = []
        order_counter = 0

        while not slot_queue.empty():
            (
                (neg_count, slot_cost),
                _,
                leftover,
                global_cost,
                plan_so_far,
                remain_so_far,
            ) = slot_queue.get()
            subtask_count = -neg_count

            # 현재 슬롯에서 배치 가능한 subtask 찾기
            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                name=current_subtask_name,
                partial_plan=plan_so_far,
                remaining_subtasks=remain_so_far,
            )

            expandables = []
            for candidate in feasible_subtasks:
                # 해당 슬롯을 트리거한 subtask(related_subtask_name)는 slot 내부에서 배치하지 않음(기존 로직 유지)
                if candidate.name == related_subtask_name:
                    continue

                # 내비게이션 시간
                nav_time = self.navigation_manager.calculate_navigation_time(
                    current_subtask_name, plan_so_far, candidate
                )
                total_dur = candidate.duration.interval + nav_time

                if total_dur <= leftover:
                    expandables.append((candidate, total_dur))

            if expandables:
                # 슬롯 안에 더 배치
                for cand_subtask, actual_dur in expandables:
                    new_global_cost = global_cost + actual_dur  # (기존 로직: 단순 누적)
                    new_leftover = leftover - actual_dur
                    new_plan = plan_so_far + [cand_subtask]
                    new_remain = [
                        r for r in remain_so_far if r.name != cand_subtask.name
                    ]

                    order_counter += 1
                    slot_queue.put(
                        (
                            (-(subtask_count + 1), slot_cost + actual_dur),
                            order_counter,
                            new_leftover,
                            new_global_cost,
                            new_plan,
                            new_remain,
                        )
                    )
            else:
                # 더 넣을 subtask가 없으면 leftover만큼 Wait 처리
                if leftover > 0:
                    wait_sub = Subtask(
                        task_name=None,
                        name=(
                            f"Wait for {related_subtask_name}"
                            if related_subtask_name
                            else "Idle"
                        ),
                        duration=leftover,
                        repetition=1,
                        type="Wait",
                        execution=None,
                        temporal_constraints=None,
                    )
                    wait_cost_val = self.cost_calculator.calc_wait_cost(
                        current_depth, wait_sub
                    )
                    final_cost = global_cost + wait_cost_val
                    final_plan = plan_so_far + [wait_sub]

                    slot_scenarios.append(
                        (
                            subtask_count,
                            final_cost,
                            current_depth + 1,
                            final_plan,
                            remain_so_far,
                        )
                    )
                else:
                    # leftover == 0
                    slot_scenarios.append(
                        (
                            subtask_count,
                            global_cost,
                            current_depth + 1,
                            plan_so_far,
                            remain_so_far,
                        )
                    )

            # 슬롯 내부에서도 beam 폭 제한
            if slot_queue.qsize() > (self.beam_width * 20):
                temp_list = []
                while not slot_queue.empty():
                    temp_list.append(slot_queue.get())
                temp_list.sort(key=lambda x: x[0])  # (-(count), slot_cost) 기준
                for item in temp_list[: self.beam_width * 10]:
                    slot_queue.put(item)

        # (subtask_count 내림차순, cost 오름차순)으로 정렬
        slot_scenarios.sort(key=lambda x: (-x[0], x[1]))
        return slot_scenarios[: self.beam_width]
