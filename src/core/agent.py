import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np
from scipy.stats import norm

from utils.constants import KNOWLEDGE_PATH


@dataclass
class Config:
    criteria: float = 0.7  # Bayesian update threshold (CDF critical value)
    interval: float = 0.1  # Time interval
    obs_variance: float = 1.0  # Observation variance


class Agent:
    def __init__(
        self,
        robot: Any,
        use_knowledge: bool = True,
    ):
        """
        Initialize the Agent class
        """
        self.robot = robot  # Agent's robot information
        if use_knowledge:
            self.config = Config()  # Configuration values
            self.knowledge = self._load_knowledge(KNOWLEDGE_PATH)  # Load knowledge
        else:
            self.knowledge = {}

    def _load_knowledge(self, knowledge_path) -> Dict[str, Any]:
        """
        Load the knowledge file
        """
        try:
            with open(knowledge_path / "knowledge.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("Knowledge file not found. Initializing empty knowledge.")
            return {
                "Valid_actions": {
                    "GRASP": 1,
                    "PLACE_INSIDE": 1,
                    "PLACE_ON_TOP": 1,
                    "TOGGLE_ON": 1,
                    "TOGGLE_OFF": 1,
                    "OPEN": 1,
                    "CLOSE": 1,
                },
                "Invalid_actions": {},
                "Subtask": {},
            }

    def _save_knowledge(self, knowledge_path) -> None:
        """
        Save the knowledge file
        """
        knowledge_path.mkdir(parents=True, exist_ok=True)
        with open(knowledge_path / "knowledge.json", "w") as f:
            json.dump(self.knowledge, f, indent=4, ensure_ascii=False)
        print("Knowledge saved successfully.")

    def get_task_duration(self, subtask: "Subtask") -> float:  # type: ignore
        """
        Adjust the expected duration of a subtask based on the agent's knowledge
        """
        subtask_data = self.knowledge.get("Subtask", {}).get(subtask.name)
        # agent가 알고 있는 subtask의 정보가 있으면 그 정보를 사용
        if subtask_data:
            expected_duration = subtask_data.get("expected_duration")
        else:
            # If no prior knowledge, calculate from actions
            expected_duration = self._calculate_subtask_duration_from_actions(subtask)
            variance = 1.0  # Initial variance
            # Save new knowledge
            self.knowledge.setdefault("Subtask", {})[subtask.name] = {
                "expected_duration": expected_duration,
                "variance": variance,
                "occurrences": 0,
            }
            self._save_knowledge(KNOWLEDGE_PATH)

        return expected_duration

    def _calculate_subtask_duration_from_actions(self, subtask: "Subtask") -> float:  # type: ignore
        """
        Calculate the subtask duration by summing the durations of its primitive actions
        """
        total_duration = 0.0
        for action in subtask.execution.primitive_actions:
            action_duration = self.knowledge["Valid_actions"].get(action.split()[0])
            if action_duration is None:
                # If action duration is unknown, assume a default value (e.g., 1)
                action_duration = 1.0
                self.knowledge["Valid_actions"][action.split()[0]] = action_duration
                self._save_knowledge(KNOWLEDGE_PATH)
            total_duration += action_duration
        return total_duration

    def update_task_knowledge(self, subtask: "Subtask", actual_duration: float) -> None:  # type: ignore
        # env에서 직접 agent의 task 수행 이후 update와 관련있는 코드
        """
        Update the knowledge based on the result of the subtask execution
        """
        # Retrieve or initialize subtask data
        subtask_data = self.knowledge.setdefault("Subtask", {}).setdefault(
            subtask.name,
            {"expected_duration": actual_duration, "variance": 1.0, "occurrences": 0},
        )

        # Prior data
        prior_mean = subtask_data["expected_duration"]
        prior_variance = subtask_data["variance"]

        # Bayesian update
        obs_variance = self.config.obs_variance
        updated_mean = (
            prior_mean / prior_variance + actual_duration / obs_variance
        ) / (1 / prior_variance + 1 / obs_variance)
        updated_variance = 1 / (1 / prior_variance + 1 / obs_variance)

        # Update occurrences
        occurrences = subtask_data["occurrences"] + 1

        # Update knowledge
        subtask_data["expected_duration"] = updated_mean
        subtask_data["variance"] = updated_variance
        subtask_data["occurrences"] = occurrences

        print(f"Updated Knowledge for {subtask.name}:")
        print(f"  - Duration: {prior_mean:.2f} -> {updated_mean:.2f}")
        print(f"  - Variance: {prior_variance:.2f} -> {updated_variance:.2f}")

        # Save knowledge
        self._save_knowledge(KNOWLEDGE_PATH)
