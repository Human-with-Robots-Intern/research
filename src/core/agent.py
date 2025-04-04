import logging
from typing import Any, Dict, List, Tuple

import networkx as nx
import numpy as np

from core.dataclass import SchedulerState, Subtask  # Assuming Subtask exists
from scheduler.constraint_handler import ConstraintHandler
from src.utils.common import create_module_logger, extract_monitoring_target_name
from src.utils.config import (
    ESTIMATE_FILE_NAME,
    FACTOR_ALPHA,
    GROUND_TRUTH_FILE_NAME,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
)
from src.utils.io_utils import load_knowledge, save_knowledge
from src.utils.nlp import SentenceSimilarityModel
from src.utils.task.constraints_util import get_critical_start_info

log = create_module_logger(module_name=__name__, module_log=True)

# Define constants for clarity and maintainability
SIMILARITY_THRESHOLD = 0.7
MIN_VARIANCE = 1e-9  # To avoid division by zero or numerical instability


class Agent:
    """
    Manages prior knowledge about subtask durations and updates it using Bayesian
    estimation based on monitoring events during task execution.
    """

    def __init__(self):
        """Initializes the Agent, loading prior knowledge and helpers."""
        self.prior_knowledge: Dict[str, Dict[str, float]] = (
            self._load_or_init_knowledge(ESTIMATE_FILE_NAME)
        )
        self.ground_truth: Dict[str, float] = load_knowledge(
            GROUND_TRUTH_FILE_NAME
        )  # Load ground truth once
        self.constraint_handler = ConstraintHandler()
        self.sentence_sim_model = SentenceSimilarityModel.get_instance()
        log.info(
            "Agent initialized with prior knowledge and sentence similarity model."
        )

    def _load_or_init_knowledge(self, filename: str) -> Dict[str, Dict[str, float]]:
        """Loads knowledge from file or returns an empty dict if not found."""
        try:
            knowledge = load_knowledge(filename)
            log.info(f"Successfully loaded knowledge from {filename}.")
            # Ensure keys are lowercase for consistent lookups
            return {k.lower(): v for k, v in knowledge.items()}
        except FileNotFoundError:
            log.warning(
                f"Knowledge file {filename} not found. Initializing empty knowledge base."
            )
            return {}

    def reset_knowledge_to_gaussian(self) -> None:
        """
        Resets the prior knowledge base, re-initializing all known subtasks
        with default Gaussian parameters (mean, variance).
        """
        if not self.prior_knowledge:
            log.warning("Attempted to reset knowledge, but no prior knowledge exists.")
            return

        updated_knowledge = {}
        for key in self.prior_knowledge.keys():
            updated_knowledge[key] = {
                "expected_duration": INIT_PRIOR_MEAN,
                "variance": INIT_PRIOR_VARIANCE,
            }
        self.prior_knowledge = updated_knowledge
        log.info(
            f"Knowledge reset to default Gaussian (mean={INIT_PRIOR_MEAN}, var={INIT_PRIOR_VARIANCE}) for {len(self.prior_knowledge)} keys."
        )
        save_knowledge(self.prior_knowledge, ESTIMATE_FILE_NAME)

    def _find_most_similar_subtask(
        self, query_sub_name: str, candidate_sub_names: List[str]
    ) -> str:
        """
        Uses the sentence similarity model to find the most similar subtask name
        from the candidates, falling back to the original query name if no
        suitable match is found.

        Args:
            query_sub_name: The subtask name to find a match for.
            candidate_sub_names: A list of known subtask names (e.g., keys from prior_knowledge).

        Returns:
            The most similar subtask name from candidates if similarity is high enough,
            otherwise the original query_sub_name.
        """
        if not candidate_sub_names:
            log.warning(
                f"No candidate subtask names provided for similarity check with '{query_sub_name}'."
            )
            return query_sub_name

        # Ensure consistent casing for comparison
        query_sub_name_lower = query_sub_name.lower()

        # Compute cosine similarities
        similarity_scores = self.sentence_sim_model.compute_batch_cosine_similarity(
            query_str=query_sub_name_lower,
            ref_strs=candidate_sub_names,  # Assuming candidates are already lowercase from _load_or_init_knowledge
        )

        if len(similarity_scores) == 0:
            log.warning(
                f"Sentence similarity model returned no scores for '{query_sub_name_lower}'."
            )
            return query_sub_name  # Return original name if scoring failed

        # Find the best match
        best_match_idx = int(np.argmax(similarity_scores))
        max_score = similarity_scores[best_match_idx]

        # Return the best match only if similarity is below the threshold (as per original logic)
        # Note: This logic seems counter-intuitive (low score means better match?).
        # Assuming the original code's logic `max_score < 0.7` is intended.
        # If high score should mean better match, this should be `max_score >= SIMILARITY_THRESHOLD`.
        # Sticking to original logic for now.
        if max_score >= SIMILARITY_THRESHOLD:
            best_match_name = candidate_sub_names[best_match_idx]
            log.debug(
                f"Found similar subtask: '{query_sub_name}' -> '{best_match_name}' (Score: {max_score:.4f})"
            )
            return best_match_name
        else:
            log.debug(
                f"No sufficiently similar subtask found for '{query_sub_name}'. Best score: {max_score:.4f}. Using original name."
            )
            return query_sub_name  # Return original if no match meets criteria

    def _get_prior_estimate(self, sub_name: str) -> Tuple[float, float]:
        """
        Retrieves the prior mean and variance for a subtask, initializing
        with defaults if the subtask is not found in the knowledge base.

        Args:
            sub_name: The name of the subtask (lowercase).

        Returns:
            A tuple containing (prior_mean, prior_variance).
        """
        prior_data = self.prior_knowledge.get(sub_name)

        if prior_data is None:
            log.info(
                f"Subtask '{sub_name}' not in prior knowledge. Initializing with defaults."
            )
            prior_mean = INIT_PRIOR_MEAN
            prior_variance = INIT_PRIOR_VARIANCE
            # Add to knowledge base for future reference
            self.prior_knowledge[sub_name] = {
                "expected_duration": prior_mean,
                "variance": prior_variance,
            }
            # Persist the newly added default knowledge immediately
            # save_knowledge(self.prior_knowledge, ESTIMATE_FILE_NAME) # Optional: Save immediately or wait for update
        else:
            prior_mean = prior_data["expected_duration"]
            prior_variance = prior_data["variance"]

        # Ensure variance is not non-positive for numerical stability
        prior_variance = max(prior_variance, MIN_VARIANCE)

        return prior_mean, prior_variance

    def _perform_bayesian_update(
        self,
        prior_mean: float,
        prior_variance: float,
        ground_truth_duration: float,
        critical_elapsed_interval: float,
    ) -> Tuple[float, float]:
        """
        Performs the Bayesian update calculation for subtask duration.

        Args:
            prior_mean: The prior expected duration.
            prior_variance: The prior variance of the duration.
            ground_truth_duration: The actual duration (used for generating noisy observation).
            critical_elapsed_interval: Time elapsed since the critical constraint started.

        Returns:
            A tuple containing (posterior_mean, posterior_variance).
        """
        # Calculate likelihood variance (epsilon_k_sq) based on the difference
        # between ground truth and elapsed time, scaled by FACTOR_ALPHA.
        # Using ground truth here assumes this is for simulation/evaluation purposes.
        diff = ground_truth_duration - critical_elapsed_interval
        # Ensure the base of the square is non-negative if durations can vary unexpectedly
        epsilon_k_sq = FACTOR_ALPHA * (max(0, diff) ** 2)
        # Ensure likelihood variance is numerically stable
        epsilon_k_sq = max(epsilon_k_sq, MIN_VARIANCE)

        # Generate a noisy observation based on the ground truth duration and likelihood variance
        observation = np.random.normal(
            loc=ground_truth_duration, scale=np.sqrt(epsilon_k_sq)
        )

        # --- Bayesian Update Formulas (for Gaussian prior and likelihood) ---
        # Denominator for posterior calculations
        denominator = epsilon_k_sq + prior_variance

        # Avoid division by zero
        if denominator < MIN_VARIANCE:
            log.warning(
                f"Denominator near zero ({denominator:.4e}) in Bayesian update for prior mean {prior_mean:.2f}. Returning prior values."
            )
            return prior_mean, prior_variance

        # Posterior Mean
        posterior_mean = (
            prior_variance * observation + epsilon_k_sq * prior_mean
        ) / denominator

        # Posterior Variance
        posterior_variance = (epsilon_k_sq * prior_variance) / denominator
        # Ensure posterior variance is also numerically stable
        posterior_variance = max(posterior_variance, MIN_VARIANCE)

        log.debug(
            f"Bayesian Update: Prior=({prior_mean:.2f}, {prior_variance:.4f}), "
            f"GT={ground_truth_duration:.2f}, Elapsed={critical_elapsed_interval:.2f}, "
            f"Obs={observation:.2f}, LikelihoodVar={epsilon_k_sq:.4f} -> "
            f"Posterior=({posterior_mean:.2f}, {posterior_variance:.4f})"
        )

        return posterior_mean, posterior_variance

    def _update_knowledge_and_constraints(
        self,
        state: SchedulerState,
        known_sub_name: str,
        posterior_mean: float,
        posterior_variance: float,
        critical_start_sub_name: str,
        monitoring_target_sub_name: str,  # The original name extracted from monitor task
        critical_start_sub_end_time: float,
    ) -> None:
        """
        Updates the agent's knowledge base and the constraints graph in the
        scheduler state with the new posterior estimates.

        Args:
            state: The current scheduler state.
            known_sub_name: The lowercase, matched subtask name in the knowledge base.
            posterior_mean: The calculated posterior mean duration.
            posterior_variance: The calculated posterior variance.
            critical_start_sub_name: The name of the subtask that started the critical constraint.
            monitoring_target_sub_name: The original name of the subtask being monitored.
            critical_start_sub_end_time: The time when the critical_start_subtask finished.
        """
        # 1) Update internal knowledge base
        if known_sub_name not in self.prior_knowledge:
            log.warning(
                f"Attempting to update knowledge for '{known_sub_name}', but it was not initialized. Creating entry."
            )
            self.prior_knowledge[known_sub_name] = (
                {}
            )  # Should have been initialized in _get_prior_estimate

        self.prior_knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.prior_knowledge[known_sub_name]["variance"] = posterior_variance
        log.info(
            f"Updated knowledge for '{known_sub_name}': Mean={posterior_mean:.2f}, Var={posterior_variance:.4f}"
        )
        # Persist the updated knowledge
        save_knowledge(self.prior_knowledge, ESTIMATE_FILE_NAME)

        # ---- START: Constraint Update CORRECTION ----

        # REMOVE the attempt to update the non-existent original edge
        # edge_critical_to_target = (critical_start_sub_name, monitoring_target_sub_name)
        # if state.constraints.has_edge(*edge_critical_to_target):
        #     ... (This block should be removed) ...
        # else:
        #     log.warning(f"Constraint edge {edge_critical_to_target} not found ...") # This warning is expected now

        # KEEP the update for the edge representing the REMAINING interval from the MONITORING task END.
        # This edge connects the end of the monitor task (state.subtask.name) to the start of the
        # task that ends the critical period (monitoring_target_sub_name).
        edge_monitor_end_to_target_start = (
            state.subtask.name,
            monitoring_target_sub_name,
        )  # Ensure monitoring_target_sub_name is the correct deadline task name here

        # Calculate the UPDATED remaining interval
        updated_remaining_interval = max(
            0, critical_start_sub_end_time + posterior_mean - state.current_time
        )

        if state.constraints.has_edge(*edge_monitor_end_to_target_start):
            nx.set_edge_attributes(
                state.constraints,
                {
                    edge_monitor_end_to_target_start: {
                        "Interval": updated_remaining_interval
                    }
                },
            )
            log.debug(
                f"Updated constraint edge {edge_monitor_end_to_target_start} with updated remaining Interval={updated_remaining_interval:.2f}"
            )
        else:
            log.warning(
                f"Constraint edge {edge_monitor_end_to_target_start} not found. Cannot update remaining interval. Check naming consistency."
            )

    def bayesian_estimate(
        self, state: SchedulerState
    ) -> Tuple[SchedulerState, Dict[str, Any]]:
        """
        Performs Bayesian estimation for a monitored subtask's duration.

        This method orchestrates the process:
        1. Extracts the target subtask name from the current monitoring task.
        2. Finds the most similar known subtask name using sentence similarity.
        3. Retrieves ground truth and prior estimates for the matched subtask.
        4. Identifies the start point (subtask and time) of the relevant critical path constraint.
        5. Calculates the posterior duration estimate using a Bayesian update.
        6. Updates the agent's internal knowledge base and the scheduler's constraint graph.

        Args:
            state: The current state of the scheduler, including the current subtask,
                   completed tasks, constraints, and current time.

        Returns:
            A tuple containing:
            - The updated SchedulerState (with modified constraints).
            - A dictionary containing information about the monitored subtask update:
                {
                    "updated_subtask_name": str, # The name in the knowledge base
                    "original_expected_time": float, # Prior mean
                    "updated_expected_time": float  # Posterior mean
                }

        Raises:
            ValueError: If ground truth data is missing for the matched subtask.
        """
        log.info(
            f"Starting Bayesian estimation for monitoring task: '{state.subtask.name}' at time {state.current_time:.2f}"
        )

        # 1) Extract target subtask name from the monitoring task name
        monitoring_target_sub_name = extract_monitoring_target_name(state.subtask.name)
        if not monitoring_target_sub_name:
            log.error(
                f"Could not extract target subtask name from '{state.subtask.name}'. Skipping update."
            )
            # Return unchanged state and empty info dict
            return state, {}

        # 2) Find the most similar known subtask name (using lowercase)
        known_sub_name_lower = self._find_most_similar_subtask(
            monitoring_target_sub_name,
            list(self.prior_knowledge.keys()),  # Pass lowercase keys
        )
        log.info(
            f"Target: '{monitoring_target_sub_name}', Matched Known Subtask: '{known_sub_name_lower}'"
        )

        # 3) Get Ground Truth (Check existence *before* proceeding)
        # Ground truth lookup should also be case-insensitive if keys aren't guaranteed lowercase
        gt_interval = self.ground_truth.get(known_sub_name_lower)
        if gt_interval is None:
            # Try original casing as fallback if GT keys aren't normalized
            gt_interval = self.ground_truth.get(monitoring_target_sub_name)
            if gt_interval is None:
                raise ValueError(
                    f"No ground_truth found for subtask: '{known_sub_name_lower}' (or original: '{monitoring_target_sub_name}'). "
                    f"Ground Truth file '{GROUND_TRUTH_FILE_NAME}' needs this entry."
                )
            else:
                log.warning(
                    f"Used original name '{monitoring_target_sub_name}' for ground truth lookup."
                )

        # 4) Get Prior Estimate (will initialize if not found)
        prior_mean, prior_variance = self._get_prior_estimate(known_sub_name_lower)

        # 5) Find critical start subtask and its end time for the monitored target
        try:
            critical_start_sub_name, critical_start_sub_end_time = (
                get_critical_start_info(
                    subtask_name=monitoring_target_sub_name,  # Use the original name for graph lookup
                    completed=state.completed_subtasks,
                    constraints=state.constraints,
                    constraint_handler=self.constraint_handler,
                )
            )
            log.debug(
                f"Critical start for '{monitoring_target_sub_name}': '{critical_start_sub_name}' ended at {critical_start_sub_end_time:.2f}"
            )
        except Exception as e:
            log.error(
                f"Failed to get critical start info for '{monitoring_target_sub_name}': {e}",
                exc_info=True,
            )
            # Cannot proceed without critical path info
            return state, {}

        # 6) Calculate elapsed time and perform Bayesian Update
        critical_elapsed_interval = state.current_time - critical_start_sub_end_time
        if critical_elapsed_interval < 0:
            log.warning(
                f"Elapsed time ({critical_elapsed_interval:.2f}) is negative. "
                f"Current time {state.current_time:.2f} is before critical start end time {critical_start_sub_end_time:.2f}. "
                f"Using elapsed time = 0 for update."
            )
            critical_elapsed_interval = 0

        posterior_mean, posterior_variance = self._perform_bayesian_update(
            prior_mean=prior_mean,
            prior_variance=prior_variance,
            ground_truth_duration=gt_interval,
            critical_elapsed_interval=critical_elapsed_interval,
        )

        # 7) Update knowledge base and constraints graph
        self._update_knowledge_and_constraints(
            state=state,
            known_sub_name=known_sub_name_lower,  # Use the matched lowercase name for knowledge update
            posterior_mean=posterior_mean,
            posterior_variance=posterior_variance,
            critical_start_sub_name=critical_start_sub_name,
            monitoring_target_sub_name=monitoring_target_sub_name,  # Use original name for graph edge lookup
            critical_start_sub_end_time=critical_start_sub_end_time,
        )

        # Prepare monitoring result information
        monitored_subtask_info = {
            "updated_subtask_name": known_sub_name_lower,  # The key in the knowledge base that was updated
            "original_expected_time": prior_mean,
            "updated_expected_time": posterior_mean,
            "ground_truth_time": gt_interval,  # Include GT for analysis
            "prior_variance": prior_variance,
            "posterior_variance": posterior_variance,
        }
        log.info(
            f"Bayesian estimation complete for '{monitoring_target_sub_name}'. Update info: {monitored_subtask_info}"
        )

        return state, monitored_subtask_info
