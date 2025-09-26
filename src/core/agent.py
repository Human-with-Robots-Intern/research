from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from src.models.dataclass import SchedulerState
from src.utils.common import create_module_logger, extract_monitoring_target_name
from src.utils.config import constants
from src.utils.config.constants import (
    AGENT_KNOWLEDGE_PATH,
    CRITICAL_OBJECT_GROUND_TRUTH,
    CRITICAL_OBJECT_INTERVALS,
    FACTOR_ALPHA,
    INIT_PRIOR_VARIANCE,
    MIN_VARIANCE,
)

if TYPE_CHECKING:
    from scheduler import ConstraintHandler

log = create_module_logger(module_name=__name__, module_log=True)


class Agent:
    def __init__(self, constraint_handler: ConstraintHandler, bayesian_load: dict):
        """Initializes the Agent with empty knowledge bases."""
        # TODO 1-1: 파일 로딩 로직을 제거하고 빈 딕셔너리로 초기화합니다.
        self.estimate_knowledge: Dict[str, Dict[str, float]] = bayesian_load

        self.constraint_handler = constraint_handler

    def _update_knowledge_and_constraints(
        self,
        state: SchedulerState,
        monitoring_target_obj_name: str,
        posterior_mean: float,
        posterior_variance: float,
        critical_start_sub_name: str,
        monitoring_target_sub_name: str,
        critical_start_sub_end_time: float,
    ) -> None:
        """
        메모리 상의 knowledge와 constraints 그래프를 업데이트합니다.
        """
        # Key가 없는 경우를 대비하여 먼저 확인하고, 없으면 생성
        if monitoring_target_obj_name not in self.estimate_knowledge:
            self.estimate_knowledge[monitoring_target_obj_name] = {}

        # 1) 메모리 내 knowledge 업데이트
        self.estimate_knowledge[monitoring_target_obj_name][
            "expected_duration"
        ] = posterior_mean
        self.estimate_knowledge[monitoring_target_obj_name][
            "variance"
        ] = posterior_variance

        with open(AGENT_KNOWLEDGE_PATH / "bayesian_estimate.json", "w") as f:
            json.dump(self.estimate_knowledge, f, indent=4)

        # 2) constraints 그래프 업데이트 (이 로직은 유지)
        #    - (critical_start_sub_name, monitoring_target_sub_name)에 posterior_mean 반영

        if state.constraints.has_edge(
            critical_start_sub_name, monitoring_target_sub_name
        ):
            edge_info = state.constraints.edges[
                critical_start_sub_name, monitoring_target_sub_name
            ].setdefault("info", {})
            edge_info["Interval"] = posterior_mean
        else:
            log.warning(
                "Constraint edge %s -> %s missing while updating posterior mean.",
                critical_start_sub_name,
                monitoring_target_sub_name,
            )

        #    - (현재 모니터링 서브태스크, 모니터링 대상) 간 엣지에 잔여 구간 반영
        updated_interval = (
            critical_start_sub_end_time + posterior_mean - state.current_time
        )

        if state.constraints.has_edge(state.subtask.name, monitoring_target_sub_name):
            edge_info = state.constraints.edges[
                state.subtask.name, monitoring_target_sub_name
            ].setdefault("info", {})
            edge_info["Interval"] = updated_interval
        else:
            log.warning(
                "Constraint edge %s -> %s missing while updating monitor residual interval.",
                state.subtask.name,
                monitoring_target_sub_name,
            )

    def _get_prior_estimate(self, obj_name: str) -> Tuple[float, float]:
        """
        Retrieves the prior mean and variance for a subtask (lowercase name).
        Initializes with defaults if not found or invalid. Ensures variance > MIN_VARIANCE.
        """
        prior_mean = constants.INIT_PRIOR_MEAN
        prior_variance = constants.INIT_PRIOR_VARIANCE

        if obj_name in CRITICAL_OBJECT_INTERVALS:
            known_data = self.estimate_knowledge.get(obj_name)
            mean_val = known_data.get("expected_duration", constants.INIT_PRIOR_MEAN)
            var_val = known_data.get("variance", constants.INIT_PRIOR_VARIANCE)

            # Ensure values are reasonable (non-negative)
            prior_mean = max(0, mean_val)
            prior_variance = max(MIN_VARIANCE, var_val)

        else:
            prior_mean = constants.INIT_PRIOR_MEAN
            prior_variance = constants.INIT_PRIOR_VARIANCE
            log.debug(f"No prior knowledge found for '{obj_name}'. Using defaults.")

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

        monitoring_target_sub_name = extract_monitoring_target_name(state.subtask.name)
        monitoring_target_obj_name = (
            state.subtask.execution.objects[0].split("|")[0]
            if state.subtask.execution.objects[0]
            else None
        )

        # 3-3. G.T.와 prior를 직접 조회합니다.
        gt_interval = CRITICAL_OBJECT_GROUND_TRUTH.get(monitoring_target_obj_name)

        # TODO 4: (중요) G.T. 값이 없을 경우의 처리 - 계산 전에 미리 확인하여 TypeError 방지
        if gt_interval is None:
            log.warning(
                f"Ground truth not found for '{monitoring_target_obj_name}'. Skipping Bayesian update."
            )
            return state, {
                "updated_subtask_name": "N/A",
                "error": "Ground truth not found for this object.",
            }

        prior_mean, prior_variance = self._get_prior_estimate(
            monitoring_target_obj_name
        )

        critical_start_sub_name, critical_start_sub_end_time = get_critical_start_info(
            subtask_name=state.subtask.name,
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

        # ZeroDivisionError 방지
        if prior_mean > 0:
            bayesian_diff = abs(posterior_mean - prior_mean) / prior_mean
        else:
            # prior_mean이 0일 경우, posterior_mean이 0이 아니면 무한대의 차이로 간주하여 항상 업데이트
            bayesian_diff = float("inf") if posterior_mean != 0 else 0.0

        log.info(f"bayesian_diff: {bayesian_diff}")
        if bayesian_diff:
            self._update_knowledge_and_constraints(
                state=state,
                monitoring_target_obj_name=monitoring_target_obj_name,
                posterior_mean=posterior_mean,
                posterior_variance=posterior_variance,
                critical_start_sub_name=critical_start_sub_name,
                monitoring_target_sub_name=monitoring_target_sub_name,
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

        return state, monitored_subtask
