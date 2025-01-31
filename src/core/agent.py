import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from utils.constants import KNOWLEDGE_PATH
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=True)


@dataclass
class Config:
    criteria: float = 0.7  # Bayesian update threshold (CDF critical value)
    interval: float = 0.1  # Time interval
    obs_variance: float = 1.0  # Observation variance


class Agent:
    def __init__(self):
        self.knowledge = self._load_knowledge(KNOWLEDGE_PATH)
        self.config = Config()

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

        self._save_knowledge(KNOWLEDGE_PATH)
        log.info("Knowledge reset to default Gaussian (mean=0, var=1).")

    def _load_knowledge(self, knowledge_path: Path) -> Dict[str, Any]:
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
        knowledge_file = knowledge_path / "bayesian_estimate.json"
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

    def _save_knowledge(self, knowledge_path: Path) -> None:
        """
        Save (overwrite) the knowledge JSON file.
        """
        knowledge_path.mkdir(parents=True, exist_ok=True)
        knowledge_file = knowledge_path / "bayesian_estimate.json"
        try:
            with knowledge_file.open("w", encoding="utf-8") as f:
                json.dump(self.knowledge, f, indent=4, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"Error saving knowledge: {e}")

    def monitering_timing(self, subtasks, urgency_time):
        # plan_about_time_critical : time-critical에 대한 planning
        # subtasks : subtask 묶음. 형식은 dictionary {"subtask이름" : 시간}
        # urgency_time : urgency 시간(숫자)
        # 0.7 : monitering의 기준 timing
        # monitering_time은 기존 전체 시간의 0.7배
        # monitering_time이 지나기 전까지의 subtask들을 붙인다.
        # wait는 원래 subtask의 urgency에 맞춰서 채워넣기.
        subtasks = {
            "navigate": 3,
            "pickup": 2,
            "drop": 5
        }
        urgency_time = 10
        ####################################
        time_sum = 0
        subtask_during_time_critical = list(subtasks.key())
        time_during_time_critical = list(subtasks.value())
        monitering_time = 0.7 * urgency_time
        with_monitering_list = []
        with_monitering_time_list = []

        if subtask_during_time_critical == ["navigate"]:
            with_monitering_list.append(subtask_during_time_critical[0])
            with_monitering_time_list.append(time_during_time_critical[0])
            with_monitering_list.append("waiting")
            with_monitering_time_list.append(urgency_time-time_during_time_critical[0])

        else:
            for t in range(len(time_during_time_critical)):
                time_sum += time_during_time_critical[t]
                if time_sum > monitering_time:
                    with_monitering_list.append("monitering")
                    with_monitering_time_list.append(0.1)
                    with_monitering = dict(zip(with_monitering_list, with_monitering_time_list))
                    return with_monitering
                else:
                    with_monitering_list.append(subtask_during_time_critical[t])
                    with_monitering_time_list.append(time_during_time_critical[t])

        with_monitering = dict(zip(with_monitering_list, with_monitering_time_list))

        return with_monitering
    

    def bayesian_estimate(self, actual_duration: float, subtask_name):
        # actual_duration : monitering한 시간
        # ground_truth : 해당 subtask의 ground_truth
        # prior_mean/variance : 이전에 예상한 값의 분포
        # cooking_data : subtask의 진행정도 // 여기에 noise를 주어야 한다.
        # posterior_mean/variance : cooking_data를 받은 후 bayesian estimate를 통해 도출된 새로운 예상한 값의 분포.
        # knowledge.json 파일에서 불러오고 업데이트.

        ground_truth = 10  # 나중에 subtask 이름에 따른 값으로 ground_truth.json 파일에서 불러와야 함.
        estimate_load = self._load_knowledge(KNOWLEDGE_PATH)
        prior_mean = estimate_load[subtask_name]["expected_duration"]
        prior_variance = estimate_load[subtask_name]["variance"]
       

        # bayesian estimate
        a = 1
        likelihood_epsilon_square = a*(prior_mean - actual_duration)** 2
        cooking_data_real = actual_duration / ground_truth
        cooking_data_with_noise = np.random.normal(loc=cooking_data_real, scale=likelihood_epsilon_square)
        posterior_mean = (prior_variance * cooking_data_with_noise + likelihood_epsilon_square * prior_mean) / (likelihood_epsilon_square + prior_variance)
        posterior_variance = (likelihood_epsilon_square * prior_variance) / (likelihood_epsilon_square + prior_variance)


        # posterior_data
        estimate_load[subtask_name]["expected_duration"] = posterior_mean
        estimate_load[subtask_name]["variance"] = posterior_variance

        self._save_knowledge(KNOWLEDGE_PATH)
