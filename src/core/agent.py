from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from src.core.dataclass import SchedulerState
from src.utils.common import create_module_logger, extract_monitoring_target_name
from src.utils.config import (
    ESTIMATE_FILE_NAME,
    FACTOR_ALPHA,
    GROUND_TRUTH_FILE_NAME,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
)
from utils.config.constants import AGENT_KNOWLEDGE_PATH, MIN_VARIANCE
from utils.nlp import SentenceSimilarityModel

if TYPE_CHECKING:
    from scheduler import ConstraintHandler

log = create_module_logger(module_name=__name__, module_log=True)


class Agent:
    def __init__(self, constraint_handler: ConstraintHandler):
        """Initializes the Agent, loading prior knowledge and helpers."""
        self.estimate_knowledge: Dict[str, Dict[str, float]] = (
            self._load_lower_case_knowledge(ESTIMATE_FILE_NAME)
        )
        self.ground_truth_knowledge: Dict[str, float] = self._load_lower_case_knowledge(
            GROUND_TRUTH_FILE_NAME
        )

        self.sentence_sim_model = SentenceSimilarityModel.get_instance()
        self.constraint_handler = constraint_handler

    def _load_lower_case_knowledge(self, filename: str) -> Dict[str, Dict]:
        """Loads knowledge from file or returns an empty dict if not found."""
        from utils.io_utils import load_file

        knowledge_path = AGENT_KNOWLEDGE_PATH / filename
        try:
            knowledge = load_file(knowledge_path, "json")
            log.info(f"Successfully loaded knowledge from {filename}.")
            processed_knowledge = {}

            for key, value in knowledge.items():
                processed_knowledge[str(key).lower()] = value

            return processed_knowledge

        except FileNotFoundError:
            log.warning(
                f"Knowledge file {filename} not found. Initializing empty knowledge base."
            )
            return {}

    def reset_knowledge_to_gaussian(self) -> None:
        """
        Reset the knowledge base:
        every key (e.g. 'Brew Coffee') is re-initialized with a new Gaussian (mean=1, var=1).
        """
        for key in self.estimate_knowledge:
            self.estimate_knowledge[key] = {
                "expected_duration": INIT_PRIOR_MEAN,
                "variance": INIT_PRIOR_VARIANCE,
            }

        knowledge_path = AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME
        with open(knowledge_path, "w", encoding="utf-8") as f:
            json.dump(self.estimate_knowledge, f, indent=4, ensure_ascii=False)

    def _find_most_similar_subtask(
        self, query_sub_name: str, candidate_sub_names: List[str]
    ) -> str:
        """
        sentence_transformer 싱글톤 인스턴스(self.sentence_sim_model)를 직접 사용하여,
        가장 유사한 sub_name 후보를 반환합니다.
        """
        if not candidate_sub_names:
            log.warning(
                f"No candidate subtask names provided for similarity check with '{query_sub_name}'."
            )
            return query_sub_name
        query_sub_name_lower = query_sub_name.lower()

        # Check if the exact lowercase name already exists
        if query_sub_name_lower in candidate_sub_names:
            log.debug(f"Exact lowercase match found for '{query_sub_name_lower}'.")
            return query_sub_name_lower

        # Compute cosine similarities
        similar_subtask_name = self.sentence_sim_model.get_similar_ref(
            query=query_sub_name_lower,
            references=candidate_sub_names,  # Assuming candidates are already lowercase from _load_or_init_knowledge
        )
        return similar_subtask_name.lower()

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
        추정된 posterior_mean, posterior_variance를 knowledge에 저장하고,
        constraints 그래프에 반영한다.
        """
        # 1) knowledge에 반영
        self.estimate_knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.estimate_knowledge[known_sub_name]["variance"] = posterior_variance
        estimate_knowledge_path = AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME
        with open(estimate_knowledge_path, "w", encoding="utf-8") as f:
            json.dump(self.estimate_knowledge, f, indent=4, ensure_ascii=False)

        # 2) constraints 그래프 업데이트
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
        source = "default"

        if sub_name in self.estimate_knowledge:
            known_data = self.estimate_knowledge[sub_name]

            mean_val = float(known_data.get("expected_duration", INIT_PRIOR_MEAN))
            var_val = float(known_data.get("variance", INIT_PRIOR_VARIANCE))

            # Ensure values are reasonable (non-negative)
            prior_mean = max(0, mean_val)
            prior_variance = max(MIN_VARIANCE, var_val)
            source = "knowledge_base"

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

        # 1) Extract target subtask name
        monitoring_target_sub_name = extract_monitoring_target_name(state.subtask.name)

        # 2) 문장 유사도 모델로 실제 known_sub_name 결정
        known_sub_name_lower = self._find_most_similar_subtask(
            monitoring_target_sub_name,
            list(
                self.estimate_knowledge.keys(),
            ),
        )

        # 3) ground_truth / prior_mean / prior_variance 가져오기
        gt_interval = self.ground_truth_knowledge.get(known_sub_name_lower)
        prior_mean, prior_variance = self._get_prior_estimate(known_sub_name_lower)

        # 4) Find critical start subtask and its end time
        critical_start_sub_name, critical_start_sub_end_time = get_critical_start_info(
            subtask_name=monitoring_target_sub_name,
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

        self._update_knowledge_and_constraints(
            state=state,
            known_sub_name=known_sub_name_lower,
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
        return state, monitored_subtask
