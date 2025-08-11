from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from src.models.dataclass import SchedulerState
from src.utils.common import create_module_logger, extract_monitoring_target_name
from src.utils.config.constants import (
    AGENT_KNOWLEDGE_PATH,
    CRITICAL_OBJECT_GROUND_TRUTH,
    ESTIMATE_FILE_NAME,
    FACTOR_ALPHA,
    GROUND_TRUTH_FILE_NAME,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
    MIN_VARIANCE,
    TIMING_TOLERANCE,
)

if TYPE_CHECKING:
    from scheduler import ConstraintHandler

log = create_module_logger(module_name=__name__, module_log=True)


class Agent:
    def __init__(self, constraint_handler: ConstraintHandler):
        """Initializes the Agent with empty knowledge bases."""
        # TODO 1-1: 파일 로딩 로직을 제거하고 빈 딕셔너리로 초기화합니다.
        self.estimate_knowledge: Dict[str, Dict[str, float]] = {}
        self.ground_truth_knowledge: Dict[str, float] = {}
        self.constraint_handler = constraint_handler

    def _update_knowledge_and_constraints(
        self,
        state: SchedulerState,
        known_sub_name: str,
        posterior_mean: float,
        posterior_variance: float,
        critical_start_sub_name: str,
        monitoring_target_sub_name: str,
        critical_start_sub_end_time: float,
    ) -> None:
        """
        메모리 상의 knowledge와 constraints 그래프를 업데이트합니다.
        """
        # 1) 메모리 내 knowledge 업데이트
        self.estimate_knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.estimate_knowledge[known_sub_name]["variance"] = posterior_variance

        # TODO 2-1: 파일 쓰기 로직 제거
        # 아래 파일 쓰기 코드는 완전히 삭제되어야 합니다.
        estimate_knowledge_path = AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME
        with open(estimate_knowledge_path, "w", encoding="utf-8") as f:
            json.dump(self.estimate_knowledge, f, indent=4, ensure_ascii=False)

        # 2) constraints 그래프 업데이트 (이 로직은 유지)
        #    - (critical_start_sub_name, monitoring_target_sub_name)에 posterior_mean 반영

        nx.set_edge_attributes(
            state.constraints,
            {
                (critical_start_sub_name, monitoring_target_sub_name): {
                    "Interval": posterior_mean
                }
            },
        )

        #    - (현재 모니터링 서브태스크, 모니터링 대상) 간 엣지에 잔여 구간 반영
        updated_interval = (
            critical_start_sub_end_time + posterior_mean - state.current_time
        )
        nx.set_edge_attributes(
            state.constraints,
            {
                (state.subtask.name, monitoring_target_sub_name): {
                    "Interval": updated_interval
                }
            },
        )

    def _get_prior_estimate(self, sub_name: str) -> Tuple[float, float]:
        """
        Retrieves the prior mean and variance for a subtask (lowercase name).
        Initializes with defaults if not found or invalid. Ensures variance > MIN_VARIANCE.
        """
        prior_mean = INIT_PRIOR_MEAN
        prior_variance = INIT_PRIOR_VARIANCE

        if sub_name in self.estimate_knowledge:
            known_data = self.estimate_knowledge[sub_name]

            mean_val = float(known_data.get("expected_duration", INIT_PRIOR_MEAN))
            var_val = float(known_data.get("variance", INIT_PRIOR_VARIANCE))

            # Ensure values are reasonable (non-negative)
            prior_mean = max(0, mean_val)
            prior_variance = max(MIN_VARIANCE, var_val)

        else:
            log.debug(f"No prior knowledge found for '{sub_name}'. Using defaults.")

        return prior_mean, max(prior_variance, MIN_VARIANCE)

    def bayesian_estimate(
        self, state: SchedulerState
    ) -> Tuple[SchedulerState, Optional[Dict[str, Any]]]:
        """
        전체 파이프라인:
        1) 모니터링 subtask 이름 파싱
        2) knowledge 로드
        3) 문장 유사도 모델로 실제 known_sub_name 결정
        4) critical_start_sub_name, end_time 찾아옴
        5) ground_truth / prior_mean / prior_variance 가져오기
        6) 베이지안 업데이트 계산
        7) knowledge 및 constraints 업데이트
        """
        from utils.task.constraints_util import get_critical_start_info

        monitoring_target_obj_name = (
            state.subtask.execution.objects[0].split("|")[0]
            if state.subtask.execution.objects[0]
            else None
        )

        # TODO 3: Belief 조회를 위한 Key를 '객체 유형'으로 변경
        key_for_belief = monitoring_target_obj_name

        # 3-3. G.T.와 prior를 직접 조회합니다.
        gt_interval = self.ground_truth_knowledge.get(key_for_belief)
        prior_mean, prior_variance = self._get_prior_estimate(key_for_belief)

        # 4) Find critical start subtask and its end time
        critical_start_sub_name, critical_start_sub_end_time = get_critical_start_info(
            subtask_name=monitoring_target_obj_name,
            completed=state.completed_entries,
            constraints=state.constraints,
            constraint_handler=self.constraint_handler,
        )

        # 5) 베이지안 업데이트 계산
        # critical 제약이 시작 된 이후 경과된 separation interval
        critical_elapsed_interval = state.current_time - critical_start_sub_end_time

        # * epsilon_k_sq (Likelihood의 분산)
        # # epsilon_k_sq (근사 버전)
        # epsilon_k_sq = FACTOR_ALPHA * (prior_interval - critical_elapsed_interval) ** 2

        # epsilon_k_sq (정확 버전)
        epsilon_k_sq = FACTOR_ALPHA * (gt_interval - critical_elapsed_interval) ** 2

        # 관측값 (노이즈 존재)
        observation = np.random.normal(loc=gt_interval, scale=np.sqrt(epsilon_k_sq))

        # posterior_mean, posterior_variance 계산
        posterior_mean = (prior_variance * observation + epsilon_k_sq * prior_mean) / (
            epsilon_k_sq + prior_variance
        )

        posterior_variance = (epsilon_k_sq * prior_variance) / (
            epsilon_k_sq + prior_variance
        )

        bayesian_diff = abs(posterior_mean - prior_mean) / prior_mean
        if bayesian_diff > TIMING_TOLERANCE:
            self._update_knowledge_and_constraints(
                state=state,
                known_sub_name=known_sub_name_lower,
                posterior_mean=posterior_mean,
                posterior_variance=posterior_variance,
                critical_start_sub_name=critical_start_sub_name,
                monitoring_target_sub_name=monitoring_target_obj_name,
                critical_start_sub_end_time=critical_start_sub_end_time,
            )
            monitored_subtask = {
                "updated_subtask_name": critical_start_sub_name,
                "original_expected_time": prior_mean,
                "updated_expected_time": posterior_mean,
                "ground_truth_time": gt_interval,
            }
        else:
            monitored_subtask = {
                "updated_subtask_name": critical_start_sub_name,
                "original_expected_time": prior_mean,
                "updated_expected_time": prior_mean,
                "ground_truth_time": gt_interval,
            }

        # TODO 4: (중요) G.T. 값이 없을 경우의 처리
        # gt_interval이 None일 경우 (e.g., non-critical subtask를 모니터링하는 예외상황)
        # 베이지안 업데이트를 건너뛰거나, 기본값을 사용하는 등의 처리가 필요합니다.
        if gt_interval is None:
            # 업데이트 없이 원래 상태와 정보 반환
            return state, {
                "updated_subtask_name": "N/A",
                "error": "Ground truth not found for this object.",
            }

        return state, monitored_subtask
