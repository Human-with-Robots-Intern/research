# scheduler/heuristic_manager.py (Final Version)

import logging
import math
from pathlib import Path  # Keep Path if KNOWLEDGE_PATH uses it
from typing import Any, Dict, List, Optional

# --- 필요한 Import ---
from src.core.dataclass import Candidate, SimulationNode, Subtask

# ConstraintHandler는 직접 필요 없음
from src.utils.common import create_module_logger  # 경로 utils.common 가정

# Config 및 IO 유틸 경로 확인 필요
from src.utils.config import ESTIMATE_FILE_NAME, KNOWLEDGE_PATH
from src.utils.io_utils import load_knowledge  # 가정: io_utils.knowledge_io 에 있음

# from src.scheduler.action_handler import ActionHandler


log = create_module_logger(module_name=__name__, module_log=True)

# --- 상수 ---
LARGE_COST = 9999999.0  # 실행 불가능 또는 매우 나쁜 후보에 대한 비용
DEFAULT_SUBTASK_DURATION = 5.0  # ActionHandler 시뮬레이션 실패 시 기본값
SLACK_EPSILON = 1e-6  # 슬랙 계산 시 분모 0 방지 및 부동 소수점 비교용


class HeuristicManager:
    """
    Calculates heuristic cost for scheduling candidates. Lower cost is preferred.

    The heuristic considers:
    1.  Navigation Time Cost: Estimated travel time to the task's first interaction object.
    2.  Urgency Cost (Slack Penalty): Penalty based on the time remaining until the
        task's deadline. Uses simulated task duration and incorporates deadline
        timing uncertainty (variance) from Bayesian knowledge for robustness.
    3.  Remaining Work Cost: Proxy for makespan, estimated as the sum of durations
        of subsequent tasks.

    Cost = alpha * nav_time + beta * slack_penalty + delta * remaining_work_cost
    """

    def __init__(
        self,
        # constraint_handler: ConstraintHandler,  # Not directly needed
        action_handler,
    ):
        self.action_handler = action_handler
        self.knowledge_filepath = (
            KNOWLEDGE_PATH / ESTIMATE_FILE_NAME
        )  # Path to knowledge file

        # --- Tunable Heuristic Weights ---
        self.alpha = 1.0  # Navigation weight
        self.beta = 5.0  # Slack penalty weight (Urgency)
        self.gamma = 0.0  # Variance cost weight (Obsolete - Set to 0)
        self.delta = 0.5  # Remaining work weight (Makespan proxy)
        # How much deadline uncertainty (std dev) affects slack calculation
        self.slack_variance_factor = 1.0  # (k) Higher k = more risk averse

        log.info(
            "HeuristicManager initialized. Weights: alpha=%.1f, beta=%.1f, gamma=%.1f, delta=%.1f, slack_k=%.1f",
            self.alpha,
            self.beta,
            self.gamma,
            self.delta,
            self.slack_variance_factor,
        )

    def _get_current_knowledge(self) -> Dict[str, Dict[str, float]]:
        """Safely reloads knowledge from file for variance info."""
        knowledge = {}
        try:
            # Assuming load_knowledge handles FileNotFoundError internally or raises it
            knowledge_data = load_knowledge(
                ESTIMATE_FILE_NAME
            )  # Use the function directly
            # Ensure keys are lowercase and structure is as expected
            knowledge = {
                k.lower(): v
                for k, v in knowledge_data.items()
                if isinstance(v, dict) and "variance" in v  # Basic validation
            }
        except FileNotFoundError:
            log.warning(
                f"Knowledge file '{ESTIMATE_FILE_NAME}' not found at {KNOWLEDGE_PATH}. Variance info unavailable."
            )
        except Exception as e:
            log.error(
                f"Error reloading or parsing knowledge file {self.knowledge_filepath}: {e}. Variance info unavailable."
            )
        return knowledge

    def _estimate_subtask_duration(
        self, current_node: SimulationNode, subtask: Subtask
    ) -> float:
        """Estimates a single subtask's duration using ActionHandler."""
        duration = DEFAULT_SUBTASK_DURATION  # Default
        if not subtask.execution or not subtask.execution.primitive_actions:
            return 0.0  # No actions, zero duration

        try:
            # Simulate the subtask's actions from the *current* node state
            # Pass current_node for context, not a temporary one unless necessary
            sub_actions_info = self.action_handler.get_actions_info(
                current_node, subtask.execution.primitive_actions
            )
            if sub_actions_info:
                simulated_time = sub_actions_info.action_duration
                duration = max(0, float(simulated_time))
            else:
                log.warning(
                    f"Duration simulation failed for '{subtask.name}'. Using default {DEFAULT_SUBTASK_DURATION}."
                )
        except AttributeError:
            log.warning(
                f"ActionSimulationLog missing 'total_time_used' method. Using default duration for {subtask.name}."
            )
        except Exception as e:
            log.warning(
                f"Error simulating duration for '{subtask.name}': {e}. Using default."
            )
        return duration

    def _estimate_remaining_duration(
        self, current_node: SimulationNode, remaining_subtasks: List[Subtask]
    ) -> float:
        """Estimates the total duration of remaining subtasks."""
        total_remaining_duration = 0.0
        if not remaining_subtasks:
            return 0.0

        for subtask in remaining_subtasks:
            # Use the helper function for individual estimation
            total_remaining_duration += self._estimate_subtask_duration(
                current_node, subtask
            )

        # log.debug(f"Estimated remaining work duration: {total_remaining_duration:.2f}")
        return total_remaining_duration

    def calc_heuristic(
        self,
        current_node: SimulationNode,  # State *before* candidate execution
        candidate: Candidate,  # Candidate subtask to evaluate
        remaining_subtasks: List[
            Subtask
        ],  # Tasks remaining *after* candidate (provided by Scheduler)
    ) -> float:
        """Calculates the heuristic cost for a candidate subtask. Lower is better."""

        # --- Reload Knowledge (for variance lookup) ---
        # This ensures we use the latest variance estimate related to deadlines
        current_knowledge = self._get_current_knowledge()

        # --- Initialize Costs ---
        nav_cost = 0.0
        urgency_cost = 0.0
        remaining_work_cost_val = 0.0

        # --- 1) Navigation Time Cost ---
        try:
            agent_pos = current_node.state.scene_positions.get("agent")
            first_obj_target = None
            if (
                candidate.subtask.execution
                and candidate.subtask.execution.primitive_actions
            ):
                for action_str in candidate.subtask.execution.primitive_actions:
                    parts = action_str.split()
                    action_type = parts[0].upper()
                    if action_type != "NAVIGATE_TO" and len(parts) > 1:
                        first_obj_target = parts[1]
                        break

            if agent_pos and first_obj_target:
                target_pos = current_node.state.scene_positions.get(first_obj_target)
                if target_pos:
                    nav_action_str = f"NAVIGATE_TO {first_obj_target}"
                    nav_path_info = self.action_handler.get_actions_info(
                        current_node, [nav_action_str]
                    )
                    if nav_path_info:
                        nav_cost = self.alpha * nav_path_info.action_duration
                else:
                    log.warning(f"Pos not found for nav target '{first_obj_target}'.")
            # else: log if agent or target missing

        except Exception as e:
            log.error(
                f"Error calculating nav_cost for {candidate.subtask.name}: {e}",
                exc_info=True,
            )
            nav_cost = self.alpha * 10.0  # Penalty

        # --- 2) Urgency Cost (Slack Penalty with Variance) ---
        if candidate.deadline.due_date != float("inf"):
            # Estimate candidate's own duration
            sub_duration = self._estimate_subtask_duration(
                current_node, candidate.subtask
            )

            # Get variance associated with the deadline constraint
            deadline_variance = 0.0
            deadline_subtask_name = candidate.deadline.subtask_name
            if deadline_subtask_name:
                # Use the name of the task causing the deadline as the key
                deadline_knowledge_key = deadline_subtask_name.lower()
                deadline_sub_info = current_knowledge.get(deadline_knowledge_key, {})
                if "variance" in deadline_sub_info:
                    deadline_variance = max(0, deadline_sub_info["variance"])
                    log.debug(
                        f"Using variance {deadline_variance:.2f} for deadline '{deadline_subtask_name}'"
                    )

            # Calculate conservative deadline and slack
            deadline_std_dev = math.sqrt(deadline_variance)
            conservative_deadline = candidate.deadline.due_date - (
                self.slack_variance_factor * deadline_std_dev
            )
            slack_val = conservative_deadline - (
                candidate.earliest_start_time + sub_duration
            )

            if slack_val < SLACK_EPSILON:
                log.debug(
                    f"Slack non-positive ({slack_val:.2f}) for '{candidate.subtask.name}' based on conservative deadline. High cost."
                )
                return LARGE_COST  # Infeasible or too risky
            else:
                slack_penalty = 1.0 / (slack_val + SLACK_EPSILON)
                urgency_cost = self.beta * slack_penalty
                log.debug(
                    f"Urgency Cost for '{candidate.subtask.name}': {urgency_cost:.3f} (Slack={slack_val:.2f}, Penalty={slack_penalty:.3f})"
                )

        # --- 3) Remaining Work Cost (Makespan Proxy) ---
        try:
            # Estimate based on tasks remaining AFTER this candidate
            remaining_work_duration = self._estimate_remaining_duration(
                current_node, remaining_subtasks
            )
            remaining_work_cost_val = self.delta * remaining_work_duration
            log.debug(
                f"Remaining Work Cost after '{candidate.subtask.name}': {remaining_work_cost_val:.2f} (Est. Duration={remaining_work_duration:.2f})"
            )
        except Exception as e:
            log.error(f"Error estimating remaining work: {e}", exc_info=True)
            remaining_work_cost_val = self.delta * 50.0  # Penalty

        # --- Final Weighted Sum ---
        total_cost = nav_cost + urgency_cost + remaining_work_cost_val

        log.debug(
            f"[calc_heuristic] FINAL: sub='{candidate.subtask.name}', cost={total_cost:.3f} = "
            f"[nav={nav_cost:.2f}] + [urgency={urgency_cost:.3f}] + [remain={remaining_work_cost_val:.2f}]"
        )

        return total_cost
