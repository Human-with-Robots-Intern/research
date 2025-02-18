import json
import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict

import numpy as np

from scheduler.constraint_handler import ConstraintHandler
from scheduler.dataclass import SchedulerState
from utils import KNOWLEDGE_PATH, create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Agent:
    def __init__(self):
        self.knowledge = self._load_knowledge()
        self.constraint_handler = ConstraintHandler()

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

    def find_best_match(subtask_name, subtask_dict):
        """
        subtask_dict에서 subtask_name과 가장 유사한 subtask를 찾아 반환
        """
        subtask_names = list(subtask_dict.keys())  # 비교할 subtask 목록
        best_match = process.extractOne(
            subtask_name, subtask_names
        )  # 가장 유사한 값 찾기

        if best_match and best_match[1] > 70:  # 유사도가 70 이상이면 채택
            return best_match[0]
        else:
            return subtask_name  # 유사한 값이 없으면 원본 유지

    def bayesian_estimate(self, state: SchedulerState, subtasks) -> None:
        """
        # actual_duration : monitoring한 시간
        # ground_truth : 해당 subtask의 ground_truth
        # prior_mean/variance : 이전에 예상한 값의 분포
        # cooking_data : subtask의 진행정도 // 여기에 noise를 주어야 한다.
        # posterior_mean/variance : cooking_data를 받은 후 bayesian estimate를 통해 도출된 새로운 예상한 값의 분포.
        # knowledge.json 파일에서 불러오고 업데이트.
        """

        subtask_name = state.subtask.name.split("for")[1].strip()
        subtask_name = subtask_name.split("_")[0].strip()
        # critical end의 subtask를 구함.
        ###################이게 일정한 이름이 아님
        ######그래서 자연어처리 query??? 를 통해 무엇인지 판단해줘야 함.

        # subtask_name = "cooking potato"

        ########
        subtasks = subtasks
        estimate_load = self._load_knowledge("bayesian_estimate.json")

        subtask_names = list(estimate_load.keys())

        best_match = process.extractOne(subtask_name, subtask_names)
        best_match_close = get_close_matches(subtask_name, subtask_names, n=1, cutoff=0)
        actual_duration = 0

        for subtask in subtasks:
            if subtask.name == subtask_name:
                temporal_constraints = subtask.temporal_constraints
                start_subtask = temporal_constraints[0].subtask
                break

        for ce in state.completed_subtasks:
            if ce.subtask.name == start_subtask:
                start_time = ce.end_time

        # for ce in state.completed_subtasks:

        actual_duration = state.current_time - start_time

        djfkdjfkdjf = self._load_knowledge("bayesian_ground_truth.json")
        ground_truth = djfkdjfkdjf[best_match_close[0]]

        prior_mean = estimate_load[best_match_close[0]]["expected_duration"]
        prior_variance = estimate_load[best_match_close[0]]["variance"]

        # bayesian estimate
        cooking_data_real = actual_duration / ground_truth
        mean_log = np.log(cooking_data_real)
        cooking_data_with_noise = np.random.lognormal(mean=mean_log, sigma=0.015)
        a = 1
        likelihood_epsilon_square = (
            a * (prior_mean - actual_duration / cooking_data_with_noise) ** 2
        )
        posterior_mean = (
            prior_variance * prior_mean
            + likelihood_epsilon_square * actual_duration / cooking_data_with_noise
        ) / (likelihood_epsilon_square + prior_variance)
        posterior_variance = (likelihood_epsilon_square * prior_variance) / (
            likelihood_epsilon_square + prior_variance
        )

        # posterior_data
        self.knowledge[best_match_close[0]]["expected_duration"] = posterior_mean
        self.knowledge[best_match_close[0]]["variance"] = posterior_variance

        self._save_knowledge()


# def monitering_timing(plan_about_time_critical):
#     # plan_about_time_critical : time-critical에 대한 planning
#     # 0.7 : monitering의 기준 timing
#     # 0.7이 되는 부분의 subtask 파악.
#     # 0.7 기준 그 전에 오는 subtask만 추가.
#     # 시간 넘으면 monitering 붙이기.
#     plan_about_time_critical = {
#         "subtask1": 3,
#         "subtask2": 4,
#     }  ##예시_이거에 맞춰서 입력 형식 보내거나 두 값을 보내주어야 함.
#     time_sum = 0
#     subtask = list(plan_about_time_critical.keys())
#     time = list(plan_about_time_critical.values())
#     monitering_time = 0.7 * sum(time)
#     replanning_list = []

#     for t in range(len(plan_about_time_critical)):
#         time_sum += time[t]
#         if time_sum > monitering_time:
#             replanning_list.append("monitering")
#             return replanning_list
#         else:
#             replanning_list.append(subtask[t])

#     return replanning_list

# def bayesian_estimate(self, state: SchedulerState) -> None:
#         """
#         Monitoring Subtask가 완료된 직후, 실제 실행 시간(actual_duration)을 기반으로
#         Bayesian 업데이트를 수행한다.
#         """
#         # 모니터링 서브태스크인지 체크 (ex: type == "Monitor")
#         if state.subtask.type != "Monitor":
#             return  # Monitor가 아니면 업데이트 안 함

#         # 실제 subtask_name 파싱
#         # 예: "Monitor for Brew Coffee" -> "Brew Coffee"
#         if "for" in state.subtask.name:
#             subtask_name = state.subtask.name.split("for", 1)[1].strip()
#         else:
#             subtask_name = state.subtask.name

#         # 실제 걸린 시간(이전 subtask 완료 시점 ~ 현재 시점)
#         actual_duration = self.constraint_handler.get_actual_duration(
#             curr_state=state, subtask_name=subtask_name
#         )

#         # ground truth
#         ground_truth_dict = self._load_knowledge("bayesian_ground_truth.json")
#         ground_truth = ground_truth_dict.get(subtask_name, 1.0)

#         # prior
#         estimate_load = self._load_knowledge("bayesian_estimate.json")
#         prior_mean = estimate_load[subtask_name]["expected_duration"]
#         prior_variance = estimate_load[subtask_name]["variance"]

#         # bayesian update
#         a = 1
#         likelihood_epsilon_square = a * (prior_mean - actual_duration) ** 2
#         cooking_data_real = actual_duration / ground_truth

#         # 관측치에 노이즈 추가
#         import numpy as np
#         cooking_data_with_noise = np.random.normal(
#             loc=cooking_data_real, scale=likelihood_epsilon_square
#         )

#         posterior_mean = (
#             prior_variance * cooking_data_with_noise
#             + likelihood_epsilon_square * prior_mean
#         ) / (likelihood_epsilon_square + prior_variance)

#         posterior_variance = (
#             likelihood_epsilon_square * prior_variance
#         ) / (likelihood_epsilon_square + prior_variance)

#         # 저장
#         self.knowledge[subtask_name]["expected_duration"] = posterior_mean
#         self.knowledge[subtask_name]["variance"] = posterior_variance
#         self._save_knowledge()
