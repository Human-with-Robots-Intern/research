# cost_calculator.py
from typing import Tuple

from core.task import Subtask
from task_management.rule import ConstraintHandler

# 전역 상수를 그대로 사용할 수도 있지만,
# 필요하다면 CostCalculator 내부 인자로 넘길 수 있습니다.
COST_WEIGHT = 3


class CostCalculator:
    """
    - Subtask 실행 시 발생하는 휴리스틱 비용 계산
    - Wait 시 발생하는 비용 계산
    """

    def __init__(
        self, constraint_handler: ConstraintHandler, cost_weight: int = COST_WEIGHT
    ):
        self.constraint_handler = constraint_handler
        self.cost_weight = cost_weight

    def calc_heuristic_cost(
        self,
        current_depth: int,
        subtask: Subtask,
        navigate_time: float,
        incoming_ts: Tuple[int, bool, str],
        outgoing_ts: Tuple[int, bool, str],
    ) -> float:
        """
        기존 코드의 휴리스틱 공식:
          cost_val = (cost_weight - current_depth) * (
              subtask.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
          )
        """
        in_separation, _, _ = incoming_ts
        out_separation, _, _ = outgoing_ts
        time_diff = in_separation - out_separation

        factor = max(self.cost_weight - current_depth, 1)  # -1 곱할 것 그리고 최대 찾기
        cost_val = factor * (subtask.duration.interval + navigate_time + time_diff)
        return cost_val

    def calc_wait_cost(self, current_depth: int, wait_subtask: Subtask) -> float:
        """
        Wait 노드 비용 계산.
        (원 코드에서는 단순히 wait_subtask.duration 사용.
         필요하다면 (cost_weight - depth) * duration 등으로 커스터마이징 가능)
        """
        return wait_subtask.duration
