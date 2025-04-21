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
SIMILARITY_THRESHOLD = 0.7  # Needs tuning based on task names and desired strictness. Higher values = stricter matching.
MIN_VARIANCE = 1e-9  # Avoid division by zero or numerical instability

# FACTOR_ALPHA: Ratio determining how much observation uncertainty relates to prior uncertainty.
# REQUIRES STATISTICAL VALIDATION AND TUNING based on the actual process. Must be positive.
# Value < 1: Observation is assumed more certain than prior.
# Value > 1: Observation is assumed less certain than prior.
# Value = 1: Observation and prior have related uncertainty.
# See config.py for the actual value being used.


class Agent:
    """
    Manages prior knowledge about subtask durations and updates it using Bayesian
    estimation based on monitoring events during task execution.
    """

    def __init__(self):
        """Initializes the Agent, loading prior knowledge and helpers."""
        self.prior_knowledge: Dict[str, Dict[str, float]] = (
            self._load_lower_case_knowledge(ESTIMATE_FILE_NAME)
        )
        self.ground_truth: Dict[str, float] = self._load_lower_case_knowledge(
            GROUND_TRUTH_FILE_NAME
        )

        self.sentence_sim_model = SentenceSimilarityModel.get_instance()

    def _load_lower_case_knowledge(self, filename: str) -> Dict[str, Any]:
        """Loads knowledge from file or returns an empty dict if not found."""
        try:
            knowledge = load_knowledge(filename)
            log.info(f"Successfully loaded knowledge from {filename}.")
            processed_knowledge = {}

            for k, v in knowledge.items():
                processed_knowledge[str(k).lower()] = v

            return processed_knowledge

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

        # Ensure query is lowercase for comparison
        query_sub_name_lower = query_sub_name.lower()

        # Check if the exact lowercase name already exists
        if query_sub_name_lower in candidate_sub_names:
            log.debug(f"Exact lowercase match found for '{query_sub_name_lower}'.")
            return query_sub_name_lower

        log.debug(
            f"Performing similarity check for '{query_sub_name_lower}' against {len(candidate_sub_names)} known tasks."
        )
        # Compute cosine similarities
        similarity_scores = self.sentence_sim_model.compute_batch_cosine_similarity(
            query_str=query_sub_name_lower,
            ref_strs=candidate_sub_names,  # Assuming candidates are already lowercase from _load_or_init_knowledge
        )

        # Find the best match
        if not candidate_sub_names or len(similarity_scores) == 0:
            log.warning(
                f"Similarity check failed for '{query_sub_name_lower}': No candidates or scores."
            )
            return query_sub_name_lower  # fallback to original
        best_match_idx = int(np.argmax(similarity_scores))
        max_score = similarity_scores[best_match_idx]

        # Return the best match only if similarity is ABOVE the threshold.
        if max_score >= SIMILARITY_THRESHOLD:
            if best_match_idx < len(candidate_sub_names):
                best_match_name = candidate_sub_names[best_match_idx]
                log.debug(
                    f"Found similar subtask: '{query_sub_name_lower}' -> '{best_match_name}' (Score: {max_score:.4f})"
                )
                return best_match_name
            else:
                log.error(
                    f"Similarity check error: best_match_idx {best_match_idx} out of bounds for candidates (len {len(candidate_sub_names)})."
                )
                return query_sub_name_lower  # fallback
        else:
            log.debug(
                f"No sufficiently similar subtask found for '{query_sub_name_lower}'. Best score: {max_score:.4f} (Threshold: {SIMILARITY_THRESHOLD}). Using original name."
            )
            return query_sub_name_lower

    def _get_prior_estimate(self, sub_name: str) -> Tuple[float, float]:
        """
        Retrieves the prior mean and variance for a subtask (lowercase name).
        Initializes with defaults if not found or invalid. Ensures variance > MIN_VARIANCE.
        """
        prior_mean = INIT_PRIOR_MEAN
        prior_variance = INIT_PRIOR_VARIANCE
        source = "default"

        if sub_name in self.prior_knowledge:
            known_data = self.prior_knowledge[sub_name]
            try:
                mean_val = float(known_data.get("expected_duration", INIT_PRIOR_MEAN))
                var_val = float(known_data.get("variance", INIT_PRIOR_VARIANCE))

                # Ensure values are reasonable (non-negative)
                prior_mean = max(0, mean_val)
                prior_variance = max(MIN_VARIANCE, var_val)
                source = "knowledge_base"
            except (ValueError, TypeError):
                log.warning(
                    f"Could not parse prior knowledge values for '{sub_name}'. Using defaults."
                )
                # Keep default values
        else:
            log.debug(f"No prior knowledge found for '{sub_name}'. Using defaults.")

        log.debug(
            f"Prior estimate for '{sub_name}': Mean={prior_mean:.2f}, Var={prior_variance:.4f} (Source: {source})"
        )
        return prior_mean, max(prior_variance, MIN_VARIANCE)

    def _perform_bayesian_update(
        self,
        prior_mean: float,
        prior_variance: float,
        critical_elapsed_interval: float,  # Observation (z_k)
    ) -> Tuple[float, float]:
        """
        Performs Bayesian update (Gaussian Prior & Likelihood).
        Uses critical_elapsed_interval as observation.
        Returns (posterior_mean, posterior_variance).
        Returns prior values if update cannot be performed.

        STATISTICAL ASSUMPTIONS (Validation REQUIRED):
        - Assumes Gaussian distributions for prior and likelihood.
        - Assumes likelihood_variance = FACTOR_ALPHA * prior_variance.
        - FACTOR_ALPHA needs tuning/justification based on data/model.
        See config.py for FACTOR_ALPHA value. Consider alternative distributions if needed.
        """
        try:
            # config에서 직접 로드 시도
            from src.utils.config import FACTOR_ALPHA as alpha_config

            if not isinstance(alpha_config, (int, float)) or alpha_config <= 0:
                log.critical(
                    f"Invalid FACTOR_ALPHA in config: {alpha_config}. Must be positive. Using 1.0 as fallback."
                )
                alpha = 1.0
            else:
                alpha = alpha_config
        except ImportError:
            log.error(
                "Could not import FACTOR_ALPHA from src.utils.config. Using 1.0 as fallback."
            )
            alpha = 1.0

        # Ensure prior variance is positive before using it
        prior_variance = max(prior_variance, MIN_VARIANCE)

        # Compute likelihood_variance
        likelihood_variance = alpha * prior_variance
        likelihood_variance = max(likelihood_variance, MIN_VARIANCE)

        # Observation (z_k)
        observation = critical_elapsed_interval
        if observation < 0:
            # Log warning and suggest investigation
            log.error(
                f"Negative critical_elapsed_interval ({observation:.2f}) observed. Clamping to 0. "
                f"Investigate upstream calculation (e.g., critical start time, current time)."
            )
            observation = 0

        # Bayesian Update Formulas
        denominator = prior_variance + likelihood_variance

        # Avoid division by zero or near-zero
        if denominator < MIN_VARIANCE:
            log.error(
                f"Denominator ({denominator:.4e}) near zero in Bayesian update for prior ({prior_mean:.2f}, {prior_variance:.4f}) "
                f"and likelihood var {likelihood_variance:.4f}. Update cannot be performed reliably. Returning PRIOR values."
            )
            return prior_mean, prior_variance

        kalman_gain = prior_variance / denominator

        posterior_mean = prior_mean + kalman_gain * (observation - prior_mean)
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
        Updates internal knowledge ONLY.
        Returns original state and monitoring info dict if successful.
        Raises ValueError if critical path info cannot be determined.
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
        try:
            # 지식 베이스 키 목록을 가져와 lowercase로 변환
            prior_knowledge_keys_lower = [
                str(k).lower() for k in self.prior_knowledge.keys()
            ]
        except Exception as e_keys:
            log.error(
                f"Error processing prior knowledge keys: {e_keys}. Bayesian update may fail.",
                exc_info=True,
            )
            prior_knowledge_keys_lower = []  # 오류 발생 시 빈 리스트 전달

        known_sub_name_lower = self._find_most_similar_subtask(
            monitoring_target_sub_name,
            prior_knowledge_keys_lower,  # lowercase 리스트 전달
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

        # 4) Get Prior Estimate
        prior_mean, prior_variance = self._get_prior_estimate(known_sub_name_lower)

        # 5) Find critical start subtask and its end time
        try:
            # Use the original monitoring target name for graph lookups
            critical_start_sub_name, critical_start_sub_end_time = (
                get_critical_start_info(
                    subtask_name=monitoring_target_sub_name,
                    completed=state.completed_subtasks,
                    constraints=state.constraints,
                )
            )
            log.debug(
                f"Critical start for '{monitoring_target_sub_name}': '{critical_start_sub_name}' ended at {critical_start_sub_end_time:.2f}"
            )
        except (
            ValueError
        ) as e_crit_path:  # get_critical_start_info가 실패 시 ValueError 발생 가정
            log.error(
                f"Failed to get critical start info for '{monitoring_target_sub_name}': {e_crit_path}",
            )
            raise ValueError(
                f"Failed to determine critical path for Bayesian update of '{monitoring_target_sub_name}'"
            ) from e_crit_path
        except Exception as e_crit_generic:  # 다른 예외 처리
            log.error(
                f"Unexpected error getting critical start info: {e_crit_generic}",
                exc_info=True,
            )
            raise ValueError(
                f"Unexpected error getting critical start info for '{monitoring_target_sub_name}'"
            ) from e_crit_generic

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
            knowledge_to_save = {}
            for k, v in self.prior_knowledge.items():
                # Ensure key is string, value is dict with float/int values
                if isinstance(v, dict) and all(
                    isinstance(val, (float, int)) for val in v.values()
                ):
                    knowledge_to_save[str(k)] = v
                else:
                    log.warning(
                        f"Skipping knowledge entry for key '{k}' due to invalid value type: {type(v)}. Expected dict with numeric values."
                    )
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
