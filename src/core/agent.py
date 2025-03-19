import json
import math
import re
import time
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np

from scheduler.constraint_handler import ConstraintHandler
from scheduler.dataclass import SchedulerState
from utils import KNOWLEDGE_PATH, create_module_logger
from utils.task import task_util
from utils.task.sentence_transformer import SentenceSimilarityModel

log = create_module_logger(module_name=__name__, module_log=True)


class Agent:
    def __init__(self):
        self.knowledge = self._load_knowledge()
        self.constraint_handler = ConstraintHandler()
        self.sentence_sim_model = SentenceSimilarityModel.get_instance()

    def reset_knowledge_to_gaussian(self) -> None:
        """
        Reset the knowledge base:
        every key (e.g. 'Brew Coffee') is re-initialized with a new Gaussian (mean=1, var=1).
        """
        for key in self.knowledge.keys():
            self.knowledge[key] = {
                "expected_duration": 0,
                "variance": 1,
            }

        self._save_knowledge()
        log.info("Knowledge reset to default Gaussian (mean=0, var=1).")

    def _load_knowledge(
        self, file_name: str = "bayesian_estimate.json"
    ) -> Dict[str, Any]:
        """
        Load the knowledge JSON file, which is assumed to have a structure like:
        {
            "Brew Coffee": {
                "expected_duration": 0.48,
                "variance": 1.0
            },
            "Boil Water": {
                "expected_duration": 3.2,
                "variance": 0.5
            }
        }
        """
        knowledge_file = KNOWLEDGE_PATH / file_name

        if knowledge_file.exists():
            try:
                with knowledge_file.open("r", encoding="utf-8") as f:
                    knowledge = json.load(f)
                return knowledge
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Error decoding knowledge file: {e}", doc="", pos=0
                )
        else:
            raise FileNotFoundError(f"Knowledge file not found at {knowledge_file}.")

    def _save_knowledge(self) -> None:
        """
        Save (overwrite) the knowledge JSON file.
        """
        KNOWLEDGE_PATH.mkdir(parents=True, exist_ok=True)
        knowledge_file = KNOWLEDGE_PATH / "bayesian_estimate.json"
        try:
            with knowledge_file.open("w", encoding="utf-8") as f:
                json.dump(self.knowledge, f, indent=4, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"Error saving knowledge: {e}")

    def _call_sentence_sim_model(
        self,
        origin_sub_name: str,
        sub_name_candidates: List[str],
    ) -> str:
        """
        문장 유사도 모델을 호출하여 가장 유사한 후보 sub_name을 반환합니다.

        - 모델 호출 시 에러 발생 시 추정 대기 시간 후에 재시도
        - similarity_scores가 비어 있으면 target_sub_name 반환
        - 최대 유사도가 0.7 미만이면 sub_name_labels 중 가장 유사한 sub_name 반환,
          그 이상이면 원본 그대로.
        """
        similarity_scores = [
            self.sentence_sim_model.compute_cosine_similarity(
                origin_sub_name, sub_name_candidate
            )
            for sub_name_candidate in sub_name_candidates
        ]

        # # 3) 비어 있으면 그대로 반환
        # if not similarity_scores:
        #     return origin_sub_name

        # 4) 최대 유사도와 해당 인덱스를 찾음
        idx, max_score = max(enumerate(similarity_scores), key=lambda x: x[1])

        # 5) 점수가 0.7 미만이면 해당 sub_name 반환, 아니면 원본 그대로
        return sub_name_candidates[idx] if max_score < 0.7 else origin_sub_name

    def _extract_monitoring_target_name(self, subtask_name: str) -> str:
        """
        'Monitoring for (.*?)_' 패턴에서 실제 모니터링 대상 subtask 이름을 추출.
        예: "Monitoring for Make_Coffee_sub_1" -> "Make_Coffee_sub"
        """
        m = re.search(r"Monitoring for (.*?)_", subtask_name)
        if not m:
            raise ValueError(f"Invalid monitoring subtask name: {subtask_name}")
        return m.group(1)

    def _find_critical_start_sub_info(
        self, state: SchedulerState, monitoring_target_sub_name: str
    ) -> tuple[str, float]:
        """
        `monitoring_target_sub_name`에 연결된 critical slot을 찾고,
        가장 큰 interval(critical)을 가진 start_sub_name과 그 end_time을 반환.
        """
        critical_start_sub_name: Optional[str] = None
        critical_start_sub_end_time: Optional[float] = None

        for remain_sub in state.remaining_subtasks:
            if remain_sub.name == monitoring_target_sub_name:
                # in방향 constraint slot들 중 critical만 추려냄
                constraints_start_names = self.constraint_handler.get_time_slots(
                    monitoring_target_sub_name,
                    state.constraints,
                    direction="in",
                )
                critical_slots = [
                    slot for slot in constraints_start_names if slot.is_critical
                ]
                if not critical_slots:
                    raise ValueError(
                        f"Monitoring target sub ({monitoring_target_sub_name}) "
                        "does not have any critical subs."
                    )

                # interval이 가장 큰 critical slot 찾기
                max_critical = max(critical_slots, key=lambda x: x.interval)
                critical_start_sub_name = max_critical.related_subtask_name
                # max_critical_interval = max_critical.interval  # 필요하다면 사용

                # completed_subtasks에서 해당 sub의 end_time 찾기
                critical_start_sub_end_time = next(
                    (
                        ce.end_time
                        for ce in state.completed_subtasks
                        if ce.subtask.name == critical_start_sub_name
                    ),
                    None,
                )
                if critical_start_sub_end_time is None:
                    raise ValueError(
                        f"Critical start sub ({critical_start_sub_name}) end time not found."
                    )

                break

        if critical_start_sub_name is None or critical_start_sub_end_time is None:
            raise ValueError(
                "Could not determine critical_start_sub_name or its end time."
            )

        return critical_start_sub_name, critical_start_sub_end_time

    def _bayesian_update(
        self,
        prior_mean: float,
        prior_variance: float,
        elapsed_time: float,
        ground_truth_value: float,
        noise_sigma: float = 0.015,
    ) -> tuple[float, float]:
        """
        베이지안 추정의 핵심 계산 부분을 별도 함수로 분리.

        파라미터
        ----------
        prior_mean: 기존 mean 추정치
        prior_variance: 기존 var 추정치
        elapsed_time: 경과 시간
        ground_truth_value: 실제 정답(예: subtask duration)
        noise_sigma: lognormal 샘플링에 쓰이는 sigma

        리턴
        ----------
        posterior_mean, posterior_variance
        """

        # 1) 진행비율(cooking_data_real) 계산
        cooking_data_real = elapsed_time / ground_truth_value
        if cooking_data_real <= 0:
            raise ValueError("cooking_data_real must be positive")

        # 2) lognormal 노이즈 모델링
        mean_log = math.log(cooking_data_real)
        cooking_data_with_noise = np.random.lognormal(mean=mean_log, sigma=noise_sigma)

        # 3) 분모 0 방지 위해 prior_variance 최소치 보정
        if prior_variance < 1e-12:
            prior_variance = 1e-12

        # 4) Custom likelihood (예: (prior_mean - 관측)^2)
        a = 1.0
        likelihood_epsilon_square = (
            a * (prior_mean - elapsed_time / cooking_data_with_noise) ** 2
        )

        denominator = likelihood_epsilon_square + prior_variance
        if denominator < 1e-12:
            raise ValueError("Denominator in Bayesian update is too small.")

        # 5) Posterior
        posterior_mean = (
            prior_variance * prior_mean
            + likelihood_epsilon_square * (elapsed_time / cooking_data_with_noise)
        ) / denominator

        posterior_variance = (likelihood_epsilon_square * prior_variance) / denominator

        return posterior_mean, posterior_variance

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
        self._save_knowledge()

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
        monitoring_target_sub_name = self._extract_monitoring_target_name(
            state.subtask.name
        )

        # 2) knowledge 로드
        bayesian_estimation = self._load_knowledge("bayesian_estimate.json")
        ground_truth_dict = self._load_knowledge("bayesian_ground_truth.json")

        # 3) 문장 유사도 모델로 실제 known_sub_name 결정
        known_sub_name = self._call_sentence_sim_model(
            monitoring_target_sub_name,
            list(bayesian_estimation.keys()),
        )

        # 4) critical_start_sub_name, end_time 찾아옴
        critical_start_sub_name, critical_start_sub_end_time = (
            self._find_critical_start_sub_info(state, monitoring_target_sub_name)
        )
        elapsed_time = state.current_time - critical_start_sub_end_time

        # 5) ground_truth / prior_mean / prior_variance 가져오기
        if known_sub_name not in ground_truth_dict:
            raise ValueError(f"No ground_truth found for subtask: {known_sub_name}")
        ground_truth_value = ground_truth_dict[known_sub_name]
        if ground_truth_value <= 0:
            raise ValueError("Invalid ground truth value")
        """
        - actual_duration : monitoring한 시간
        - ground_truth : 해당 subtask의 ground_truth
        - prior_mean/variance : 이전에 예상한 값의 분포
        - cooking_data : subtask의 진행정도 // 여기에 noise를 주어야 한다.
        - posterior_mean/variance : cooking_data를 받은 후 bayesian estimate를 통해 도출된 새로운 예상한 값의 분포.
        - knowledge.json 파일에서 불러오고 업데이트.
        """

        m = re.search("Monitoring for (.*?)_", state.subtask.name)
        if not m:
            raise ValueError("Monitoring subtask name is not valid.")
        monitoring_target_sub_name = m.group(1)

        bayesian_estimation = self._load_knowledge("bayesian_estimate.json")
        ground_truth = self._load_knowledge("bayesian_ground_truth.json")

        known_sub_name = self._call_sentence_sim_model(
            monitoring_target_sub_name, list(bayesian_estimation.keys())
        )

        for remain_sub in state.remaining_subtasks:
            # 제약 시작 sub 찾기
            if remain_sub.name == monitoring_target_sub_name:
                constraints_start_names = self.constraint_handler.get_time_slots(
                    monitoring_target_sub_name, state.constraints, "in"
                )
                critical_slots = [
                    slot for slot in constraints_start_names if slot.is_critical
                ]
                if not critical_slots:
                    raise ValueError(
                        "Monitoring target sub does not have any critical subs"
                    )
                max_critical = max(critical_slots, key=lambda x: x.interval)
                critical_start_sub_name, max_critical_interval = (
                    max_critical.related_subtask_name,
                    max_critical.interval,
                )
                critical_start_sub_end_time = next(
                    (
                        ce.end_time
                        for ce in state.completed_subtasks
                        if ce.subtask.name == critical_start_sub_name
                    ),
                    None,
                )
                if not critical_start_sub_end_time:
                    raise ValueError(
                        "Critical start sub end time is not found in completed subtasks."
                    )
                break

        elapsed_time = state.current_time - critical_start_sub_end_time
        ground_truth = ground_truth[known_sub_name]

        prior_mean = bayesian_estimation[known_sub_name]["expected_duration"]
        prior_variance = bayesian_estimation[known_sub_name]["variance"]

        # bayesian estimate
        cooking_data_real = elapsed_time / ground_truth
        mean_log = np.log(cooking_data_real)
        cooking_data_with_noise = np.random.lognormal(mean=mean_log, sigma=0.015)
        a = 1
        likelihood_epsilon_square = (
            a * (prior_mean - elapsed_time / cooking_data_with_noise) ** 2
        )
        posterior_mean = (
            prior_variance * prior_mean
            + likelihood_epsilon_square * elapsed_time / cooking_data_with_noise
        ) / (likelihood_epsilon_square + prior_variance)
        posterior_variance = (likelihood_epsilon_square * prior_variance) / (
            likelihood_epsilon_square + prior_variance
        )

        # update the posterior_data
        self.knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.knowledge[known_sub_name]["variance"] = posterior_variance
        self._save_knowledge()

        # ! update the constraints
        nx.set_edge_attributes(
            state.constraints,
            {
                (critical_start_sub_name, monitoring_target_sub_name): {
                    "Interval": posterior_mean
                }
            },
        )

        nx.set_edge_attributes(
            state.constraints,
            {
                (state.subtask.name, monitoring_target_sub_name): {
                    "Interval": critical_start_sub_end_time
                    + posterior_mean
                    - state.current_time
                }
            },
        )

        return state
