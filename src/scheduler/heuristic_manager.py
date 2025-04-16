import math

from core.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config.constants import ESTIMATE_FILE_NAME, KNOWLEDGE_PATH, LARGE_NUMBER
from src.utils.io_utils.file_io import load_file

log = create_module_logger(__name__, module_log=True)


class HeuristicManager:
    """
    Multi-criteria heuristic example:
      cost = alpha * distance
            + beta * (-1/(slack+1))
            + gamma * sqrt(variance)

    (slack이 작을수록 cost가 더 작아짐 => 우선순위↑)
    """

    def __init__(self, constraint_handler, action_handler):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.knowledge = load_file(KNOWLEDGE_PATH / ESTIMATE_FILE_NAME, "json")

        self.alpha = 1.0  # distance weight
        self.beta = 1.0  # slack weight
        self.gamma = 1.0  # variance weight

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> float:
        """
        time-critical(=slack 작은) => cost 작게
        distance 크면 => cost 커짐
        variance 크면 => cost 커짐
        => smallest cost = highest priority in min-heap
        """

        # -------------------------------
        # (A) distance 계산
        # -------------------------------
        # 1) 로봇 현재 위치
        nav_to_target_action = candidate.subtask.execution.primitive_actions[0]

        nav_time = self.action_handler.get_actions_info(
            current_node, [nav_to_target_action]
        ).action_duration

        log.debug(f"nav_duration: {nav_time}")

        # -------------------------------
        # (B) slack 계산
        # -------------------------------
        # deadline - (earliest_start_time + duration)
        # => slack 작으면 => slackTerm = -1/(slack+1) "더 음수" => total cost "더 작음" => 우선순위↑
        # 2) slack
        #  -> "deadline" 필드는 "critical subtask start time"으로 간주
        slack_val = None
        log.debug(f"subtask: {candidate.subtask.name}, deadline: {candidate.deadline}")
        if candidate.deadline.due_date and candidate.deadline.due_date < float("inf"):
            sub_duration = self.action_handler.get_actions_info(
                current_node, candidate.subtask.execution.primitive_actions
            ).action_duration
            slack_val = candidate.deadline.due_date - (
                candidate.earliest_start_time + sub_duration
            )
        # slackTerm: slack이 작을수록 cost가 더 작아지도록 음수값
        slack_term = 0.0
        if slack_val is not None:
            if slack_val <= 0:
                # 이미 임박/초과 -> 큰 cost로 처리 (or 9999999)
                return LARGE_NUMBER
            else:
                # slack이 남아 있는 경우
                slack_term = -1.0 / (slack_val + 1.0)

        # -------------------------------
        # (C) variance
        # -------------------------------
        # 베이지안 추정 분산
        sub_info = self.knowledge.get(candidate.subtask.name, {})
        variance_val = sub_info.get("variance", 0.0)
        var_cost = math.sqrt(variance_val)

        # -------------------------------
        # (D) Weighted sum
        # -------------------------------
        cost = self.alpha * nav_time + self.beta * slack_term + self.gamma * var_cost

        return cost
