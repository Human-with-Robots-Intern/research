import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np

from scheduler.constraint_handler import ConstraintHandler
from scheduler.dataclass import SchedulerState
from utils import KNOWLEDGE_PATH, create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=True)


@dataclass
class Config:
    criteria: float = 0.7  # Bayesian update threshold (CDF critical value)
    interval: float = 0.1  # Time interval
    obs_variance: float = 1.0  # Observation variance


class Agent:
    def __init__(self):
        self.knowledge = self._load_knowledge()
        self.config = Config()
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

    def bayesian_estimate(self, state: SchedulerState) -> None:
        # actual_duration : monitoring한 시간
        # ground_truth : 해당 subtask의 ground_truth
        # prior_mean/variance : 이전에 예상한 값의 분포
        # cooking_data : subtask의 진행정도 // 여기에 noise를 주어야 한다.
        # posterior_mean/variance : cooking_data를 받은 후 bayesian estimate를 통해 도출된 새로운 예상한 값의 분포.
        # knowledge.json 파일에서 불러오고 업데이트.

        subtask_name = state.subtask.name.split("for")[1].strip()
        actual_duration = self.constraint_handler.get_actual_duration(
            curr_state=state, subtask_name=subtask_name
        )
        ground_truth = self._load_knowledge("bayesian_ground_truth.json").get(
            subtask_name
        )

        estimate_load = self._load_knowledge("bayesian_estimate.json")
        prior_mean = estimate_load[subtask_name]["expected_duration"]
        prior_variance = estimate_load[subtask_name]["variance"]

        # bayesian estimate
        a = 1
        likelihood_epsilon_square = a * (prior_mean - actual_duration) ** 2
        cooking_data_real = actual_duration / ground_truth
        cooking_data_with_noise = np.random.normal(
            loc=cooking_data_real, scale=likelihood_epsilon_square
        )
        posterior_mean = (
            prior_variance * cooking_data_with_noise
            + likelihood_epsilon_square * prior_mean
        ) / (likelihood_epsilon_square + prior_variance)
        posterior_variance = (likelihood_epsilon_square * prior_variance) / (
            likelihood_epsilon_square + prior_variance
        )

        # posterior_data
        self.knowledge[subtask_name]["expected_duration"] = posterior_mean
        self.knowledge[subtask_name]["variance"] = posterior_variance

        self._save_knowledge()
