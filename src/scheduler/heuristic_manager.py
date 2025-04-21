import logging
import math
from typing import TYPE_CHECKING, Optional

import networkx as nx  # Required for path finding

from core.dataclass import Candidate, SimulationNode, Subtask
from core.task import Subtask  # Subtask 직접 임포트
from src.utils.config import (
    ALPHA_HEURISTIC,
    BETA_HEURISTIC,
    DEFAULT_SUBTASK_DURATION_ESTIMATE,
    EPSILON,
    LARGE_NUMBER,
    ZETA_HEURISTIC,
)

# Forward declarations for type hinting
if TYPE_CHECKING:
    from core.agent import Agent
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler

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
        self.agent = agent  # Store agent instance

        # --- 휴리스틱 가중치 (config 파일에서 로드) ---
        self.alpha = ALPHA_HEURISTIC
        self.beta = BETA_HEURISTIC
        self.zeta = ZETA_HEURISTIC
        if self.agent:
            log.info("HeuristicManager initialized with Agent knowledge.")
        else:
            log.warning(
                "HeuristicManager initialized WITHOUT Agent knowledge. Using default estimates."
            )

    def _get_estimated_duration(self, subtask: Subtask) -> float:
        """Estimates the duration for a single subtask using Agent or defaults."""
        duration_value = DEFAULT_SUBTASK_DURATION_ESTIMATE
        duration_source = "default"

        # 1. Try Agent's knowledge (using the new get_latest_estimate method)
        if self.agent:
            try:
                estimate = self.agent.get_latest_estimate(subtask.name)
                if estimate is not None:
                    prior_mean, _ = estimate
                    # Ensure non-negative duration
                    duration_value = max(0, prior_mean)
                    duration_source = "agent"
                # else: Agent returned None (error occurred internally)
            except Exception as e_agent:
                log.warning(
                    f"Failed to get estimate from Agent for '{subtask.name}': {e_agent}. Falling back."
                )

        # 2. If Agent didn't provide, try subtask.duration.interval
        if (
            duration_source == "default"
            and subtask.duration
            and subtask.duration.interval is not None
        ):
            try:
                interval_val = float(subtask.duration.interval)
                if interval_val >= 0:
                    duration_value = interval_val
                    duration_source = "subtask_interval"
                else:
                    log.warning(
                        f"Subtask '{subtask.name}' has negative duration.interval. Using {duration_source} estimate ({duration_value:.2f})."
                    )
            except (ValueError, TypeError):
                pass  # Keep default

        # log.debug(f"Estimated duration for '{subtask.name}': {duration_value:.2f} (Source: {duration_source})")
        return duration_value

    def calc_heuristic(
        self,
        current_node: "SimulationNode",
        candidate: "Candidate",
        remaining_subtasks: list["Subtask"],
        current_constraints: nx.DiGraph,
    ) -> float:
        """
        Estimates the heuristic cost for a given candidate and remaining tasks.
        """
        # ... (네비게이션 비용 계산 부분 유지) ...

        # ... (긴급도 비용 계산 부분 수정) ...
        urgency_cost = 0.0
        slack_val = float("inf")

        if candidate.deadline and candidate.deadline.due_date < float("inf"):
            deadline_time = candidate.deadline.due_date
            # ... (estimated_duration_candidate 계산) ...
            # ... (time_needed_for_intermediate_tasks 계산 - 아래 18번 항목에서 수정될 수 있음) ...

            # 2. 슬랙 계산
            time_remaining_until_deadline = deadline_time - current_time
            time_needed = (
                estimated_duration_candidate + time_needed_for_intermediate_tasks
            )
            slack_val = time_remaining_until_deadline - time_needed

            log.debug(f"Slack Calc: ... Slack={slack_val:.2f}")

            # --- 수정: 긴급도 비용 계산 로직 변경 ---
            if slack_val <= EPSILON:
                # Slack이 없거나 음수 -> 매우 높은 비용 (데드라인 불가능 또는 임박)
                log.warning(
                    f"Urgency Alert for '{candidate.subtask.name}': Slack is {slack_val:.2f} (<= {EPSILON}). Assigning very high urgency cost."
                )
                urgency_cost = (
                    self.beta * LARGE_NUMBER
                )  # beta 가중치를 곱한 큰 양수 비용
            else:
                # Slack이 양수 -> Slack의 역수에 비례하는 비용 (Slack 작을수록 비용 증가)
                urgency_term = 1.0 / (
                    slack_val + EPSILON
                )  # 단순 역수 또는 다른 함수 (예: 1/sqrt(slack))
                urgency_cost = (
                    self.beta * urgency_term
                )  # beta * (양수 term) -> 양수 비용
                log.debug(
                    f"Calculated urgency term: {urgency_term:.3f}, Urgency Cost: {urgency_cost:.3f}"
                )

        # else: No deadline, urgency_cost remains 0

        # ... (남은 작업량 비용 계산 계속) ...
        remaining_work_cost = self.zeta * remaining_work_estimate

        # ... (최종 비용 계산) ...
        total_cost = (
            navigation_cost + urgency_cost + remaining_work_cost
        )  # 이제 urgency_cost는 양수

        # ... (로깅) ...
        log.debug(f"Heuristic Cost Breakdown: '{candidate.subtask.name}'")
        log.debug(
            f"  Nav Cost ({self.alpha:.2f} * {nav_time:.2f}): {navigation_cost:.3f}"
        )
        log.debug(
            f"  Urgency Cost ({self.beta:.2f}): {urgency_cost:.3f} (Slack: {slack_val:.2f})"
        )
        log.debug(
            f"  Remaining Work Cost ({self.zeta:.2f} * est={remaining_work_estimate:.2f}): {remaining_work_cost:.3f}"
        )
        log.debug(f"  ==> Total Cost: {total_cost:.4f}")

        # ... (실행 불가능 처리 (휴리스틱 레벨) ---
        if total_cost >= LARGE_NUMBER:  # LARGE_NUMBER 비용 발생 조건 통합
            log.warning(
                f"Returning LARGE_NUMBER cost for '{candidate.subtask.name}' due to calculation failure, infeasible navigation, or extreme urgency (Slack {slack_val:.2f})."
            )
            return LARGE_NUMBER

        # Sanity check for negative cost (should be less likely now)
        if total_cost < 0:
            log.error(...)  # 기존 로직 유지
            return 0.0

        return total_cost

        # ... (중간 태스크 시간 계산 - time_needed_for_intermediate_tasks) ...
        # ... (Slack 계산 및 긴급도 비용 계산) ...
        # ... (남은 작업량 비용 계산 - remaining_work_estimate) ...
        # ... (최종 비용 계산) ...
        # ... (로깅) ...
        # ... (실행 불가능 처리) ...
        # ... (반환) ...

        # Sanity check for negative cost (should be less likely now)
        if total_cost < 0:
            log.error(...)  # 기존 로직 유지
            return 0.0

        return total_cost

        remaining_work_estimate = self._estimate_remaining_cost(
            remaining_subtasks, current_constraints
        )
        remaining_work_cost = self.zeta * remaining_work_estimate

        # ... (최종 비용 계산) ...
        total_cost = (
            navigation_cost + urgency_cost + remaining_work_cost
        )  # 이제 urgency_cost는 양수

        # ... (로깅) ...
        log.debug(f"Heuristic Cost Breakdown: '{candidate.subtask.name}'")
        log.debug(
            f"  Remaining Work Cost ({self.zeta:.2f} * est={remaining_work_estimate:.2f}): {remaining_work_cost:.3f}"
        )
        log.debug(f"  ==> Total Cost: {total_cost:.4f}")

        # ... (실행 불가능 처리 로직) ...
        if total_cost >= LARGE_NUMBER:  # LARGE_NUMBER 비용 발생 조건 통합
            log.warning(
                f"Returning LARGE_NUMBER cost for '{candidate.subtask.name}' due to calculation failure, infeasible navigation, or extreme urgency (Slack {slack_val:.2f})."
            )
            return LARGE_NUMBER

        # Sanity check for negative cost (should be less likely now)
        if total_cost < 0:
            log.error(...)  # 기존 로직 유지
            return 0.0

        return total_cost
