# cost_calculator.py
from typing import Any, Tuple

from core.task import Subtask

COST_WEIGHT = 3


class CostCalculator:
    """
    - Subtask 실행 시 발생하는 휴리스틱 비용 계산
    - Wait 시 발생하는 비용 계산
    """

    def __init__(self, constraint_handler):
        self.constraint_handler = constraint_handler
        self.cost_weight = COST_WEIGHT

    def calc_heuristic_cost(
        self,
        current_node: Any,
        subtask: Subtask,
        navigate_time: float,
    ) -> float:
        """
        기존 코드의 휴리스틱 공식:
          cost_val = (cost_weight - current_depth) * (
        subtask.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
        """
        in_time_slot = self.constraint_handler.get_temporal_constraints(
            subtask.name, "in"
        )
        out_time_slot = self.constraint_handler.get_temporal_constraints(
            subtask.name, "out"
        )
        time_diff = out_time_slot.interval - in_time_slot.interval

        factor = max(self.cost_weight - current_node.depth, 1)
        cost_val = factor * (subtask.duration.interval + navigate_time + time_diff)
        return cost_val

    def calc_wait_cost(self, current_depth: int, wait_subtask: Subtask) -> float:
        """
        Wait 노드 비용 계산.
        (원 코드에서는 단순히 wait_subtask.duration 사용.
         필요하다면 (cost_weight - depth) * duration 등으로 커스터마이징 가능)
        """
        return wait_subtask.duration
