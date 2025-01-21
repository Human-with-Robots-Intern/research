import heapq
from queue import PriorityQueue
from typing import List, NamedTuple, Tuple

from core.task import Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management.rule import ConstraintHandler


class SimulationState(NamedTuple):
    """
    시뮬레이션 중 임시 상태.
    """

    name: str  # 마지막으로 실행된 Subtask 이름 (또는 "Init")
    partial_plan: List[Subtask]
    remaining_subtasks: List[Subtask]


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
        temporal_constraint: Tuple[int, bool, str],
    ) -> List[Tuple[int, float, int, List[Subtask], List[Subtask]]]:
        """
        Time Slot 내에서 subtask를 여러 개 배치해볼 수 있는 시나리오를 만든 뒤,
        (subtask_count, final_cost, new_depth, final_plan, remain)을 반환합니다.

        - subtask_count: 이 슬롯에서 배치된 서브태스크의 수
        - final_cost: 현재까지의 총 비용 (누적)
        - new_depth: 증가된 깊이
        - final_plan: Time Slot 시뮬레이션 후의 부분 계획
        - remain: Time Slot 시뮬레이션 후 남은 서브태스크들
        """

        slot_queue = PriorityQueue()
        # PriorityQueue stores items of the form:
        # ((-subtask_count, slot_cost), order, leftover, global_cost, plan_so_far, remain_so_far)
        # where:
        #   - subtask_count = number of subtasks already placed into this slot
        #   - slot_cost = local slot cost (if needed; here it’s just an incremental measure)
        #   - leftover = how much time remains in this slot
        #   - global_cost = total accumulated cost so far
        #   - plan_so_far, remain_so_far = current partial plan & remaining subtasks
        separation_interval, is_critical, related_subtask = temporal_constraint
        slot_queue.put(
            (
                (0, 0.0),  # subtask_count=0, slot_cost=0
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

            # 1) Create a local SimulationState and get feasible subtasks
            local_state = SimulationState(
                name=current_subtask_name,
                partial_plan=plan_so_far,
                remaining_subtasks=remain_so_far,
            )

            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                local_state
            )

            # 2) Filter out the subtask that triggered this time slot (related_subtask_name)
            #    because we don't want to place it inside its own slot
            expandables = []
            for candidate in feasible_subtasks:
                if candidate.name == related_subtask:
                    continue

                # Calculate navigation time (from current_subtask_name to candidate)
                nav_time = self.navigation_manager.calculate_navigation_time(
                    current_subtask_name, plan_so_far, candidate
                )
                total_dur = candidate.duration.interval + nav_time

                # If the candidate fits into the leftover time
                if total_dur <= leftover:
                    expandables.append((candidate, total_dur))

            if expandables:
                # 3) We can still place more subtasks inside this slot
                for cand_subtask, actual_dur in expandables:
                    new_global_cost = global_cost + actual_dur  # Simple additive cost
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
                # 4) No more subtasks can be placed -> fill leftover with a Wait subtask
                if leftover > 0:
                    wait_sub = Subtask(
                        task_name=None,
                        name=(
                            f"Wait for {related_subtask}" if related_subtask else "Idle"
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
                    # TODO cost를 계산하는데 global cost는 heuristic cost임.
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
                    # leftover == 0 -> no waiting needed
                    slot_scenarios.append(
                        (
                            subtask_count,
                            global_cost,
                            current_depth + 1,
                            plan_so_far,
                            remain_so_far,
                        )
                    )

            # 5) Beam constraint inside the slot simulation
            if slot_queue.qsize() > (self.beam_width):
                temp_list = []
                while not slot_queue.empty():
                    temp_list.append(slot_queue.get())
                # Sort primarily by subtask_count (descending), then cost (ascending)
                # Actually, our priority is stored as (-(subtask_count), slot_cost).
                temp_list.sort(key=lambda x: x[0])  # Sort by ((-count, slot_cost), ...)
                # Reinsert only top N
                for item in temp_list[: self.beam_width]:
                    slot_queue.put(item)

        # 6) Sort final scenarios by (subtask_count desc, cost asc)
        slot_scenarios.sort(key=lambda x: (-x[0], x[1]))
        return slot_scenarios[: self.beam_width]
