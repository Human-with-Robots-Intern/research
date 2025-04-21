import copy
import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from core.dataclass import Candidate, Deadline, SimulationNode, TimeSlot
from core.task import Subtask

# from scheduler.action_handler import ActionHandler
from src.utils.config import EPSILON, LARGE_NUMBER, LOG_ROUND

# [추가됨] TYPE_CHECKING 블록 내에서만 ActionHandler 임포트
if TYPE_CHECKING:
    from scheduler.action_handler import ActionHandler

log = logging.getLogger(__name__)

# Define a tolerance for critical task start time checks
CRITICAL_TIME_TOLERANCE = 0.05  # Example: 50ms tolerance, adjust as needed


class ConstraintHandler:

    def __init__(self, action_handler: "ActionHandler"):
        """
        ConstraintHandler 초기화. ActionHandler 인스턴스를 주입받습니다.
        """
        self.action_handler = action_handler
        log.debug("ConstraintHandler initialized with ActionHandler.")

    def get_time_slots(
        self, subtask_name: str, constraints: DiGraph, direction: str
    ) -> List[TimeSlot]:
        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        if not edges:
            return []

        time_slots = []

        for u, v, data in edges:
            interval = data.get("info", {}).get("Interval", 0.0)
            is_crit = data.get("info", {}).get("IsCritical", False)
            linked_subtask = v if direction == "out" else u

            time_slots.append(TimeSlot(float(interval), is_crit, linked_subtask))
        return time_slots

    def get_feasible_candidates(
        self,
        curr_node: SimulationNode,
    ) -> Tuple[List[Candidate], List[Candidate]]:
        """
        Determines feasible and not-yet-feasible candidates from the current state.
        Adjusts start times based on navigation estimates and checks against current time.
        """
        feasible_candidates: List[Candidate] = []
        not_yet_candidates: List[Candidate] = []

        current_time = curr_node.state.current_time
        remaining_subtasks = curr_node.state.remaining_subtasks
        log.debug(
            f"Checking {len(remaining_subtasks)} remaining subtasks at time {current_time:.2f}"
        )

        for sub in remaining_subtasks:
            # Check if the subtask is ready based on predecessor constraints
            # Returns: (logical_start_time, is_critical, predecessor_status)
            logical_start_time, is_critical, pred_status = self.get_earliest_start_time(
                curr_node, sub
            )

            # --- Filter based on predecessor status ---
            if pred_status == "FAILED":
                log.warning(
                    f"Subtask '{sub.name}' skipped: Predecessor check indicates failure or conflict."
                )
                continue  # Skip candidate if predecessors failed or constraints conflict
            if pred_status is None:  # Not 'COMPLETED' or 'FAILED'
                log.debug(
                    f"Subtask '{sub.name}' not ready yet (predecessors not completed)."
                )
                continue  # Skip candidate if predecessors not yet finished

            # --- Estimate Navigation Time (using dedicated ActionHandler method) ---
            estimated_nav_time = 0.0
            nav_estimation_failed = False
            try:
                # Call the dedicated (assumed improved) navigation time estimation method
                # This method should ideally consider the task type, target location,
                # and potentially multiple initial actions or agent state.
                estimated_nav_time = self.action_handler.get_navigation_time_estimate(
                    curr_node, sub
                )

                if estimated_nav_time == float("inf"):
                    log.warning(
                        f"Task '{sub.name}': Navigation deemed infeasible by ActionHandler."
                    )
                    nav_estimation_failed = True
                elif estimated_nav_time < 0:
                    log.warning(
                        f"Task '{sub.name}': Received negative nav estimate ({estimated_nav_time:.2f}). Using 0."
                    )
                    estimated_nav_time = 0.0

                log.debug(
                    f"Task '{sub.name}': Estimated nav/setup time from ActionHandler: {estimated_nav_time:.2f}s"
                )

            except AttributeError:
                # Fallback if the dedicated method doesn't exist on ActionHandler yet
                log.warning(
                    f"ActionHandler does not have 'get_navigation_time_estimate'. Falling back to simulating first action."
                )
                try:
                    first_action = sub.execution.primitive_actions[0]
                    sim_node_for_nav = copy.deepcopy(curr_node)
                    action_info = self.action_handler.get_actions_info(
                        sim_node_for_nav, [first_action]
                    )
                    if action_info is None or action_info.time_used < 0:
                        log.warning(
                            f"Task '{sub.name}': Fallback nav estimation failed. Assuming infinite time."
                        )
                        nav_estimation_failed = True
                    else:
                        estimated_nav_time = action_info.action_duration
                        log.debug(
                            f"Task '{sub.name}': Fallback estimated nav/setup time: {estimated_nav_time:.2f}s"
                        )
                except Exception as e_fallback:
                    log.error(
                        f"Task '{sub.name}': Error during fallback nav estimation: {e_fallback}. Assuming infinite time.",
                        exc_info=True,
                    )
                    nav_estimation_failed = True

            except Exception as e:
                log.error(
                    f"Task '{sub.name}': Error during navigation time estimation: {e}. Assuming infinite time.",
                    exc_info=True,
                )
                nav_estimation_failed = True

            # --- Calculate Adjusted Start Time ---
            if nav_estimation_failed:
                adjusted_start_time_val = float("inf")
                log.warning(
                    f"Task '{sub.name}' has infeasible navigation, setting adjusted_start_time to infinity."
                )
            else:
                adjusted_start_time_val = logical_start_time - estimated_nav_time

            log.debug(
                f"Task '{sub.name}': LogicalEST={logical_start_time:.2f}, EstNavTime={estimated_nav_time:.2f}, AdjustedEST={adjusted_start_time_val:.2f}"
            )

            # Create the candidate object
            candidate_obj = Candidate(
                subtask=sub,
                is_critical=is_critical,
                adjusted_start_time=adjusted_start_time_val,
                logical_start_time=logical_start_time,  # Keep logical time for reference
            )

            # --- Determine Feasibility based on Adjusted Start Time ---
            # Check if the agent can start now or needs to wait

            # Using Adjusted EST for feasibility check
            check_time = adjusted_start_time_val

            # Add a small epsilon for floating point comparisons (used below for non-critical)
            if is_critical:
                # --- MODIFIED Critical Check ---
                # Critical tasks MUST start close to their adjusted start time
                time_diff = current_time - check_time
                if abs(time_diff) < CRITICAL_TIME_TOLERANCE:
                    log.debug(
                        f"Critical task '{sub.name}' is feasible now (Diff: {time_diff:.3f}, Tol: {CRITICAL_TIME_TOLERANCE})."
                    )
                    feasible_candidates.append(candidate_obj)
                elif (
                    time_diff < 0
                ):  # current_time < check_time - CRITICAL_TIME_TOLERANCE => Need to wait
                    log.debug(
                        f"Critical task '{sub.name}' is not yet ready (needs wait). AdjustedEST: {check_time:.2f}"
                    )
                    not_yet_candidates.append(candidate_obj)
                else:  # current_time > check_time + CRITICAL_TIME_TOLERANCE
                    # Critical start time window has passed!
                    log.error(  # Changed from CRITICAL to ERROR
                        f"MISSED CRITICAL START WINDOW for '{sub.name}'! "
                        f"Current Time: {round(current_time, LOG_ROUND)}, "
                        f"Required Start Window: ~{round(check_time, LOG_ROUND)} +/- {CRITICAL_TIME_TOLERANCE}. "
                        f"Difference: {time_diff:.3f}. Candidate is infeasible."
                    )
                    # Do not add to feasible or not_yet lists
            else:  # Non-critical tasks
                # Can start if current time is at or after the adjusted start time
                if current_time >= check_time - EPSILON:
                    log.debug(f"Non-critical task '{sub.name}' is feasible now.")
                    feasible_candidates.append(candidate_obj)
                else:  # Need to wait for non-critical start
                    log.debug(
                        f"Non-critical task '{sub.name}' is not yet ready (needs wait). AdjustedEST: {check_time:.2f}"
                    )
                    not_yet_candidates.append(candidate_obj)

        # Assign deadlines based on the next upcoming critical task among not_yet candidates
        # This modifies feasible_candidates in-place by adding deadline info
        feasible_candidates_with_deadlines = self._assign_deadlines(
            feasible_candidates, not_yet_candidates, curr_node
        )

        log.info(
            f"Found {len(feasible_candidates_with_deadlines)} feasible and {len(not_yet_candidates)} not-yet candidates."
        )
        return (feasible_candidates_with_deadlines, not_yet_candidates)

    def _assign_deadlines(
        self,
        feasible: List[Candidate],
        not_yet: List[Candidate],
        curr_node: SimulationNode,
    ) -> List[Candidate]:
        """
        Assigns deadlines to feasible candidates based on the earliest upcoming
        critical task found in the not_yet list.
        """
        # Find the earliest adjusted start time among upcoming critical tasks
        crit_candidates = [
            c for c in not_yet if c.is_critical and c.status != "MISSED_CRITICAL"
        ]
        crit_candidates.sort(
            key=lambda x: x.adjusted_start_time
        )  # Sort by adjusted start time

        if not crit_candidates:
            # No upcoming critical tasks in the 'not_yet' list
            deadline_time = float("inf")
            deadline_reason_subtask_name = "None"
        else:
            next_crit = crit_candidates[0]
            # The deadline is the adjusted start time of the next critical task
            deadline_time = next_crit.adjusted_start_time
            deadline_reason_subtask_name = next_crit.subtask.name
            log.debug(
                f"Next critical task '{deadline_reason_subtask_name}' sets deadline at AdjustedEST {deadline_time:.2f}"
            )

        # Assign the calculated deadline to all currently feasible candidates
        for c in feasible:
            c.deadline = Deadline(deadline_time, deadline_reason_subtask_name)
            log.debug(
                f"  Assigned deadline to feasible '{c.subtask.name}': Due={c.deadline.due_date:.2f} (due to next critical '{c.deadline.subtask_name}')"
            )

        # 6.3: 전역 데드라인 고려
        global_deadline = curr_node.state.global_deadline
        final_deadline_time = deadline_time
        if global_deadline is not None:
            if deadline_time == float("inf"):
                final_deadline_time = global_deadline
                deadline_reason_subtask_name = "Global"
                log.debug(
                    f"No upcoming critical task, using global deadline: {global_deadline:.2f}"
                )
            elif deadline_time > global_deadline:
                final_deadline_time = global_deadline
                original_reason = deadline_reason_subtask_name
                deadline_reason_subtask_name = (
                    f"Global (earlier than {original_reason})"
                )
                log.debug(
                    f"Global deadline {global_deadline:.2f} is earlier than next critical task deadline {deadline_time:.2f}. Using global."
                )
            # else: critical deadline is earlier than global, use critical

        for c in feasible:
            c.deadline = Deadline(final_deadline_time, deadline_reason_subtask_name)
            log.debug(
                f"  Assigned deadline to feasible '{c.subtask.name}': Due={c.deadline.due_date:.2f} (due to next critical '{c.deadline.subtask_name}')"
            )

        return feasible

    def get_earliest_start_time(
        self, curr_node: SimulationNode, sub: Subtask
    ) -> Tuple[Optional[float], bool, Optional[str]]:
        """
        Calculates the logical earliest start time for subtask 'sub' based on
        predecessor completion times and constraint intervals.
        Checks for predecessor failures and constraint conflicts.

        Returns:
            Tuple[Optional[float], bool, Optional[str]]:
            - logical_start_time (float or None): Earliest time based on constraints, None if not ready or conflict.
            - is_critical (bool): True if determined by a critical constraint.
            - predecessor_status (str or None): "COMPLETED", "FAILED", None (if not finished).
        """
        curr_constraints = curr_node.state.constraints

        # --- MODIFIED: Add cycle check before using the graph ---
        if not nx.is_directed_acyclic_graph(curr_constraints):
            log.error(
                f"CONSTRAINT ERROR: Cycle detected in the constraint graph for state at time {curr_node.state.current_time:.2f}! "
                f"Cannot reliably calculate earliest start time for '{sub.name}'. Check constraint update logic."
            )
            # Depending on desired behavior, could return (None, False, "FAILED") or raise an exception.
            # Returning FAILED status for now.
            return (None, False, "FAILED")

        # Create a map for faster lookup of completed task entries
        completed_subtasks_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_subtasks
        }

        # Check if the subtask exists in the graph
        if sub.name not in curr_constraints:
            # Handle tasks not in graph (e.g., 'Init' or dynamically added tasks without preds)
            log.warning(
                f"Subtask '{sub.name}' not found in constraint graph. Assuming ready at time 0."
            )
            # 'Init' task has no predecessors, others might implicitly start at 0
            return (
                (0.0, False, "COMPLETED") if sub.name != "Init" else (0.0, False, None)
            )

        # Get incoming edges (predecessors)
        in_edges = list(curr_constraints.in_edges(sub.name, data=True))
        if not in_edges:
            # No predecessors, can start immediately
            log.debug(f"Subtask '{sub.name}' has no predecessors. Ready at time 0.")
            return (0.0, False, "COMPLETED")

        critical_times = (
            []
        )  # Store potential start times dictated by critical constraints
        non_critical_earliest_start = (
            0.0  # Earliest start time based on non-critical constraints
        )
        all_predecessors_finished = True
        any_predecessor_failed = False

        for pred_name, _, edge_data in in_edges:
            info = edge_data.get("info", {})
            interval = float(
                info.get("Interval", 0.0)
            )  # Time gap after predecessor ends
            is_crit = info.get(
                "IsCritical", False
            )  # Is this a critical timing constraint?

            # Find the completion entry for the predecessor
            pred_entry = completed_subtasks_map.get(pred_name)

            if not pred_entry:
                # If any predecessor is not yet completed
                all_predecessors_finished = False
                log.debug(
                    f"Predecessor '{pred_name}' for '{sub.name}' not completed yet."
                )
                # Continue checking other predecessors for potential failures, but cannot determine start time yet
                continue  # Cannot calculate start time if a predecessor is not finished

            # --- Check predecessor execution status ---
            # Use getattr for safe access to potentially missing attribute
            pred_status = getattr(pred_entry.subtask, "execution_status", None)
            # If status attribute is missing, log warning and assume success for now
            if pred_status is None:
                log.warning(
                    f"Predecessor '{pred_name}' for '{sub.name}' completed but lacks 'execution_status'. Assuming success."
                )
                pred_status = True  # Default assumption

            if pred_status is False:
                # If any predecessor failed, this subtask cannot run
                any_predecessor_failed = True
                log.warning(
                    f"Predecessor '{pred_name}' for '{sub.name}' FAILED execution. '{sub.name}' cannot start."
                )
                # No need to check further predecessors if one failed
                break  # Exit the loop early

            # --- Calculate potential start time based on this predecessor ---
            pred_end_time = pred_entry.end_time
            candidate_start_time = pred_end_time + interval

            if is_crit:
                critical_times.append(candidate_start_time)
            else:
                # For non-critical, the task can only start after the latest predecessor finishes
                non_critical_earliest_start = max(
                    non_critical_earliest_start, candidate_start_time
                )

        # --- Determine final result based on checks ---
        if any_predecessor_failed:
            # If any predecessor failed, return FAILED status
            return (None, False, "FAILED")

        if not all_predecessors_finished:
            # If predecessors are okay so far but not all finished, return None status
            return (None, False, None)

        # --- Check for conflicts if all predecessors completed successfully ---
        final_start_time = 0.0
        is_final_critical = False

        if critical_times:
            # If there are critical constraints, find the earliest and latest required start times
            earliest_critical_time = min(critical_times)
            latest_critical_time = max(critical_times)

            # Check for conflicting critical times
            if abs(earliest_critical_time - latest_critical_time) > EPSILON:
                log.error(
                    f"CONSTRAINT CONFLICT for '{sub.name}': Multiple distinct critical start times calculated: {critical_times}. "
                    f"Check constraint graph logic. Proceeding with the LATEST required critical time: {latest_critical_time:.2f}"
                )
                # Policy: Use the latest required critical time in case of conflict.
                final_start_time = latest_critical_time
            else:
                # All critical times agree
                final_start_time = (
                    earliest_critical_time  # Or latest_critical_time, they are the same
                )

            is_final_critical = (
                True  # Mark as critical if any critical constraint exists
            )

            # Check if the (latest) critical time conflicts with non-critical time
            # The final start time must be >= the latest non-critical requirement
            if final_start_time < non_critical_earliest_start - EPSILON:
                log.error(
                    f"CONSTRAINT CONFLICT for '{sub.name}': Required critical start time {final_start_time:.2f} "
                    f"is EARLIER than latest non-critical requirement {non_critical_earliest_start:.2f}. "
                    f"Check constraint graph logic. Proceeding with the LATEST non-critical requirement time: {non_critical_earliest_start:.2f}"
                )
                # Policy: Respect the non-critical dependency, use the later time.
                final_start_time = non_critical_earliest_start
                # Keep is_final_critical = True because a critical constraint *was* involved.
        else:
            # No critical constraints, determined by latest non-critical predecessor
            final_start_time = non_critical_earliest_start
            is_final_critical = False

        log.debug(
            f"Subtask '{sub.name}' ready at {final_start_time:.2f} (Critical: {is_final_critical})"
        )
        return (final_start_time, is_final_critical, "COMPLETED")
