from __future__ import annotations

import copy
import logging
import math
from typing import TYPE_CHECKING, Optional

import networkx as nx  # Required for path finding
import numpy as np  # 추가 (남은 작업량 추정 등에 사용될 수 있음)

from src.core.dataclass import Candidate, SimulationNode
from src.utils.config import (
    ALPHA_HEURISTIC,
    BETA_HEURISTIC,
    EPSILON,
    GAMMA_HEURISTIC,
    INIT_PRIOR_MEAN,
    LARGE_NUMBER,
)

# Forward declarations for type hinting
if TYPE_CHECKING:
    from src.core.agent import Agent
    from src.core.task import Subtask  # Subtask 직접 임포트
    from src.scheduler.action_handler import ActionHandler
    from src.scheduler.constraint_handler import ConstraintHandler

log = logging.getLogger(__name__)


class HeuristicManager:
    """
    개선된 다중 기준 휴리스틱 (3개 파라미터, 절쩩안):
      비용 = alpha * 네비게이션_비용 (nav_time)
            + beta * 긴급도_비용 (수정된 slack_term)
            + zeta * 남은_작업_비용 (개수와 총 예상 시간의 가중 합)

    비용이 낮을수록 우선순위가 높습니다.
    """

    def __init__(
        self,
        constraint_handler: "ConstraintHandler",
        action_handler: "ActionHandler",
        agent: Optional["Agent"] = None,  # Inject Agent dependency
    ):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.agent = agent

        self.alpha = ALPHA_HEURISTIC
        self.beta = BETA_HEURISTIC
        self.gamma = GAMMA_HEURISTIC

    def _get_estimated_duration(self, subtask: Subtask) -> float:
        """Subtask의 예상 소요 시간을 반환합니다."""
        # TODO: Agent의 지식이나 경험을 바탕으로 더 정확한 추정치 제공
        log.warning(
            f"Using default duration estimate ({INIT_PRIOR_MEAN}) for subtask '{subtask.name}'. Implement agent-specific estimation."
        )
        return INIT_PRIOR_MEAN  # Placeholder

    def _calculate_navigation_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """후보 Subtask의 첫 번째 액션(주로 네비게이션) 비용(시간)을 계산합니다."""
        nav_action = candidate.subtask.execution.primitive_actions[0]
        # 네비게이션 외 다른 액션이 첫번째일 경우 처리 필요
        if not nav_action.startswith("NAVIGATE_TO"):
            log.warning(
                f"First action for candidate '{candidate.subtask.name}' is not NAVIGATE_TO: {nav_action}. Treating navigation cost as 0."
            )
            return 0.0  # 또는 다른 방식으로 처리

        sim_result = self.action_handler.get_actions_info(current_node, [nav_action])
        nav_time = sim_result.action_duration
        log.debug(f"  Navigation Cost (nav_time): {nav_time:.2f}")
        return nav_time

    def _calculate_urgency_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> tuple[float, float]:
        """
        긴급도 비용과 계산에 사용된 slack 값을 반환합니다.
        긴급도 비용은 deadline이 있는 경우 slack 값에 반비례합니다.
        """
        if not (
            candidate.deadline.due_date and candidate.deadline.due_date < float("inf")
        ):
            log.debug("  No finite deadline. Urgency Cost: 0.0, Slack: inf")
            return 0.0, float("inf")  # 긴급도 비용 0, 슬랙 무한대

        current_time = current_node.state.current_time
        deadline_time = candidate.deadline.due_date
        deadline_reason = candidate.deadline.subtask_name
        log.debug(
            f"  Deadline detected: {deadline_time:.2f} (due to '{deadline_reason}')"
        )

        # 1. 후보 태스크 실행 시간 추정
        candidate_sim_result = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )
        candidate_sim_duration = candidate_sim_result.action_duration
        candidate_done_agent_pos = candidate_sim_result.scene_positions["agent"]

        # 2. 후보 태스크 완료 후 데드라인 태스크 시작 위치까지 이동 시간 추정
        nav_to_deadline_duration = 0.0
        deadline_subtask = next(
            (
                st
                for st in current_node.state.remaining_subtasks
                if st.name == deadline_reason
            ),
            None,
        )
        if deadline_subtask:
            deadline_first_action = deadline_subtask.execution.primitive_actions[0]
            if deadline_first_action.startswith("NAVIGATE_TO"):
                # 후보 완료 위치에서 데드라인 태스크 시작 위치까지 네비게이션 시뮬레이션
                dummy_node = copy.deepcopy(current_node)
                dummy_node.state.agent_location = candidate_done_agent_pos
                nav_sim_result = self.action_handler.get_actions_info(
                    dummy_node, [deadline_first_action]
                )
                nav_to_deadline_duration = nav_sim_result.action_duration
        else:
            log.warning(
                f"Deadline reason subtask '{deadline_reason}' not found in remaining tasks."
            )

        # 3. Slack 계산
        time_needed = candidate_sim_duration + nav_to_deadline_duration
        time_remaining_until_deadline = deadline_time - current_time
        slack_val = time_remaining_until_deadline - time_needed

        log.debug(
            f"  Slack Calc: Deadline={deadline_time:.2f}, Current={current_time:.2f}, Remaining={time_remaining_until_deadline:.2f}"
        )
        log.debug(
            f"    Time Needed = EstDurCand({candidate_sim_duration:.2f}) + EstDurIntermed({nav_to_deadline_duration:.2f}) = {time_needed:.2f}"
        )
        log.debug(
            f"    Calculated Slack = {time_remaining_until_deadline:.2f} - {time_needed:.2f} = {slack_val:.2f}"
        )

        # 4. 긴급도 비용 계산
        urgency_cost = 0.0
        if slack_val <= EPSILON:
            log.warning(
                f"  Urgency Alert for '{candidate.subtask.name}': Slack is {slack_val:.2f} (<= {EPSILON}). Assigning very high urgency cost."
            )
            urgency_cost = self.beta * LARGE_NUMBER
        else:
            urgency_term = 1.0 / (slack_val + EPSILON)  # 0 나누기 방지
            urgency_cost = self.beta * urgency_term
            log.debug(
                f"  Calculated urgency term: {urgency_term:.3f}, Urgency Cost (beta={self.beta:.2f}): {urgency_cost:.3f}"
            )

        return urgency_cost, slack_val

    def _calculate_remaining_work_cost(
        self, remaining_subtasks: list[Subtask], current_constraints: nx.DiGraph
    ) -> float:
        """남은 Subtask들의 예상 비용(총 소요 시간 등)을 추정합니다."""
        if not remaining_subtasks:
            return 0.0

        total_estimated_duration = sum(
            self._get_estimated_duration(sub) for sub in remaining_subtasks
        )

        # TODO: 제약 조건(예: critical path)을 고려하여 개선
        # remaining_cost = total_estimated_duration + weight * len(remaining_subtasks)

        log.debug(
            f"  Remaining Work Cost (sum of est. durations): {total_estimated_duration:.2f} for {len(remaining_subtasks)} tasks."
        )
        return total_estimated_duration

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
        log.debug(f"Calculating heuristic for candidate: {candidate.subtask.name}")

        # 1. 네비게이션 비용 계산
        navigation_cost = self._calculate_navigation_cost(current_node, candidate)

        # 2. 긴급도 비용 계산
        urgency_cost, slack_val = self._calculate_urgency_cost(current_node, candidate)

        # 3. 남은 작업 비용 계산
        # 주의: 현재 상태의 남은 작업을 사용해야 함 (후보 실행 후가 아님)
        remaining_work_cost = self._calculate_remaining_work_cost(
            current_node.state.remaining_subtasks, current_node.state.constraints
        )

        # 4. 가중 합 계산
        total_cost = (
            self.alpha * navigation_cost
            + self.beta * urgency_cost
            + self.gamma * remaining_work_cost
        )

        log.debug(
            f"  Heuristic Costs for '{candidate.subtask.name}': Nav={navigation_cost:.3f}, Urg={urgency_cost:.3f} (Slack={slack_val:.2f}), Rem={remaining_work_cost:.3f}"
        )
        log.debug(
            f"  Total Weighted Cost: {total_cost:.4f} (alpha={self.alpha:.2f}, beta={self.beta:.2f}, gamma={self.gamma:.2f})"
        )

        # 5. 실행 불가능하거나 매우 높은 비용 처리
        if (
            navigation_cost >= LARGE_NUMBER
            or urgency_cost
            >= LARGE_NUMBER  # urgency_cost가 beta * LARGE_NUMBER가 될 수 있음
            # total_cost 자체도 확인 (overflow 등 예방)
            or total_cost >= LARGE_NUMBER
        ):
            log.warning(
                f"Returning LARGE_NUMBER cost for '{candidate.subtask.name}' due to infeasible navigation (est={navigation_cost:.2f}) or extreme urgency (Slack {slack_val:.2f}). Marking as likely infeasible path."
            )
            return LARGE_NUMBER

        # 6. 음수 비용 방지 (오류 상황)
        if total_cost < 0:
            log.error(
                f"Negative total heuristic cost ({total_cost:.4f}) calculated for '{candidate.subtask.name}'. This should not happen. Returning 0.0. Breakdown: Nav={navigation_cost:.3f}, Urg={urgency_cost:.3f}, Rem={remaining_work_cost:.3f}"
            )
            return 0.0

        return total_cost
