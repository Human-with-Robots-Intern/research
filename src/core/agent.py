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
FACTOR_ALPHA = 0.5  # Default: 1.0. Adjusted slightly, but REQUIRES VALIDATION AND TUNING. Must be positive.


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

        if len(similarity_scores) == 0:
            log.warning(
                f"Sentence similarity model returned no scores for '{query_sub_name_lower}'."
            )
            return query_sub_name  # Return original name if scoring failed

        # Find the best match
        best_match_idx = int(np.argmax(similarity_scores))
        max_score = similarity_scores[best_match_idx]

        # Return the best match only if similarity is ABOVE the threshold.
        # (Higher cosine similarity score means more similar)
        if max_score >= SIMILARITY_THRESHOLD:
            best_match_name = candidate_sub_names[best_match_idx]
            log.debug(
                f"Found similar subtask: '{query_sub_name}' -> '{best_match_name}' (Score: {max_score:.4f})"
            )
            return best_match_name
        else:
            log.debug(
                f"No sufficiently similar subtask found for '{query_sub_name}'. Best score: {max_score:.4f} (Threshold: {SIMILARITY_THRESHOLD}). Using original name."
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
        # Ensure lookup key is lowercase
        sub_name_lower = sub_name.lower()
        prior_data = self.prior_knowledge.get(sub_name_lower)

        if prior_data is None:
            log.info(
                f"Subtask '{sub_name_lower}' not in prior knowledge. Initializing with defaults (Mean={INIT_PRIOR_MEAN}, Var={INIT_PRIOR_VARIANCE})."
            )
            prior_mean = INIT_PRIOR_MEAN
            prior_variance = INIT_PRIOR_VARIANCE
            # Add to knowledge base with lowercase key
            self.prior_knowledge[sub_name_lower] = {
                "expected_duration": prior_mean,
                "variance": prior_variance,
            }
            # Defer saving to save_knowledge_to_file() call
        else:
            # Make sure the keys within the loaded data are accessible
            try:
                prior_mean = prior_data["expected_duration"]
                prior_variance = prior_data["variance"]
            except KeyError as e:
                log.error(
                    f"Missing key {e} in prior knowledge for '{sub_name_lower}'. Using defaults."
                )
                prior_mean = INIT_PRIOR_MEAN
                prior_variance = INIT_PRIOR_VARIANCE
                # Correct the entry
                self.prior_knowledge[sub_name_lower] = {
                    "expected_duration": prior_mean,
                    "variance": prior_variance,
                }

        # Ensure variance is not non-positive for numerical stability
        prior_variance = max(prior_variance, MIN_VARIANCE)

        return prior_mean, prior_variance

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
        # --- TODO: Statistical Validation Needed ---
        # The choice of Gaussian prior/likelihood and the specific update formulas
        # should be statistically validated against the actual process characteristics.
        # Consider alternative models (e.g., Gamma distribution for durations) if Gaussian assumption is poor.
        # The observation model (likelihood_variance) is particularly critical and needs justification/validation.

        # --- TODO: Review Observation Data Usage ---
        # Currently uses a single observation (critical_elapsed_interval).
        # Consider policies for incorporating multiple observations over time,
        # handling outliers, or weighting recent observations more heavily.

        # Ensure prior variance is numerically stable
        prior_variance = max(prior_variance, MIN_VARIANCE)

        # Model Likelihood Variance (epsilon_k_sq): How uncertain is our observation?
        # Simple model: Assume observation uncertainty is proportional to prior uncertainty.
        # FACTOR_ALPHA scales this. Higher alpha = less trust in prior / more observation noise.
        # --- !!! VALIDITY WARNING & TODO !!! ---
        # This simple noise model (likelihood_variance = FACTOR_ALPHA * prior_variance)
        # needs rigorous validation and potentially replacement with a more sophisticated model
        # that considers sensor noise, process variability, etc.
        # The FACTOR_ALPHA value requires careful tuning based on experiments or domain knowledge.
        # TODO: Evaluate and potentially replace this likelihood variance model.

        # 4.1: FACTOR_ALPHA 유효성 검사 및 주석 강화
        if not isinstance(FACTOR_ALPHA, (int, float)) or FACTOR_ALPHA <= 0:
            log.critical(
                f"Invalid FACTOR_ALPHA configured: {FACTOR_ALPHA}. Must be positive number. Using 1.0 as fallback."
            )
            alpha = 1.0
        else:
            alpha = FACTOR_ALPHA

        likelihood_variance = alpha * prior_variance
        likelihood_variance = max(likelihood_variance, MIN_VARIANCE)

        # Observation (z_k): The actual measured time elapsed since the critical event.
        observation = critical_elapsed_interval
        # Ensure observation is non-negative (time cannot be negative)
        if observation < 0:
            log.warning(
                f"Negative critical_elapsed_interval ({observation:.2f}) observed. Clamping to 0."
            )
            observation = 0

        # --- Bayesian Update Formulas (Gaussian Prior & Likelihood) ---
        # K = Kalman Gain = prior_variance / (prior_variance + likelihood_variance)
        # posterior_mean = prior_mean + K * (observation - prior_mean)
        # posterior_variance = (1 - K) * prior_variance

        denominator = prior_variance + likelihood_variance

        # Avoid division by zero
        if denominator < MIN_VARIANCE:
            log.warning(
                f"Denominator ({denominator:.4e}) near zero in Bayesian update. "
                f"PriorVar={prior_variance:.4e}, LikelihoodVar={likelihood_variance:.4e}. Returning prior values."
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
            f"ObservedElapsed(z_k)={observation:.2f}, "
            f"LikelihoodVar(R)={likelihood_variance:.4f}, K={kalman_gain:.4f} -> "
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
        log.info(
            f"Target: '{monitoring_target_sub_name}', Matched Known Subtask (lowercase): '{known_sub_name_lower}'"
        )

        # 3) Get Ground Truth (Optional, for logging/comparison only)
        gt_interval = None
        gt_key_used = None
        try:
            # Attempt lookup with matched lowercase key first, then original casing as fallback
            gt_interval = self.ground_truth.get(known_sub_name_lower)
            gt_key_used = known_sub_name_lower
            if gt_interval is None:
                gt_interval = self.ground_truth.get(monitoring_target_sub_name)
                gt_key_used = monitoring_target_sub_name
                if gt_interval is None:
                    log.warning(
                        f"Ground truth not found for matched key '{known_sub_name_lower}' or original key '{monitoring_target_sub_name}'. "
                        f"Check ground truth file '{GROUND_TRUTH_FILE_NAME}'. Proceeding without GT for update."
                    )
                else:
                    log.debug(
                        f"Used original name '{monitoring_target_sub_name}' for ground truth lookup."
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
            log.error(  # WARNING -> ERROR
                f"Elapsed time ({critical_elapsed_interval:.2f}) is negative. "
                f"(Current: {state.current_time:.2f}, CritStartEnd: {critical_start_sub_end_time:.2f}). "
                f"Using elapsed time = 0 for update. CRITICAL: Investigate timing source (get_critical_start_info or state.current_time)."  # 원인 조사 촉구
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
            "prior_variance": prior_variance,
            "posterior_variance": posterior_variance,
            "observed_elapsed": critical_elapsed_interval,
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
