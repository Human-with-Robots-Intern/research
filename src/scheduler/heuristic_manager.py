import logging
import math

from core.dataclass import Candidate, SimulationNode, Subtask
from src.utils.config import EPSILON
from src.utils.config.constants import LARGE_NUMBER

log = logging.getLogger(__name__)


class HeuristicManager:
    """
    개선된 다중 기준 휴리스틱 (3개 파라미터, 절충안):
      비용 = alpha * 네비게이션_비용 (nav_time)
            + beta * 긴급도_비용 (수정된 slack_term)
            + zeta * 남은_작업_비용 (개수와 총 예상 시간의 가중 합)

    비용이 낮을수록 우선순위가 높습니다.
    """

    def __init__(self, constraint_handler, action_handler, knowledge_base=None):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler

        # --- 휴리스틱 가중치 (실험을 통해 튜닝 필요) ---
        self.alpha = 1.0  # 네비게이션 시간 가중치
        self.beta = 1.5  # 긴급도 (슬랙) 가중치
        self.zeta = 0.1  # 남은 작업량 추정치 가중치 (단위 고려하여 조정)
        # ---------------------------------------------------

        log.info(
            f"휴리스틱 가중치: alpha={self.alpha}, beta={self.beta}, zeta={self.zeta} "
        )

    def calc_heuristic(
        self,
        current_node: "SimulationNode",
        candidate: "Candidate",
        remaining_subtasks: list["Subtask"],
    ) -> float:
        """
        후보 서브태스크 확장에 대한 휴리스틱 비용을 계산합니다.
        비용이 낮을수록 우선순위가 높습니다.

        Args:
            current_node (SimulationNode): 확장 기준이 되는 현재 노드.
            candidate (Candidate): 평가 대상 후보 태스크.
            remaining_subtasks (list[Subtask]): 이 후보가 실행된 후 남게 될 서브태스크 리스트.

        Returns:
            float: 계산된 휴리스틱 비용. 실행 불가능한 경우 LARGE_NUMBER 반환.
        """

        candidate_subtask = candidate.subtask

        # --- (A) 네비게이션 비용 (alpha * nav_time) ---
        nav_time = 0.0
        try:
            # 네비게이션 시간 계산 (이전과 동일)
            first_action = candidate_subtask.execution.primitive_actions[0]
            action_type = first_action.split()[0].upper()
            if action_type == "NAVIGATE_TO":
                action_info = self.action_handler.get_actions_info(
                    current_node, [first_action]
                )
                nav_time = action_info.time_used if action_info else 0.0
        except (IndexError, AttributeError, TypeError, Exception) as e:
            log.warning(
                f"'{candidate_subtask.name}'의 네비게이션 시간 계산 불가: {e}. nav_time=0 가정."
            )
            nav_time = 0.0
        navigation_cost = self.alpha * nav_time

        # --- (B) 긴급도 비용 (beta * urgency_term) ---
        urgency_term = 0.0
        estimated_duration = 0.0
        slack_val = float("inf")

        if candidate.deadline and candidate.deadline.due_date < float("inf"):
            try:
                # 예상 소요 시간 계산 (이전과 동일)
                sub_duration_info = self.action_handler.get_actions_info(
                    current_node, candidate_subtask.execution.primitive_actions
                )
                if sub_duration_info:
                    estimated_duration = sub_duration_info.time_used
                else:
                    log.warning(
                        f"'{candidate_subtask.name}'의 예상 시간 계산 실패. 기본값 사용."
                    )
                    estimated_duration = (
                        candidate_subtask.duration.interval
                        if candidate_subtask.duration
                        else 0.0
                    )

                # 슬랙 계산 (이전과 동일)
                earliest_finish_time = (
                    candidate.earliest_start_time + estimated_duration
                )
                slack_val = candidate.deadline.due_date - earliest_finish_time

                # 긴급도 항 계산 (이전과 동일)
                if slack_val <= EPSILON:
                    log.warning(
                        f"후보 '{candidate_subtask.name}'의 슬랙({slack_val:.2f})이 0 이하. 높은 긴급도 페널티 적용."
                    )
                    urgency_term = LARGE_NUMBER
                else:
                    urgency_term = -1.0 / math.sqrt(slack_val + EPSILON)

            except Exception as e:
                log.error(
                    f"'{candidate_subtask.name}'의 슬랙 계산 중 오류: {e}. urgency_term=0 설정."
                )
                urgency_term = 0.0
        else:
            log.debug(
                f"후보 '{candidate_subtask.name}'에 유효한 마감 시간이 없음. urgency_term=0."
            )
            urgency_term = 0.0

        urgency_cost = self.beta * urgency_term

        # --- (C) 남은 작업량 비용 (zeta * remaining_work_estimate) ---
        remaining_work_estimate = self._estimate_remaining_cost(remaining_subtasks)
        remaining_work_cost = self.zeta * remaining_work_estimate

        # --- (D) 최종 비용 계산 ---
        total_cost = navigation_cost + urgency_cost + remaining_work_cost

        # --- 로깅 ---
        log.debug(f"휴리스틱 비용 분석: '{candidate_subtask.name}'")
        log.debug(
            f"  네비게이션 비용 (alpha={self.alpha:.2f} * nav={nav_time:.2f}): {navigation_cost:.3f}"
        )
        log.debug(
            f"  긴급도 비용 (beta={self.beta:.2f} * term={urgency_term:.3f}): {urgency_cost:.3f} (슬랙: {slack_val:.2f})"
        )
        log.debug(
            f"  남은 작업 비용 (zeta={self.zeta:.2f} * est={remaining_work_estimate:.2f}): {remaining_work_cost:.3f}"
        )
        log.debug(f"  ==> 총 비용: {total_cost:.4f}")

        # --- 실행 불가능 처리 ---
        if urgency_term >= LARGE_NUMBER:
            log.warning(
                f"후보 '{candidate_subtask.name}'는 슬랙 부족({slack_val:.2f})으로 실행 불가능 처리됨. 비용=LARGE_NUMBER."
            )
            return LARGE_NUMBER

        return total_cost

    def _estimate_remaining_cost(self, remaining_subtasks: list["Subtask"]) -> float:
        """
        남은 작업량을 추정합니다 (개수와 총 예상 시간 가중 합 사용).

        Args:
            remaining_subtasks (list[Subtask]): 남은 서브태스크 리스트.

        Returns:
            float: 추정된 남은 작업 비용.
        """
        if not remaining_subtasks:
            return 0.0

        total_estimated_duration = 0.0
        for sub in remaining_subtasks:
            # 가정: sub.duration.interval이 해당 서브태스크의 예상 소요 시간을 나타냄
            if sub.duration and sub.duration.interval is not None:
                try:
                    # interval 값이 float 또는 int로 변환 가능한지 확인
                    duration_value = float(sub.duration.interval)
                    total_estimated_duration += duration_value
                except (ValueError, TypeError):
                    log.warning(
                        f"Subtask '{sub.name}'의 duration.interval ('{sub.duration.interval}')이 숫자가 아님. 무시."
                    )
            else:
                log.warning(
                    f"Subtask '{sub.name}'에 유효한 duration 정보가 없음. 예상 시간 0으로 처리."
                )
                pass  # 또는 기본 시간 추가

        # 가중 합으로 비용 계산
        cost = total_estimated_duration

        log.debug(f"추정된 남은 작업 비용 총 예상시간:{total_estimated_duration:.2f})")
        return cost
