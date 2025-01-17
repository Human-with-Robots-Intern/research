import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from omnigibson.utils.ui_utils import create_module_logger
from utils.constants import KNOWLEDGE_PATH

log = create_module_logger(module_name=__name__, is_file_handler=True)


@dataclass
class Config:
    criteria: float = 0.7  # Bayesian update threshold (CDF critical value)
    interval: float = 0.1  # Time interval
    obs_variance: float = 1.0  # Observation variance


class BayesianAgent:
    DEFAULT_KNOWLEDGE = {
        "Valid_actions": {
            "GRASP": {"expected_duration": 1.0, "variance": 1.0, "occurrences": 0},
            "PLACE_INSIDE": {
                "expected_duration": 1.0,
                "variance": 1.0,
                "occurrences": 0,
            },
            "PLACE_ON_TOP": {
                "expected_duration": 1.0,
                "variance": 1.0,
                "occurrences": 0,
            },
            "TOGGLE_ON": {"expected_duration": 1.0, "variance": 1.0, "occurrences": 0},
            "TOGGLE_OFF": {"expected_duration": 1.0, "variance": 1.0, "occurrences": 0},
            "OPEN": {"expected_duration": 1.0, "variance": 1.0, "occurrences": 0},
            "CLOSE": {"expected_duration": 1.0, "variance": 1.0, "occurrences": 0},
        },
        "Invalid_actions": {},
        "Subtask": {},
    }

    def __init__(self, robot: Any, use_knowledge: bool = True):
        """
        Initialize the BayesianAgent.

        Args:
            robot (Any): Robot information associated with the agent.
            use_knowledge (bool): Whether to use stored knowledge. Defaults to True.
        """
        self.robot_attribute = robot
        self.config = Config()
        if use_knowledge:
            self.knowledge = self._load_knowledge(KNOWLEDGE_PATH)
        else:
            self.knowledge = {
                "Valid_actions": {},
                "Invalid_actions": {},
                "Subtask": {},
            }

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

        log.info("Knowledge successfully reset to Gaussian.")
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
                log.info("Knowledge loaded successfully.")
                return knowledge
            except json.JSONDecodeError as e:
                log.error(f"Error decoding knowledge file: {e}")
        else:
            log.warning("Knowledge file not found. Initializing default knowledge.")

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
            log.info("Knowledge saved successfully.")
        except Exception as e:
            log.error(f"Error saving knowledge: {e}")

    def _get_subtask_duration(self, subtask: "Subtask") -> float:
        """
        Get the expected duration of a subtask based on the agent's knowledge.

        Args:
            subtask (Subtask): The subtask whose duration is to be retrieved.

        Returns:
            float: The expected duration of the subtask.
        """
        subtask_name = subtask.name
        subtask_data = self.knowledge.get("Subtask", {}).get(subtask_name)

        if subtask_data:
            expected_duration = subtask_data.get("expected_duration")
            log.info(
                f"Using known duration for subtask '{subtask_name}': {expected_duration}"
            )
        else:
            # If no prior knowledge, calculate from actions
            expected_duration = self._calculate_subtask_duration_from_actions(subtask)
            variance = 1.0  # Initial variance
            # Save new knowledge
            self.knowledge.setdefault("Subtask", {})[subtask_name] = {
                "expected_duration": expected_duration,
                "variance": variance,
                "occurrences": 0,
            }
            log.info(
                f"Estimated duration for new subtask '{subtask_name}': {expected_duration}"
            )
            self._save_knowledge(KNOWLEDGE_PATH)

        return expected_duration

    def adjust_subtask_duration(self, tasks: List["Task"]) -> List["Task"]:
        """
        Adjust the duration intervals of subtasks in the given tasks based on the agent's knowledge.

        Args:
            tasks (List[Task]): List of tasks whose subtasks' durations are to be adjusted.

        Returns:
            List[Task]: The list of tasks with adjusted subtask durations.
        """
        for task in tasks:
            for subtask in task.subtasks:
                subtask.duration.interval = self._get_subtask_duration(subtask)
        return tasks

    def _calculate_subtask_duration_from_actions(self, subtask: "Subtask") -> float:
        """
        Calculate the subtask duration by summing the durations of its primitive actions.

        Args:
            subtask (Subtask): The subtask whose duration is to be calculated.

        Returns:
            float: The calculated expected duration of the subtask.
        """
        total_duration = 0.0
        for action_str in subtask.execution.primitive_actions:
            action_name = action_str.split()[0]
            action_data = self.knowledge.get("Valid_actions", {}).get(action_name)

            if action_data and "expected_duration" in action_data:
                action_duration = action_data["expected_duration"]
            else:
                # If action duration is unknown, assume a default value (e.g., 1.0)
                action_duration = 1.0
                # Initialize the action in knowledge
                self.knowledge.setdefault("Valid_actions", {})[action_name] = {
                    "expected_duration": action_duration,
                    "variance": 1.0,
                    "occurrences": 0,
                }
                log.warning(
                    f"Action '{action_name}' unknown. Assuming default duration {action_duration}."
                )
                self._save_knowledge(KNOWLEDGE_PATH)

            total_duration += action_duration

        return total_duration

    def update_observation_data(self, actual_duration: float, estimate, ground_truth):
        # prior_data
        prior_mean = estimate[0]
        prior_variance = estimate[1]
        cooking_data = actual_duration / ground_truth

        # bayesian estimate
        a = 1
        time_observation = actual_duration
        likelihood_epsilon = a(prior_mean - time_observation) ^ 2
        posterior_mean = (
            prior_variance * cooking_data + likelihood_epsilon * prior_mean
        ) / (likelihood_epsilon + prior_variance)
        posterior_variance = (likelihood_epsilon * prior_variance) / (
            likelihood_epsilon + prior_variance
        )

        # posterior_data
        estimate[0] = posterior_mean
        estimate[1] = posterior_variance

        return estimate

    def update_primitive_action_knowledge(
        self, action_name: str, actual_duration: float
    ) -> None:
        """
        Update the knowledge based on the result of the primitive action execution.

        Args:
            action_name (str): The name of the action that was executed.
            actual_duration (float): The actual duration of the action execution.
        """
        action_data = self.knowledge.setdefault("Valid_actions", {}).setdefault(
            action_name,
            {"expected_duration": actual_duration, "variance": 1.0, "occurrences": 0},
        )

        # Prior data
        prior_mean = action_data["expected_duration"]
        prior_variance = action_data["variance"]

        # Bayesian update
        obs_variance = self.config.obs_variance
        updated_mean = (
            prior_mean / prior_variance + actual_duration / obs_variance
        ) / (1 / prior_variance + 1 / obs_variance)
        updated_variance = 1 / (1 / prior_variance + 1 / obs_variance)

        # Update occurrences
        occurrences = action_data["occurrences"] + 1

        # Update knowledge
        action_data["expected_duration"] = updated_mean
        action_data["variance"] = updated_variance
        action_data["occurrences"] = occurrences

        log.info(f"Updated knowledge for action '{action_name}':")
        log.info(f"  - Duration: {prior_mean:.2f} -> {updated_mean:.2f}")
        log.info(f"  - Variance: {prior_variance:.2f} -> {updated_variance:.2f}")

        # Save knowledge
        self._save_knowledge(KNOWLEDGE_PATH)


# TODO 이 로직을 재사용해야해. 작업 예상시간 넘으면 재추정해야하거든.
# def run_task(self, task_info):
#         print("\n===================================")
#         print(f"Task {task_info.idx + 1}: {task_info.plan_task.name}")
#         print("-----------------------------------")
#         print(
#             f"  - Planned Task Schedule Info: {task_info.plan_task.start:.2f} ~ {task_info.plan_task.end:.2f} ({task_info.plan_task.duration:.2f})"
#         )
#         print(
#             f"  - Noise Task Schedule Info: {task_info.sim_task.start:.2f} ~ {task_info.sim_task.end:.2f} ({task_info.sim_task.duration:.2f})"
#         )
#         print("-----------------------------------")

#         task_duration_dist = norm(
#             loc=task_info.plan_task.duration, scale=(task_info.plan_task.duration / 2)
#         )
#         t_c = task_info.start_time

#         while True:
#             t_c += self.config.interval
#             elapsed_time = t_c - task_info.start_time

#             if task_duration_dist.cdf(elapsed_time) >= self.config.criteria:
#                 print(f"   [Time: {t_c:.2f}] Elapsed: {elapsed_time:.2f}", end="")
#                 task_duration_dist = self.bayesian_estimation(
#                     task_duration_dist, elapsed_time
#                 )

#             if task_info.sim_task.end <= t_c:
#                 print(f"   [Time: {t_c:.2f}] Elapsed: {elapsed_time:.2f}", end="")
#                 task_duration_dist = self.bayesian_estimation(
#                     task_duration_dist, elapsed_time
#                 )

#                 if task_info.plan_task is not None:
#                     pass

#                 print("\n-----------------------------------")
#                 print(f"   Planned Task Duration: {task_info.plan_task.duration:.2f}")
#                 print(f"   Real Task Duration: {task_info.sim_task.duration:.2f}")
#                 print(
#                     f"   Duration updated: {task_info.plan_task.duration:.2f} -> {task_duration_dist.mean():.2f}"
#                 )
#                 print("===================================")
#                 break

#         return t_c
