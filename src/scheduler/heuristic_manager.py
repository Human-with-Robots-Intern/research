import logging
import math
from typing import TYPE_CHECKING, Optional

import networkx as nx  # Required for path finding
import numpy as np  # 추가 (남은 작업량 추정 등에 사용될 수 있음)

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
    ):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler

        # --- 휴리스틱 가중치 (config 파일에서 로드) ---
        # --- 수정: 가중치 로드 시 오류 처리 추가 ---
        try:
            self.alpha = ALPHA_HEURISTIC
            self.beta = BETA_HEURISTIC
            self.zeta = ZETA_HEURISTIC
            if not all(
                isinstance(w, (int, float)) and w >= 0
                for w in [self.alpha, self.beta, self.zeta]
            ):
                raise ValueError(
                    "Heuristic weights (alpha, beta, zeta) must be non-negative numbers."
                )
            log.info(
                f"Heuristic weights loaded: alpha={self.alpha}, beta={self.beta}, zeta={self.zeta}"
            )
        except (ImportError, ValueError, Exception) as e_weights:
            log.error(
                f"Failed to load or validate heuristic weights from config: {e_weights}. Using defaults (1.0, 1.0, 1.0)."
            )
            self.alpha, self.beta, self.zeta = 1.0, 1.0, 1.0  # 안전한 기본값

    def calc_heuristic(
        self,
        current_node: "SimulationNode",
        candidate: "Candidate",
    ) -> float:
        """
        Calculates the heuristic cost for selecting the candidate subtask next.
        Cost = alpha * Nav_Cost + beta * Urgency_Cost + zeta * Remaining_Work_Cost
        """
        current_time = current_node.state.current_time
        log.debug(
            f"Calculating heuristic for Candidate: '{candidate.subtask.name}' at time {current_time:.2f}"
        )

        # --- 1. Navigation Cost ---
        navigation_cost = 0.0
        nav_time = 0.0  # 로깅용

        nav_time = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )
        # --- 수정: nav_time 유효성 검사 ---
        if nav_time < 0:
            log.warning(
                f"Negative estimated_nav_time ({nav_time:.2f}) found for candidate '{candidate.subtask.name}'. Using 0."
            )
            nav_time = 0.0
        # --- 수정 끝 ---
        navigation_cost = self.alpha * nav_time
        log.debug(
            f"  Nav Time Est.: {nav_time:.2f}, Nav Cost (alpha={self.alpha:.2f}): {navigation_cost:.3f}"
        )

        # --- 2. Urgency Cost (Slack-based) ---
        urgency_cost = 0.0
        slack_val = float("inf")  # Slack 무한대로 초기화 (데드라인 없는 경우)

        # Candidate에 deadline 정보가 있는지 확인 (ConstraintHandler에서 할당)
        if candidate.deadline and candidate.deadline.due_date < float("inf"):
            deadline_time = candidate.deadline.due_date
            deadline_reason = candidate.deadline.subtask_name
            log.debug(
                f"  Deadline detected: {deadline_time:.2f} (due to '{deadline_reason}')"
            )

            # a) Estimate duration of the candidate task itself
            estimated_duration_candidate = self._get_estimated_duration(
                candidate.subtask
            )

            # c) Calculate Slack
            # 현재 시간부터 데드라인까지 남은 시간
            time_remaining_until_deadline = deadline_time - current_time
            # 후보 태스크 + 중간 태스크 실행에 필요한 총 시간
            time_needed = estimated_duration_candidate

            # 슬랙 = 남은 시간 - 필요한 시간
            slack_val = time_remaining_until_deadline - time_needed

            log.debug(
                f"  Slack Calc: Deadline={deadline_time:.2f}, Current={current_time:.2f}, Remaining={time_remaining_until_deadline:.2f}"
            )
            log.debug(
                f"    Time Needed = EstDurCand({estimated_duration_candidate:.2f}) + EstDurIntermed({time_needed_for_intermediate_tasks:.2f}) = {time_needed:.2f}"
            )
            log.debug(
                f"    Calculated Slack = {time_remaining_until_deadline:.2f} - {time_needed:.2f} = {slack_val:.2f}"
            )

            # d) Calculate Urgency Cost based on Slack
            # --- 수정: 긴급도 비용 계산 로직 (기존 유지, 주석 추가) ---
            # Slack <= 0: 데드라인 임박/불가 -> 높은 비용
            # Slack > 0: Slack의 역수에 비례 (Slack 작을수록 비용 증가)
            if slack_val <= EPSILON:
                log.warning(
                    f"  Urgency Alert for '{candidate.subtask.name}': Slack is {slack_val:.2f} (<= {EPSILON}). Assigning very high urgency cost."
                )
                urgency_cost = (
                    self.beta * LARGE_NUMBER
                )  # beta 가중치를 곱한 큰 양수 비용
            else:
                # 비용 함수 형태 (1/slack) - 다른 형태(e.g., exp(-slack), 1/slack^2) 고려 가능
                urgency_term = 1.0 / (slack_val + EPSILON)  # 0 나누기 방지
                urgency_cost = self.beta * urgency_term
                log.debug(
                    f"  Calculated urgency term: {urgency_term:.3f}, Urgency Cost (beta={self.beta:.2f}): {urgency_cost:.3f}"
                )
            # --- 수정 끝 ---
        else:
            log.debug("  No finite deadline for this candidate. Urgency cost is 0.")
            # urgency_cost remains 0.0, slack_val remains inf

        # --- 3. Remaining Work Cost ---
        # --- 수정: _estimate_remaining_cost 호출 ---
        # 현재 후보(candidate)를 제외한 나머지 태스크들에 대한 비용 추정
        # 주의: remaining_subtasks 목록은 현재 상태 기준이어야 함 (Scheduler에서 전달)
        remaining_work_estimate = self._estimate_remaining_cost(
            remaining_subtasks, current_constraints
        )
        remaining_work_cost = self.zeta * remaining_work_estimate
        log.debug(
            f"  Remaining Work Est.: {remaining_work_estimate:.2f}, Remaining Work Cost (zeta={self.zeta:.2f}): {remaining_work_cost:.3f}"
        )
        # --- 수정 끝 ---

        # --- 4. Total Cost ---
        total_cost = navigation_cost + urgency_cost + remaining_work_cost
        log.info(
            f"Heuristic Cost for '{candidate.subtask.name}': {total_cost:.4f} (Nav={navigation_cost:.3f}, Urg={urgency_cost:.3f}, Rem={remaining_work_cost:.3f})"
        )

        # --- 5. Handle Infeasible/Extremely High Cost ---
        # --- 수정: LARGE_NUMBER 조건 통합 및 로깅 명확화 ---
        # nav_time이 LARGE_NUMBER인 경우 (ActionHandler에서 반환?) 또는 urgency_cost가 LARGE_NUMBER인 경우
        # 또는 계산 오류로 total_cost가 비정상적으로 큰 경우
        if (
            navigation_cost >= LARGE_NUMBER
            or urgency_cost >= LARGE_NUMBER
            or total_cost >= LARGE_NUMBER
        ):
            log.warning(
                f"Returning LARGE_NUMBER cost for '{candidate.subtask.name}' due to infeasible navigation (est={nav_time:.2f}) or extreme urgency (Slack {slack_val:.2f}). Marking as likely infeasible path."
            )
            return LARGE_NUMBER  # 경로 배제를 위해 매우 큰 값 반환
        # --- 수정 끝 ---

        # --- 6. Sanity check for negative cost ---
        if total_cost < 0:
            log.error(
                f"Negative total heuristic cost ({total_cost:.4f}) calculated for '{candidate.subtask.name}'. This should not happen. Returning 0.0. Breakdown: Nav={navigation_cost:.3f}, Urg={urgency_cost:.3f}, Rem={remaining_work_cost:.3f}"
            )
            return 0.0  # 음수 비용 대신 0 반환

        return total_cost
