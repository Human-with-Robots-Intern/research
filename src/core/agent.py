import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from core.dataclass import SchedulerState, Subtask  # Assuming Subtask exists

if TYPE_CHECKING:
    from scheduler.action_handler import ActionHandler
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
SIMILARITY_THRESHOLD = (
    0.7  # NOTE: Needs tuning based on task names and desired strictness
)
MIN_VARIANCE = 1e-9  # To avoid division by zero or numerical instability
# 4.1: FACTOR_ALPHA 검증 필요성 강조 및 기본값 조정 (예시)
# --- 수정: FACTOR_ALPHA 주석 강화 ---
FACTOR_ALPHA = 0.5  # Default: 1.0. Adjusted slightly, but REQUIRES STATISTICAL VALIDATION AND TUNING. Must be positive.
# This factor determines the relationship between prior variance and likelihood variance.
# A value < 1 implies likelihood is more certain than prior, > 1 implies less certain.
# The choice significantly impacts how much the observation influences the posterior.
# --- 수정 끝 ---


class Agent:
    """
    Manages prior knowledge about subtask durations and updates it using Bayesian
    estimation based on monitoring events during task execution.
    """

    def __init__(self, constraint_handler: "ConstraintHandler"):
        """Initializes the Agent, loading prior knowledge and helpers."""
        self.prior_knowledge: Dict[str, Dict[str, float]] = (
            self._load_or_init_knowledge(ESTIMATE_FILE_NAME, lowercase_keys=True)
        )
        self.ground_truth: Dict[str, float] = self._load_or_init_knowledge(
            GROUND_TRUTH_FILE_NAME, lowercase_keys=True
        )
        self.constraint_handler = constraint_handler
        self.sentence_sim_model = SentenceSimilarityModel.get_instance()
        log.info(
            "Agent initialized with injected ConstraintHandler and sentence similarity model."
        )

    def _load_or_init_knowledge(
        self, filename: str, lowercase_keys: bool = True
    ) -> Dict[str, Any]:
        """Loads knowledge from file or returns an empty dict if not found."""
        try:
            knowledge = load_knowledge(filename)
            log.info(f"Successfully loaded knowledge from {filename}.")
            # Ensure keys are lowercase for consistent lookups if requested
            if lowercase_keys:
                # Convert keys to lowercase, handle potential non-string keys gracefully
                return {str(k).lower(): v for k, v in knowledge.items()}
            else:
                return knowledge
        except FileNotFoundError:
            log.warning(
                f"Knowledge file {filename} not found. Initializing empty knowledge base."
            )
            return {}
        except (ValueError, TypeError, KeyError) as e_parse:
            log.error(
                f"Error parsing knowledge data from {filename}: {e_parse}. Returning empty.",
                exc_info=True,
            )
            return {}
        except Exception as e_broad:
            log.error(
                f"Error loading knowledge from {filename}: {e_broad}. Returning empty.",
                exc_info=True,
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

        # Ensure query is lowercase for comparison
        query_sub_name_lower = query_sub_name.lower()

        # Check if the exact lowercase name already exists
        if query_sub_name_lower in candidate_sub_names:
            log.debug(f"Exact match found for '{query_sub_name_lower}'.")
            return query_sub_name_lower

        # Proceed with similarity check if exact match not found
        # Compute cosine similarities
        similarity_scores = self.sentence_sim_model.compute_batch_cosine_similarity(
            query_str=query_sub_name_lower,
            ref_strs=candidate_sub_names,  # Assuming candidates are already lowercase from _load_or_init_knowledge
        )

        # Find the best match
        best_match_idx = int(np.argmax(similarity_scores))
        max_score = similarity_scores[best_match_idx]

        # Return the best match only if similarity is ABOVE the threshold.
        if max_score >= SIMILARITY_THRESHOLD:
            best_match_name = candidate_sub_names[best_match_idx]
            log.debug(
                f"Found similar subtask: '{query_sub_name_lower}' -> '{best_match_name}' (Score: {max_score:.4f})"
            )
            return best_match_name
        else:
            log.debug(
                f"No sufficiently similar subtask found for '{query_sub_name_lower}'. Best score: {max_score:.4f} (Threshold: {SIMILARITY_THRESHOLD}). Using original name."
            )
            return query_sub_name_lower

    def _get_prior_estimate(self, sub_name: str) -> Tuple[float, float]:
        """
        Retrieves the prior mean and variance for a subtask, initializing
        with defaults if the subtask is not found in the knowledge base.

        Args:
            sub_name: The name of the subtask to find a match for.

        Returns:
            A tuple containing (prior_mean, prior_variance).
        """
        duration_value = INIT_PRIOR_MEAN
        duration_source = "default"

        # 1. Try Agent's knowledge (using the new get_latest_estimate method)
        if self.agent:
            try:
                estimate = self.agent.get_latest_estimate(sub_name)
                if estimate is not None:
                    prior_mean, _ = estimate
                    # Ensure non-negative duration
                    duration_value = max(0, prior_mean)
                    duration_source = "agent"
                # else: Agent returned None (error occurred internally)
            except Exception as e_agent:
                log.warning(
                    f"Failed to get estimate from Agent for '{sub_name}': {e_agent}. Falling back."
                )

        # 2. If Agent didn't provide, try subtask.duration.interval
        if (
            duration_source == "default"
            and self.prior_knowledge.get(sub_name)
            and self.prior_knowledge[sub_name]["expected_duration"] is not None
        ):
            try:
                interval_val = float(
                    self.prior_knowledge[sub_name]["expected_duration"]
                )
                if interval_val >= 0:
                    duration_value = interval_val
                    duration_source = "subtask_interval"
                else:
                    log.warning(
                        f"Subtask '{sub_name}' has negative duration.interval. Using {duration_source} estimate ({duration_value:.2f})."
                    )
            except (ValueError, TypeError):
                pass  # Keep default

        log.debug(
            f"Estimated duration for '{sub_name}': {duration_value:.2f} (Source: {duration_source})"
        )
        return duration_value

    def _perform_bayesian_update(
        self,
        prior_mean: float,
        prior_variance: float,
        critical_elapsed_interval: float,  # This is the observation (z_k)
    ) -> Tuple[float, float]:
        """
        Performs the Bayesian update for Gaussian prior and likelihood.
        Uses the critical_elapsed_interval as the observation.
        """
        # --- Statistical Validation Note ---
        # ASSUMPTION: Subtask durations follow a Gaussian distribution, and the observation
        #             (critical_elapsed_interval) also allows for a Gaussian likelihood model.
        # VALIDATION NEEDED: These assumptions MUST be statistically validated against the actual
        #                    process characteristics. If durations are non-Gaussian (e.g., always positive,
        #                    potentially skewed), consider alternative models like Gamma or Log-Normal distributions
        #                    and corresponding Bayesian update methods.
        # likelihood_variance CALCULATION: The formula `likelihood_variance = alpha * prior_variance`
        #                                is a simplification. A more rigorous approach would involve
        #                                deriving the likelihood variance from an observation model or data.
        #                                FACTOR_ALPHA requires careful tuning and justification.
        # --- End Statistical Validation Note ---

        # 4.1: FACTOR_ALPHA 유효성 검사 및 주석 강화
        if not isinstance(FACTOR_ALPHA, (int, float)) or FACTOR_ALPHA <= 0:
            log.critical(
                f"Invalid FACTOR_ALPHA configured: {FACTOR_ALPHA}. Must be positive number. Using 1.0 as fallback."
            )
            alpha = 1.0
        else:
            alpha = FACTOR_ALPHA

        # Ensure prior variance is positive before using it
        prior_variance = max(prior_variance, MIN_VARIANCE)

        likelihood_variance = alpha * prior_variance
        likelihood_variance = max(likelihood_variance, MIN_VARIANCE)

        # Observation (z_k): The actual measured time elapsed since the critical event.
        observation = critical_elapsed_interval
        # Ensure observation is non-negative (time cannot be negative)
        if observation < 0:
            # --- 수정: 음수 관측값 로깅 강화 ---
            log.warning(
                f"Negative critical_elapsed_interval ({observation:.2f}) observed. Clamping to 0. "
                f"This might indicate upstream calculation issues or clock skew."
            )
            # --- 수정 끝 ---
            observation = 0

        # --- Bayesian Update Formulas (Gaussian Prior & Likelihood) ---
        # K = Kalman Gain = prior_variance / (prior_variance + likelihood_variance)
        # posterior_mean = prior_mean + K * (observation - prior_mean)

        denominator = prior_variance + likelihood_variance

        # Avoid division by zero
        if denominator < MIN_VARIANCE:
            log.warning(
                f"Denominator ({denominator:.4e}) near zero in Bayesian update. Returning prior values."
            )
            return prior_mean, prior_variance

        kalman_gain = prior_variance / denominator

        posterior_mean = prior_mean + kalman_gain * (observation - prior_mean)
        # Ensure posterior mean is non-negative
        posterior_mean = max(0, posterior_mean)

        posterior_variance = (1 - kalman_gain) * prior_variance
        # Ensure posterior variance is numerically stable and non-negative
        posterior_variance = max(posterior_variance, MIN_VARIANCE)

        log.debug(
            f"Bayesian Update: Prior=({prior_mean:.2f}, {prior_variance:.4f}), "
            f"ObservedElapsed(z_k)={observation:.2f}, K={kalman_gain:.4f} -> "
            f"Posterior=({posterior_mean:.2f}, {posterior_variance:.4f})"
        )

        return posterior_mean, posterior_variance

    def _update_knowledge_and_constraints(
        self,
        state: SchedulerState,  # State is now only used for logging/context if needed
        known_sub_name: str,  # lowercase name for knowledge base key
        posterior_mean: float,
        posterior_variance: float,
        # Constraint-related args removed as constraints are not modified here
    ) -> None:
        """
        Updates ONLY the agent's internal knowledge base with the new posterior estimates.
        Constraint graph modification is REMOVED based on feedback to avoid inconsistencies.
        This design choice assumes the Scheduler relies on the original logical constraints
        for feasibility checks, while the HeuristicManager can query the Agent for the
        latest duration estimates to guide the search.
        """
        # 1) Update internal knowledge base (using lowercase key)
        if known_sub_name not in self.prior_knowledge:
            log.warning(
                f"Attempting to update knowledge for '{known_sub_name}', but it was not initialized. Creating entry."
            )
            self.prior_knowledge[known_sub_name] = {}  # Initialize if missing

        self.prior_knowledge[known_sub_name]["expected_duration"] = posterior_mean
        self.prior_knowledge[known_sub_name]["variance"] = posterior_variance
        log.info(
            f"Updated internal knowledge for '{known_sub_name}': Mean={posterior_mean:.2f}, Var={posterior_variance:.4f}"
        )

        # Knowledge is saved later via save_knowledge_to_file()

        # ---- Constraint Update Removed ----
        # --- MODIFIED: Add explicit confirmation comment ---
        # As per design review, Agent no longer directly modifies the constraint graph.
        # This prevents potential conflicts with Scheduler's constraint management and
        # ensures constraint intervals remain based on logical structure, not just updated estimates.
        # The Scheduler uses the logical constraints, while the HeuristicManager can
        # query the Agent for updated duration estimates to inform heuristic calculations.
        log.debug("Constraint graph modification by Agent is disabled.")

    def bayesian_estimate(
        self, state: SchedulerState
    ) -> Tuple[SchedulerState, Optional[Dict[str, Any]]]:
        """
        Performs Bayesian estimation based on a monitoring task.
        Updates internal knowledge ONLY. Returns original state and monitoring info.
        """
        log.info(
            f"Starting Bayesian estimation for monitoring task: '{state.subtask.name}' at time {state.current_time:.2f}"
        )
        monitored_subtask_info = {}  # Initialize result dict

        # 1) Extract target subtask name
        monitoring_target_sub_name = extract_monitoring_target_name(state.subtask.name)
        if not monitoring_target_sub_name:
            log.error(
                f"Could not extract target subtask name from '{state.subtask.name}'. Skipping update."
            )
            return state, monitored_subtask_info  # Return original state

        # 2) Find most similar known subtask name (using lowercase)
        # Ensure knowledge keys are lowercase before passing
        prior_knowledge_keys_lower = [
            str(k).lower() for k in self.prior_knowledge.keys()
        ]
        known_sub_name_lower = self._find_most_similar_subtask(
            monitoring_target_sub_name,  # Pass original for similarity check
            prior_knowledge_keys_lower,
        )
        if known_sub_name_lower.lower() != monitoring_target_sub_name.lower():
            log.info(
                f"Target '{monitoring_target_sub_name}' was matched to known subtask '{known_sub_name_lower}' using similarity."
            )
        else:
            log.info(
                f"Target '{monitoring_target_sub_name}' matched existing known subtask."
            )

        # 3) Get Ground Truth (Optional, for logging/comparison only)
        gt_interval = None
        gt_key_used = known_sub_name_lower
        try:
            gt_interval = self.ground_truth.get(gt_key_used)
            if gt_interval is None:
                log.warning(
                    f"Ground truth not found for matched key '{gt_key_used}'. "
                    f"Check ground truth file '{GROUND_TRUTH_FILE_NAME}' and ensure keys are lowercase. Proceeding without GT for update."
                )
            else:
                log.debug(
                    f"Used original name '{known_sub_name_lower}' for ground truth lookup."
                )
        except Exception as e_gt:
            log.error(f"Error accessing ground truth data: {e_gt}", exc_info=True)
            # Proceed without GT even if there was an error accessing it

        # 4) Get Prior Estimate (will initialize if not found)
        prior_mean, prior_variance = self._get_prior_estimate(known_sub_name_lower)

        # 5) Find critical start subtask and its end time
        try:
            # Use the original monitoring target name for graph lookups
            critical_start_sub_name, critical_start_sub_end_time = (
                get_critical_start_info(
                    subtask_name=monitoring_target_sub_name,
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
            return (
                state,
                monitored_subtask_info,
            )  # Cannot proceed without critical path info

        # 6) Calculate elapsed time and perform Bayesian Update
        critical_elapsed_interval = state.current_time - critical_start_sub_end_time
        # Clamp negative elapsed time (can happen due to float precision or logic errors)
        if critical_elapsed_interval < 0:
            log.error(
                f"Elapsed time ({critical_elapsed_interval:.2f}) is negative. Clamping to 0."
            )
            critical_elapsed_interval = 0

        posterior_mean, posterior_variance = self._perform_bayesian_update(
            prior_mean=prior_mean,
            prior_variance=prior_variance,
            critical_elapsed_interval=critical_elapsed_interval,
        )

        # 7) Update ONLY internal knowledge base
        self._update_knowledge_and_constraints(
            state=state,  # Pass state for context if needed inside (currently unused)
            known_sub_name=known_sub_name_lower,  # Use matched lowercase name
            posterior_mean=posterior_mean,
            posterior_variance=posterior_variance,
            # No constraint args needed anymore
        )

        # Prepare monitoring result information
        monitored_subtask_info = {
            "updated_subtask_name": known_sub_name_lower,
            "original_expected_time": prior_mean,
            "updated_expected_time": posterior_mean,
            "ground_truth_time": gt_interval,
        }
        log.info(f"Bayesian estimation complete. Update info: {monitored_subtask_info}")

        # Return the ORIGINAL state and the monitoring info
        return state, monitored_subtask_info

    def save_knowledge_to_file(self) -> None:
        """Saves the current prior knowledge base to the estimate file."""
        if not self.prior_knowledge:
            log.warning("Attempted to save knowledge, but knowledge base is empty.")
            return

        try:
            # Ensure keys are strings before saving if necessary, though load handles lowercase conversion
            knowledge_to_save = {str(k): v for k, v in self.prior_knowledge.items()}
            save_knowledge(knowledge_to_save, ESTIMATE_FILE_NAME)
            log.info(
                f"Successfully saved {len(knowledge_to_save)} knowledge entries to {ESTIMATE_FILE_NAME}."
            )
        except (IOError, PermissionError) as e_io:
            log.error(
                f"CRITICAL: Failed to save knowledge due to file system error: {e_io}",
                exc_info=True,
            )
            # Consider re-raising or specific handling for critical save failures
            # raise e_io # Optional: uncomment to stop execution on critical save failure
        except Exception as e_generic:
            log.error(
                f"Failed to save knowledge base to {ESTIMATE_FILE_NAME}: {e_generic}",
                exc_info=True,
            )
