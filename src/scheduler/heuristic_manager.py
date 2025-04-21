import logging
import math
from typing import TYPE_CHECKING, Optional

import networkx as nx  # Required for path finding

from core.dataclass import Candidate, SimulationNode, Subtask
from core.task import Subtask  # Subtask 직접 임포트
from src.utils.config import EPSILON
from src.utils.config.constants import DEFAULT_SUBTASK_DURATION_ESTIMATE, LARGE_NUMBER

# Forward declarations for type hinting
if TYPE_CHECKING:
    from core.agent import Agent
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler

log = logging.getLogger(__name__)


class HeuristicManager:
    """
    개선된 다중 기준 휴리스틱 (3개 파라미터, 절충안):
      비용 = alpha * 네비게이션_비용 (nav_time)
            + beta * 긴급도_비용 (수정된 slack_term)
            + zeta * 남은_작업_비용 (개수와 총 예상 시간의 가중 합)

    비용이 낮을수록 우선순위가 높습니다.
    """

    def __init__(
        self,
        constraint_handler: "ConstraintHandler",
        action_handler: "ActionHandler",
        agent: Optional["Agent"] = None,  # Inject Agent dependency
    ):
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.agent = agent  # Store agent instance

        # --- 휴리스틱 가중치 (매우 중요! 실험 및 튜닝 필수!) ---
        # 7.4: 튜닝 필요성 강조 및 gamma 추가
        # These weights critically determine the scheduler's behavior.
        # They MUST be tuned based on experiments, specific task characteristics,
        # and desired scheduling objectives (e.g., makespan, deadline adherence).
        self.alpha = 1.0  # Navigation time weight
        self.beta = 1.5  # Urgency (slack) weight
        self.zeta = 0.1  # Remaining work estimate weight
        # --- 주석 추가: 미사용 파라미터 ---
        self.gamma = (
            0.5  # Wait time penalty weight (Currently unused in calc_heuristic)
        )
        # ----------------------------------------------------------
        if self.agent:
            log.info("HeuristicManager initialized with Agent knowledge.")
        else:
            log.warning(
                "HeuristicManager initialized WITHOUT Agent knowledge. Using default estimates."
            )

    def calc_heuristic(
        self,
        current_node: "SimulationNode",
        candidate: "Candidate",
        remaining_subtasks: list["Subtask"],
        actual_duration: Optional[float] = None,  # 실제 소요 시간 (옵션)
    ) -> float:
        """
        후보 서브태스크 확장에 대한 휴리스틱 비용을 계산합니다.
        비용이 낮을수록 우선순위가 높습니다.

        Args:
            current_node (SimulationNode): 확장 기준이 되는 현재 노드.
            candidate (Candidate): 평가 대상 후보 태스크.
            remaining_subtasks (list[Subtask]): 이 후보가 실행된 후 남게 될 서브태스크 리스트.
            actual_duration (Optional[float]): 후보 태스크의 실제 시뮬레이션 시간 (제공된 경우 사용).

        Returns:
            float: 계산된 휴리스틱 비용. 실행 불가능하거나 매우 비관적인 경우 LARGE_NUMBER 반환.
        """
        # --- TODO: Review Heuristic Components and Weights (alpha, beta, zeta) ---
        # The current combination of navigation, urgency, and remaining work might be biased
        # towards certain task types or scheduling goals (e.g., minimizing makespan vs. meeting deadlines).
        # Evaluate the effectiveness of each component and the appropriateness of the weights
        # based on simulation results and desired system behavior. Consider alternative heuristics.

        candidate_subtask = candidate.subtask
        current_time = current_node.state.current_time

        # --- (A) 네비게이션 비용 (Improved Estimation) ---
        nav_time = 0.0
        try:
            # Use dedicated estimation method from ActionHandler
            # Assumes action_handler is updated separately to provide this method
            nav_time = self.action_handler.get_navigation_time_estimate(
                current_node, candidate.subtask
            )
            if nav_time == float("inf"):
                log.warning(
                    f"'{candidate.subtask.name}' navigation deemed infeasible. Cost=LARGE_NUMBER."
                )
                return LARGE_NUMBER
            elif nav_time < 0:
                log.warning(
                    f"'{candidate.subtask.name}' received negative nav estimate ({nav_time:.2f}). Using 0."
                )
                nav_time = 0.0

        except AttributeError:
            # Fallback if the dedicated method doesn't exist yet
            log.warning(
                f"ActionHandler missing 'get_navigation_time_estimate'. Falling back to first action sim."
            )
            try:
                # Check if there are any actions first
                if (
                    not candidate.subtask.execution
                    or not candidate.subtask.execution.primitive_actions
                ):
                    log.warning(
                        f"Task '{candidate.subtask.name}' has no actions for fallback nav estimation. Assuming 0."
                    )
                    nav_time = 0.0
                else:
                    first_action = candidate.subtask.execution.primitive_actions[0]
                    # --- MODIFIED FALLBACK ---
                    # Check if the first action is actually navigation
                    if first_action.upper().startswith("NAVIGATE_TO"):
                        action_info = self.action_handler.get_actions_info(
                            current_node, [first_action]
                        )
                        if action_info is None or action_info.time_used < 0:
                            log.warning(
                                f"'{candidate.subtask.name}' fallback nav estimation failed. Cost=LARGE_NUMBER."
                            )
                            return LARGE_NUMBER
                        nav_time = action_info.action_duration
                    else:
                        # First action is not NAVIGATE_TO, fallback is unreliable
                        log.warning(
                            f"Task '{candidate.subtask.name}': Fallback nav estimation skipped. First action ('{first_action}') is not NAVIGATE_TO. Cost=LARGE_NUMBER."
                        )
                        nav_time = 0.0  # LARGE_NUMBER 대신 0.0

            except Exception as e_fallback:
                log.warning(
                    f"'{candidate.subtask.name}' fallback nav estimation error: {e_fallback}. Cost=LARGE_NUMBER."
                )
                return LARGE_NUMBER
        except (ValueError, TypeError, Exception) as e:
            log.warning(
                f"'{candidate.subtask.name}' nav time estimation error: {e}. Cost=LARGE_NUMBER."
            )
            return LARGE_NUMBER  # Return high cost if nav estimation fails

        navigation_cost = self.alpha * nav_time

        # --- (B) 긴급도 비용 ---
        urgency_term = 0.0  # Default urgency term (no urgency if no deadline)
        slack_val = float("inf")  # Default slack

        if candidate.deadline and candidate.deadline.due_date < float("inf"):
            deadline_time = candidate.deadline.due_date
            deadline_sub_name = (
                candidate.deadline.subtask_name
            )  # Task that sets the deadline
            try:
                # 1. 후보 작업 자체의 예상 시간 계산
                estimated_duration_candidate = 0.0
                if actual_duration is not None and actual_duration >= 0:
                    estimated_duration_candidate = actual_duration
                    log.debug(
                        f"Using provided actual_duration for {candidate_subtask.name}: {actual_duration:.2f}"
                    )
                else:
                    # Reuse existing logic to estimate candidate duration
                    sub_duration_info = self.action_handler.get_actions_info(
                        current_node, candidate_subtask.execution.primitive_actions
                    )
                    if (
                        sub_duration_info is None or sub_duration_info.time_used < 0
                    ):  # Check for negative time too
                        log.warning(
                            f"'{candidate_subtask.name}' duration estimation failed. Returning LARGE_NUMBER cost."
                        )
                        return LARGE_NUMBER
                    estimated_duration_candidate = sub_duration_info.time_used

                # --- NEW: Estimate time needed for tasks *between* candidate and deadline task ---
                time_needed_for_intermediate_tasks = 0.0
                # Check if deadline task exists and is different from candidate
                if deadline_sub_name and deadline_sub_name != candidate_subtask.name:
                    constraints = current_node.state.constraints
                    if constraints.has_node(
                        candidate_subtask.name
                    ) and constraints.has_node(deadline_sub_name):
                        try:
                            # Find all simple paths (no cycles) between candidate end and deadline start
                            # This can be computationally expensive! Consider optimizing (e.g., critical path).
                            # --- 주석 추가: 잠재적 성능 병목 ---
                            # NOTE: Calculating all simple paths can be computationally expensive
                            # for complex graphs. Consider optimization (e.g., using critical path estimation)
                            # if performance becomes an issue.
                            all_paths = list(
                                nx.all_simple_paths(
                                    constraints,
                                    source=candidate_subtask.name,
                                    target=deadline_sub_name,
                                )
                            )

                            max_intermediate_time = 0.0
                            if not all_paths:
                                log.debug(
                                    f"No direct constraint path found between '{candidate_subtask.name}' and deadline task '{deadline_sub_name}'. Intermediate time = 0."
                                )
                            else:
                                log.debug(
                                    f"Found {len(all_paths)} paths between '{candidate_subtask.name}' and '{deadline_sub_name}'. Calculating max duration."
                                )
                                for path in all_paths:
                                    current_path_time = 0.0
                                    # Sum durations of intermediate nodes in the path
                                    # Path includes start and end node, so iterate from index 1 to N-2
                                    for i in range(1, len(path) - 1):
                                        intermediate_sub_name = path[i]
                                        # Find the Subtask object for the intermediate node
                                        intermediate_sub = next(
                                            (
                                                sub
                                                for sub in remaining_subtasks
                                                + [candidate.subtask]
                                                if sub.name == intermediate_sub_name
                                            ),
                                            None,
                                        )
                                        if intermediate_sub:
                                            # Use _estimate_remaining_cost logic (or similar) to get its duration
                                            # This avoids duplicating estimation logic. Call helper?
                                            # Simplified version: use agent or default
                                            est_dur = DEFAULT_SUBTASK_DURATION_ESTIMATE
                                            if self.agent:
                                                try:
                                                    est_dur, _ = (
                                                        self.agent._get_prior_estimate(
                                                            intermediate_sub.name
                                                        )
                                                    )
                                                except Exception:
                                                    pass  # Ignore agent errors here
                                            elif (
                                                intermediate_sub.duration
                                                and intermediate_sub.duration.interval
                                                is not None
                                            ):
                                                try:
                                                    est_dur = float(
                                                        intermediate_sub.duration.interval
                                                    )
                                                except:
                                                    pass
                                            current_path_time += max(
                                                0, est_dur
                                            )  # Add non-negative duration

                                    max_intermediate_time = max(
                                        max_intermediate_time, current_path_time
                                    )

                                time_needed_for_intermediate_tasks = (
                                    max_intermediate_time
                                )
                                log.debug(
                                    f"Estimated max intermediate task time between '{candidate_subtask.name}' and '{deadline_sub_name}': {time_needed_for_intermediate_tasks:.2f}"
                                )

                        except nx.NetworkXNoPath:
                            log.debug(
                                f"No path found between '{candidate_subtask.name}' and '{deadline_sub_name}' in constraint graph."
                            )
                        except nx.NodeNotFound:
                            log.warning(
                                f"Node '{candidate_subtask.name}' or '{deadline_sub_name}' not found in constraint graph for intermediate time calculation."
                            )
                        except Exception as e_path:
                            log.error(
                                f"Error calculating intermediate task time: {e_path}",
                                exc_info=True,
                            )

                # 2. 슬랙 계산 (후보 작업 + 중간 작업 시간 고려)
                time_remaining_until_deadline = deadline_time - current_time
                # Total time needed includes candidate itself and longest path of intermediate tasks
                time_needed = (
                    estimated_duration_candidate + time_needed_for_intermediate_tasks
                )
                slack_val = time_remaining_until_deadline - time_needed

                log.debug(
                    f"Slack Calc: DeadlineTime={deadline_time:.2f}, CurrentTime={current_time:.2f}, "
                    f"Remaining={time_remaining_until_deadline:.2f} | "
                    f"TimeNeeded (Candidate={estimated_duration_candidate:.2f} + Intermediate={time_needed_for_intermediate_tasks:.2f}) = {time_needed:.2f} | "
                    f"Slack={slack_val:.2f}"
                )

                # 3. 긴급도 항 계산 (음수 슬랙 처리, 역제곱근 사용 - 타당성 검토 필요)
                if slack_val <= EPSILON:
                    # ... (High urgency penalty logging) ...
                    urgency_term = (
                        -LARGE_NUMBER
                    )  # 매우 큰 음수 값 (비용 함수에서는 큰 양수 페널티)
                else:
                    # Use reciprocal square root for smoother penalty increase
                    urgency_term = -1.0 / math.sqrt(slack_val + EPSILON)

            except (ValueError, Exception) as e:  # ValueError 포함
                log.error(
                    f"'{candidate_subtask.name}' slack calculation error: {e}. Cost=LARGE_NUMBER."
                )
                return LARGE_NUMBER

        urgency_cost = self.beta * urgency_term

        # --- (C) 남은 작업량 비용 ---
        remaining_work_estimate = self._estimate_remaining_cost(remaining_subtasks)
        remaining_work_cost = self.zeta * remaining_work_estimate

        # --- (D) 최종 비용 계산 ---
        total_cost = navigation_cost + urgency_cost + remaining_work_cost

        # --- 로깅 ---
        log.debug(f"Heuristic Cost Breakdown: '{candidate_subtask.name}'")
        log.debug(
            f"  Nav Cost ({self.alpha:.2f} * {nav_time:.2f}): {navigation_cost:.3f}"
        )
        log.debug(
            f"  Urgency Cost ({self.beta:.2f} * {urgency_term:.3f}): {urgency_cost:.3f} (Slack: {slack_val:.2f})"
        )
        log.debug(
            f"  Remaining Work Cost ({self.zeta:.2f} * est={remaining_work_estimate:.2f}): {remaining_work_cost:.3f}"
        )
        log.debug(f"  ==> Total Cost: {total_cost:.4f}")

        # --- 실행 불가능 처리 (휴리스틱 레벨) ---
        # urgency_term이 매우 낮은 값(-LARGE_NUMBER)이면 LARGE_NUMBER 비용 반환
        if urgency_term <= -LARGE_NUMBER + EPSILON:
            log.warning(
                f"'{candidate_subtask.name}' deemed highly unpromising due to very low/negative slack ({slack_val:.2f}). Cost=LARGE_NUMBER."
            )
            return LARGE_NUMBER  # 높은 비용 반환

        # --- MODIFIED: Justification for LARGE_NUMBER ---
        # Return LARGE_NUMBER if any sub-calculation failed (already handled above)
        # or if urgency cost itself is LARGE_NUMBER (due to negative slack).
        if total_cost >= LARGE_NUMBER:
            log.warning(
                f"Returning LARGE_NUMBER cost for '{candidate_subtask.name}' due to calculation failure or extreme urgency."
            )
            return LARGE_NUMBER

        # Sanity check for negative cost (should not happen with current components)
        if total_cost < 0:
            log.error(
                f"Calculated negative heuristic cost ({total_cost:.4f}) for '{candidate_subtask.name}'. Returning 0."
            )
            return 0.0

        return total_cost

    def _estimate_remaining_cost(self, remaining_subtasks: list["Subtask"]) -> float:
        """
        Estimates the remaining workload based on the sum of estimated durations.
        NOTE: This is a very rough estimate, ignoring dependencies and parallelism.
        """
        # --- NOTE: Dependency on Agent Knowledge ---
        # This estimation relies on duration estimates, potentially from the Agent.
        # The accuracy of the Agent's knowledge (prior estimates) directly impacts
        # the quality of this remaining work cost component.
        if not remaining_subtasks:
            return 0.0

        total_estimated_duration = 0.0
        for sub in remaining_subtasks:
            duration_value = DEFAULT_SUBTASK_DURATION_ESTIMATE  # 기본값 사용
            duration_source = "default"

            # 1. Try using Agent's knowledge if available
            if self.agent:
                try:
                    # Use Agent's method to get prior, handling similarity/defaults internally
                    # Assuming Agent has _get_prior_estimate method accessible
                    # Pass the subtask name for potential similarity matching inside agent
                    prior_mean, _ = self.agent._get_prior_estimate(sub.name)
                    duration_value = prior_mean
                    duration_source = "agent"
                except Exception as e_agent:
                    log.warning(
                        f"Failed to get estimate from Agent for '{sub.name}': {e_agent}. Falling back."
                    )

            # 2. If Agent didn't provide value, try using subtask.duration.interval
            if (
                duration_source == "default"
                and sub.duration
                and sub.duration.interval is not None
            ):
                try:
                    interval_val = float(sub.duration.interval)
                    if interval_val >= 0:
                        duration_value = interval_val
                        duration_source = "subtask_interval"
                    else:
                        log.warning(
                            f"Subtask '{sub.name}' has negative duration.interval. Using {duration_source} estimate ({duration_value:.2f})."
                        )
                except (ValueError, TypeError):
                    pass  # Keep default if interval is not numeric

            # Log the source of the duration used if not default
            # if duration_source != "default":
            #      log.debug(f"Using '{duration_source}' duration ({duration_value:.2f}) for '{sub.name}' remaining cost.")

            total_estimated_duration += duration_value

        log.debug(
            f"Estimated remaining cost (sum of durations): {total_estimated_duration:.2f} for {len(remaining_subtasks)} tasks"
        )
        return total_estimated_duration
