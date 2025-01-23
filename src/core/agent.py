import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from utils.constants import KNOWLEDGE_PATH
from utils.util import create_module_logger

# log = create_module_logger(module_name=__name__, is_file_handler=True)


@dataclass
class Config:
    criteria: float = 0.7  # Bayesian update threshold (CDF critical value)
    interval: float = 0.1  # Time interval
    obs_variance: float = 1.0  # Observation variance


class BayesianAgent:

    @staticmethod
    def _initialize_gaussian(
        mean: float = 1.0, variance: float = 1.0
    ) -> Dict[str, Any]:
        """
        Initialize a Gaussian distribution for expected durations.

        Args:
            mean (float): Mean of the Gaussian distribution. Defaults to 1.0.
            variance (float): Variance of the Gaussian distribution. Defaults to 1.0.

        Returns:
            Dict[str, Any]: Dictionary containing expected duration, variance, and occurrences.
        """
        return {
            "expected_duration": np.random.normal(mean, np.sqrt(variance)),
            "variance": variance,
            "occurrences": 0,
        }

    def reset_knowledge_to_gaussian(self) -> None:
        """
        Reset the knowledge base, initializing all expected durations with a Gaussian distribution.
        """
        for action in self.knowledge.get("Valid_actions", {}).keys():
            self.knowledge["Valid_actions"][action] = self._initialize_gaussian()

        for subtask in self.knowledge.get("Subtask", {}).keys():
            self.knowledge["Subtask"][subtask] = self._initialize_gaussian()

        # log.info("Knowledge successfully reset to Gaussian.")
        self._save_knowledge(KNOWLEDGE_PATH)

    def _load_knowledge(self, knowledge_path: Path) -> Dict[str, Any]:
        """
        Load the knowledge file.

        Args:
            knowledge_path (Path): Path to the knowledge directory.

        Returns:
            Dict[str, Any]: Loaded knowledge dictionary.
        """
        knowledge_file = knowledge_path / "knowledge.json"
        if knowledge_file.exists():
            try:
                with knowledge_file.open("r") as f:
                    knowledge = json.load(f)
                # log.info("Knowledge loaded successfully.")
                return knowledge
            except json.JSONDecodeError as e:
                # log.error(f"Error decoding knowledge file: {e}")
                raise json.JSONDecodeError
        else:
            # log.warning("Knowledge file not found. Initializing default knowledge.")
            pass

        # Return default knowledge if file not found or error occurs
        return self.DEFAULT_KNOWLEDGE.copy()

    def _save_knowledge(self, knowledge_path: Path) -> None:
        """
        Save the knowledge file.

        Args:
            knowledge_path (Path): Path to the knowledge directory.
        """
        knowledge_path.mkdir(parents=True, exist_ok=True)
        knowledge_file = knowledge_path / "knowledge.json"
        try:
            with knowledge_file.open("w") as f:
                json.dump(self.knowledge, f, indent=4, ensure_ascii=False)
            # log.info("Knowledge saved successfully.")
        except Exception as e:
            # log.error(f"Error saving knowledge: {e}")
            raise Exception

    def monitering_timing(plan_about_time_critical):
        # plan_about_time_critical : time-critical에 대한 planning
        # 0.7 : monitering의 기준 timing
        # 0.7이 되는 부분의 subtask 파악.
        # 0.7에 subtask가 없으면 그 뒤에 있는거 제거
        # 0.7에 stbtask가 있으면 그걸 포함하여 그 뒤에 있는 것 제거.
        # 그리고 그 끝에 monitering 붙이기.
        plan_about_time_critical = {"subtask1": 3, "subtask2": 4}
        time_sum = 0
        subtask = list(plan_about_time_critical.keys())
        time = list(plan_about_time_critical.values())
        monitering_time = 0.7 * sum(time)
        replanning_list = []

        for t in range(len(plan_about_time_critical)):
            time_sum += time[t]
            if time_sum > monitering_time:
                replanning_list.append("monitering")
                return replanning_list
            else:
                replanning_list.append(subtask[t])

        return replanning_list

    def bayesian_estimate(self, actual_duration: float, subtask):
        # actual_duration : monitering한 시간
        # estimate : 원래 가지고 있던 값의 분포
        # ground_truth : 해당 subtask의 ground_truth
        # prior_mean/variance : 이전에 예상한 값의 분포
        # cooking_data : subtask의 진행정도 // 여기에 noise를 주어야 한다.
        #                   아니면 input값으로 cooking_data를 받기. 이거 받으려면 추가로 받아야 함.
        # posterior_mean/variance : cooking_data를 받은 후 bayesian estimate를 통해 도출된 새로운 예상한 값의 분포.
        subtask_name = subtask

        ground_truth = 10  # 나중에 subtask 이름에 따른 값으로 ground_truth.json 파일에서 불러와야 함.
        estimate_load = self._load_knowledge(KNOWLEDGE_PATH)
        prior_mean = estimate_load["Subtask"][subtask_name]["expected_duration"]
        prior_variance = estimate_load["Subtask"][subtask_name]["variance"]
        cooking_data = actual_duration / ground_truth

        # bayesian estimate
        a = 1
        time_observation = actual_duration
        likelihood_epsilon = a * (prior_mean - time_observation) ^ 2
        posterior_mean = (
            prior_variance * cooking_data + likelihood_epsilon * prior_mean
        ) / (likelihood_epsilon + prior_variance)
        posterior_variance = (likelihood_epsilon * prior_variance) / (
            likelihood_epsilon + prior_variance
        )

        # posterior_data
        estimate_load["Subtask"][subtask_name]["expected_duration"] = posterior_mean
        estimate_load["Subtask"][subtask_name]["variance"] = posterior_variance

        self._save_knowledge(KNOWLEDGE_PATH)
