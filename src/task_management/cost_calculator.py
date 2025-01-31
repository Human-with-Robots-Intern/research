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
        cost_val = factor * (subtask.duration.interval + time_diff + navigate_time)
        return cost_val
