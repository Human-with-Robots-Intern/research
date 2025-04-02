from typing import List

import networkx as nx
import numpy as np

from core.dataclass import SchedulerState
from scheduler.constraint_handler import ConstraintHandler
from utils.common import create_module_logger, extract_monitoring_target_name
from utils.config import (
    ESTIMATE_FILE_NAME,
    FACTOR_ALPHA,
    GROUND_TRUTH_FILE_NAME,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
)
from utils.io_utils import load_knowledge, save_knowledge
from utils.nlp import SentenceSimilarityModel
from utils.task.constraints_util import get_critical_start_info

log = create_module_logger(module_name=__name__, module_log=True)


class Agent:
    def __init__(self):
        self.knowledge = load_knowledge(ESTIMATE_FILE_NAME)
        self.constraint_handler = ConstraintHandler()
        self.sentence_sim_model = SentenceSimilarityModel.get_instance()

    def reset_knowledge_to_gaussian(self) -> None:
        """
        Reset the knowledge base:
        every key (e.g. 'Brew Coffee') is re-initialized with a new Gaussian (mean=1, var=1).
        """
        for key in self.knowledge.keys():
            self.knowledge[key] = {
                "expected_duration": INIT_PRIOR_MEAN,
                "variance": INIT_PRIOR_VARIANCE,
            }
        log.info("Knowledge reset to default Gaussian (mean=0, var=1).")
        save_knowledge(self.knowledge, ESTIMATE_FILE_NAME)

    def _call_sentence_sim_model(
        self, origin_sub_name: str, sub_name_candidates: List[str]
    ) -> str:
        """
        sentence_transformer 싱글톤 인스턴스(self.sentence_sim_model)를 직접 사용하여,
        가장 유사한 sub_name 후보를 반환합니다.
        """
        # 1) 원본 텍스트를 벡터로 인코딩
        origin_vec = self.sentence_sim_model.encode_sentence(origin_sub_name)

        # 2) 후보들을 한 번에 벡터로 인코딩
        candidate_vecs = self.sentence_sim_model.encode_sentences(sub_name_candidates)

        # 3) 배치로 코사인 유사도 계산
        similarity_scores = self.sentence_sim_model.compute_batch_cosine_similarity(
            query_vec=origin_vec, ref_vecs=candidate_vecs
        )

        # 후보가 아예 없거나(similarity_scores가 비어있거나),
        # 예외 상황이면 그냥 origin_sub_name을 리턴
        if len(similarity_scores) == 0:
            return origin_sub_name

        # 4) 가장 유사도가 높은 후보를 찾고, 0.7 미만이면 그 후보로 교체
        idx = int(np.argmax(similarity_scores))
        max_score = similarity_scores[idx]
        return sub_name_candidates[idx] if max_score < 0.7 else origin_sub_name

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
        self.knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.knowledge[known_sub_name]["variance"] = posterior_variance
        save_knowledge(self.knowledge, ESTIMATE_FILE_NAME)

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

    def bayesian_estimate(self, state: SchedulerState) -> SchedulerState:
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

        # 1) 모니터링 subtask 이름 파싱
        monitoring_target_sub_name = extract_monitoring_target_name(state.subtask.name)

        # 2) knowledge 로드
        bayesian_estimate_dict = load_knowledge(ESTIMATE_FILE_NAME)
        gt = load_knowledge(GROUND_TRUTH_FILE_NAME)

        # 3) 문장 유사도 모델로 실제 known_sub_name 결정
        known_sub_name = self._call_sentence_sim_model(
            monitoring_target_sub_name.lower(),
            list(bayesian_estimate_dict.keys()),
        ).lower()

        if known_sub_name not in gt:
            raise ValueError(
                f"No ground_truth found for subtask: {known_sub_name}. Ground Truth에 해당 subtask를 추가해야 합니다."
            )
        gt_interval = gt[known_sub_name]
        if gt_interval <= 0:
            raise ValueError(
                "Invalid ground truth value. Ground truth must be positive."
            )

        # 5) ground_truth / prior_mean / prior_variance 가져오기
        if known_sub_name in bayesian_estimate_dict:
            prior_interval = bayesian_estimate_dict[known_sub_name]["expected_duration"]
            prior_variance = bayesian_estimate_dict[known_sub_name]["variance"]
        else:
            prior_interval = INIT_PRIOR_MEAN
            prior_variance = INIT_PRIOR_VARIANCE
            self.knowledge[known_sub_name] = {
                "expected_duration": INIT_PRIOR_MEAN,
                "variance": INIT_PRIOR_VARIANCE,
            }
        # dictionary의 key를 전부 lowercase로 변경.
        # * 파일 내 key를 전부 lowercase로 바꾸면 아래 주석 처리된 코드는 필요 없음.
        # bayesian_estimate_dict = {
        #     k.lower(): v for k, v in bayesian_estimate_dict.items()
        # }
        # ground_truth_dict = {k.lower(): v for k, v in ground_truth_dict.items()}

        # 4) critical_start_sub_name, end_time 찾아옴
        critical_start_sub_name, critical_start_sub_end_time = get_critical_start_info(
            subtask_name=monitoring_target_sub_name,
            completed=state.completed_subtasks,
            constraints=state.constraints,
            constraint_handler=self.constraint_handler,
        )

        # 6) 베이지안 업데이트 계산
        # critical 제약이 시작 된 이후 경과된 separation interval
        critical_elapsed_interval = state.current_time - critical_start_sub_end_time

        # # epsilon_k_sq (근사 버전)
        # epsilon_k_sq = FACTOR_ALPHA * (prior_interval - critical_elapsed_interval) ** 2

        # epsilon_k_sq (정확 버전)
        epsilon_k_sq = FACTOR_ALPHA * (gt_interval - critical_elapsed_interval) ** 2
        
        # 관측값 (노이즈 존재)
        observation = np.random.normal(loc=gt_interval, scale=np.sqrt(epsilon_k_sq))

        # posterior_interval, posterior_variance 계산
        posterior_interval = (
            prior_variance * observation + epsilon_k_sq * prior_interval
        ) / (epsilon_k_sq + prior_variance)

        posterior_variance = (epsilon_k_sq * prior_variance) / (
            epsilon_k_sq + prior_variance
        )

        self._update_knowledge_and_constraints(
            state=state,
            known_sub_name=known_sub_name,
            posterior_mean=posterior_interval,
            posterior_variance=posterior_variance,
            critical_start_sub_name=critical_start_sub_name,
            monitoring_target_sub_name=monitoring_target_sub_name,
            critical_start_sub_end_time=critical_start_sub_end_time,
        )
        monitored_subtask = {
            "updated_subtask_name": critical_start_sub_name,
            "original_expected_time": prior_interval,
            "updated_expected_time": posterior_interval,
        }
        return state, monitored_subtask
