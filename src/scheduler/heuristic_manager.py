import math

from core.task import Subtask
from scheduler.dataclass import Candidate, SimulationNode, TimeSlot
from utils.constants import SIMULATION_DEPTH
from utils.util import create_module_logger

log = create_module_logger(__name__)


class HeuristicManager:
    """
    - Subtask (wait, monitoring 포함) 실행 시 발생하는 휴리스틱 비용 계산
    """

    def __init__(self, constraint_handler):
        self.constraint_handler = constraint_handler
        self.cost_weight = SIMULATION_DEPTH

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> float:
        """
        기존 코드의 휴리스틱 공식:
          cost_val = (cost_weight - current_depth) * (
        subtask.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
        """

        # * (1) 이전 실행에 가까울수록 높은 우선 순위를 부여
        factor = -math.exp(max(self.cost_weight - current_node.depth, 1))

        # * (2) 시간 휴리스틱
        # Dependency를 끝내는 작업은 느리게 시작해야 됨
        in_time_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, current_node.state.constraints, "in"
        )

        out_time_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, current_node.state.constraints, "out"
        )

        # * (3) 시간 슬롯 중 가장 큰 시간을 가진 TimeSlot을 찾아서 계산
        in_time_slot = (
            max(
                list(filter(lambda x: x.is_critical, in_time_slots)),
                key=lambda x: x.interval,
            )
            if list(filter(lambda x: x.is_critical, in_time_slots))
            else TimeSlot(interval=0, is_critical=False, related_subtask_name=None)
        )
        out_time_slot = max(out_time_slots, key=lambda x: x.interval)

        # ! DO NOT FIX THIS HEURISTIC FORMULA
        time_diff = out_time_slot.interval - in_time_slot.interval
        base_heuristic = factor * (
            candidate.subtask.duration.interval + math.exp(time_diff)
        )

        return base_heuristic
