from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from src.models.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import LARGE_NUMBER, constants
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    NAV_STEP_DURATION,
    PLACE_ACTION_DURATION,
    TOGGLE_ACTION_DURATION,
)

if TYPE_CHECKING:
    from src.models.task import Subtask
    from src.scheduler.action_handler import ActionHandler

log = create_module_logger(__name__, True, logging.DEBUG)


class HeuristicManager:
    """
    Manages the calculation of heuristic costs for scheduling candidates.
    Evaluates immediate costs (navigation, urgency) and future costs (remaining workload).
    """

    def __init__(self, action_handler: "ActionHandler"):
        self.action_handler = action_handler
        self.alpha = constants.ALPHA_HEURISTIC
        self.beta = constants.BETA_HEURISTIC
        self.gamma = constants.GAMMA_HEURISTIC
        log.info(
            f"HeuristicManager initialized with weights: alpha={self.alpha}, beta={self.beta}, gamma={self.gamma}"
        )

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        all_candidates: List[Candidate],
    ) -> Tuple[int, float, float]:
        """
        Calculates the heuristic cost for a given candidate subtask.
        Returns: (risk_level, total_heuristic_cost, collateral_penalty)
        """
        if candidate.subtask.name.startswith("Wait for"):
            return self._calculate_wait_heuristic(
                current_node, candidate, all_candidates
            )

        # 1. Calculate Urgency & Risk
        risk_level, urgency_cost = self._calculate_candidate_risk_and_urgency(
            current_node, candidate
        )

        # 2. Calculate Future Workload Cost
        remaining_work_cost, cp_dur, mst_time = self._calculate_remaining_work_cost(
            current_node, candidate
        )

        # 3. Check Collateral Damage (Resource Contention)
        # Identify if this task starts a critical chain (Interval ~0) that locks resources
        chain_duration, chain_members = self._get_chain_info(
            current_node, candidate.subtask
        )
        collateral_penalty = self._check_collateral_damage(
            current_node, candidate, chain_duration, chain_members, all_candidates
        )

        # [Revised 251216] Promote high collateral penalty to Risk Level.
        # If a candidate causes a massive delay to others (violation likely),
        # it should be treated as a Risk, not just a high cost that can be washed out in lookahead.
        if collateral_penalty >= 5000.0:
            risk_level = max(risk_level, 2)
            log.warning(
                f"  [Risk Promotion] Candidate '{candidate.subtask.name}' has high collateral penalty ({collateral_penalty:.0f}). Promoting to Risk Level 2."
            )

        # [NEW 251216] Interval Creation Bonus
        # Encourage tasks that open up a large time window (Interval) for interleaving.
        # e.g., Start Coffee Machine -> (100s Interval) -> Retrieve Coffee
        # The agent is free during this interval, so starting it early is beneficial.
        interval_bonus = self._get_interval_creation_bonus(current_node, candidate)

        # 4. Final Weighted Sum
        total_heuristic_cost = (
            self.beta * urgency_cost + self.gamma * remaining_work_cost
        )

        step_adjustment = collateral_penalty - interval_bonus

        log.info(
            f"  Heuristic for '{candidate.subtask.name}': Risk={risk_level}, "
            f"Urg({self.beta:.1f}*{urgency_cost:.2f})={self.beta * urgency_cost:.2f} (Slack={slack:.2f}), "
            f"RemWork({self.gamma:.1f}*Rem[{cp_dur:.2f}+{mst_time:.2f}])={self.gamma * remaining_work_cost:.2f}, "
            f"Collateral={collateral_penalty:.2f}, "
            f"IntervalBonus={interval_bonus:.2f}"
        )
        log.info(
            f"  => Total Heuristic Cost for '{candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return risk_level, total_heuristic_cost, step_adjustment

    def _get_interval_creation_bonus(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """
        Calculates a bonus score if the candidate initiates a critical interval.
        Higher bonus for longer intervals, encouraging early execution to open up interleaving windows.
        """
        bonus = 0.0
        constraints = current_node.state.constraints
        task_name = candidate.subtask.name

        if not constraints.has_node(task_name):
            return 0.0

        for _, _, data in constraints.out_edges(task_name, data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval", 0.0) > constants.EPSILON:
                interval = info.get("Interval")
                # Bonus formula: Base weight * Interval duration
                # We want this to be significant enough to overcome minor collateral penalties or delays.
                # e.g., Interval 100s * 10.0 = 1000.0 Bonus.
                bonus += interval * 10.0
                log.debug(
                    f"  [Interval Bonus] '{task_name}' starts interval of {interval:.2f}s. Bonus += {interval * 10.0:.2f}"
                )

        return bonus

    # ========================================================================
    # Core Logic: Urgency & Risk Calculation
    # ========================================================================

    def _calculate_candidate_risk_and_urgency(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[int, float, float]:
        """
        Calculates risk and urgency based on slack and volume pressure.
        """
        if not self._has_valid_deadline(candidate):
            return 0, 0.0, 0.0

        current_time = current_node.state.current_time
        deadline = candidate.scheduling_due.due_date

        # 1. Calculate Slack
        total_time_needed = self._estimate_total_time_needed(current_node, candidate)
        time_available = deadline - current_time
        slack = time_available - total_time_needed

        # 2. Map Slack to Base Risk & Cost
        risk_level, urgency_cost = self._map_slack_to_risk_and_cost(slack)

        # 3. Apply Volume Pressure (if not already violated)
        if risk_level < 2:
            pass
            # risk_level, urgency_cost = self._apply_volume_pressure(
            #     current_node, candidate, deadline, risk_level, urgency_cost
            # )

        log.info(
            f"  Urgency for '{candidate.subtask.name}': Due={deadline:.2f}, "
            f"Need={total_time_needed:.2f}, Avail={time_available:.2f} => Slack={slack:.2f}"
        )

        return (risk_level, urgency_cost)

    def _has_valid_deadline(self, candidate: Candidate) -> bool:
        return candidate.scheduling_due and candidate.scheduling_due.due_date != float(
            "inf"
        )

    def _estimate_total_time_needed(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Estimates time needed for nav + interaction + lookahead return trip."""
        nav_time = candidate.estimated_first_nav_duration or 0.0
        interact_time = self._get_estimated_pure_interaction_time(candidate.subtask)

        # [Fix] If the deadline is for the candidate itself (Start Time Constraint),
        # we only need to arrive (Nav) by the deadline, not finish.
        is_target_self = (
            candidate.scheduling_due
            and candidate.scheduling_due.due_related_sub_name == candidate.subtask.name
        )

        if is_target_self:
            total_time = nav_time
        else:
            total_time = nav_time + interact_time

        # Lookahead: Check if we need to return to a future critical task location
        future_crit_name = candidate.scheduling_due.due_related_sub_name
        if future_crit_name and future_crit_name != candidate.subtask.name:
            lookahead_time = self._calculate_lookahead_nav_time(
                current_node, candidate, future_crit_name
            )
            total_time += lookahead_time

        return total_time

    def _calculate_lookahead_nav_time(
        self, current_node: SimulationNode, candidate: Candidate, future_crit_name: str
    ) -> float:
        future_subtask = next(
            (
                t
                for t in current_node.state.remaining_subtasks
                if t.name == future_crit_name
            ),
            None,
        )
        if not future_subtask:
            return 0.0

        current_target_pos = self._get_task_interaction_location(
            candidate.subtask, current_node.state.scene_positions
        ) or tuple(current_node.state.scene_positions.get("agent", (0, 0, 0)))

        future_target_pos = self._get_task_interaction_location(
            future_subtask, current_node.state.scene_positions
        )

        return self._estimate_navigation_time_between_positions(
            current_target_pos, future_target_pos
        )

    def _map_slack_to_risk_and_cost(self, slack: float) -> Tuple[int, float]:
        """Maps slack value to risk level and cost using revised 251216 logic."""

        if slack >= -constants.TIMING_TOLERANCE_ABS:
            # Safe: Linear penalty (Lower slack -> Lower cost -> Higher Priority)
            # [Revised 251216] Reduce the weight of slack cost significantly.
            # Previously, large slack (safe task) resulted in high cost, discouraging early execution of non-urgent tasks.
            # We want to encourage "doing work" over "waiting" even if the work is not urgent.
            # We keep a small positive slope to prefer tighter deadlines (EDF) among safe tasks.
            return 0, slack
        else:
            # Violation: Huge penalty.
            return 2, 10000.0 + abs(slack)

    def _apply_volume_pressure(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        deadline: float,
        current_risk: int,
        current_cost: float,
    ) -> Tuple[int, float]:
        """Adds cost based on volume slack (future workload vs time available)."""
        future_crit_name = candidate.scheduling_due.due_related_sub_name
        if not future_crit_name:
            return current_risk, current_cost

        # Determine volume slack.
        # We ignore the is_violation boolean since we check tolerance explicitly.
        _, v_slack = self._calculate_volume_risk(
            current_node, candidate, deadline, future_crit_name
        )

        if v_slack >= 0:
            # Safe zone: Reward high slack (Low Cost).
            # Cost represents "Equivalent Time Penalty" for squeezing the schedule.
            # Using 100.0 base: v_slack=20s -> Cost=4.7s. (Better than Waiting 10s)
            # v_slack=0s -> Cost=100s. (Avoid if possible)
            vol_pressure_cost = 100.0 / (v_slack + 1.0)
            return current_risk, current_cost + vol_pressure_cost

        elif v_slack >= -constants.TIMING_TOLERANCE_ABS:
            # Tolerance zone: Negative slack but valid (Accepted).
            # We assign Risk 0 (Safe) but add penalty to prefer positive slack.
            # Smooth transition from 0 slack (Cost ~100).
            return current_risk, current_cost + 100.0 + abs(v_slack) * 10.0

        else:
            # Violation zone
            log.warning(
                f"  [Volume Risk] Candidate {candidate.subtask.name} causes violation! "
                f"VolSlack: {v_slack:.2f}"
            )
            return 2, current_cost + 10000.0 + abs(v_slack) * 100.0

    # ========================================================================
    # Wait Heuristic
    # ========================================================================

    def _calculate_wait_heuristic(
        self,
        current_node: SimulationNode,
        wait_candidate: Candidate,
        all_candidates: List[Candidate],
    ) -> Tuple[int, float, float]:
        """Calculates heuristic for 'Wait' action by delegating to target task logic."""
        target_task_name = wait_candidate.subtask.name.replace("Wait for ", "")
        target_candidate = next(
            (cand for cand in all_candidates if cand.subtask.name == target_task_name),
            None,
        )

        risk_level = 0
        wait_urgency_cost = 0.0

        # Wait inherits urgency from its target
        if target_candidate:
            risk_level, wait_urgency_cost = self._calculate_candidate_risk_and_urgency(
                current_node, target_candidate
            )

        # Calculate Remaining Work
        remaining_work_cost, cp_dur, mst_time = self._calculate_remaining_work_cost(
            current_node, wait_candidate
        )

        # [Check Collateral Damage for Wait]
        # Wait effectively blocks resources for (WaitTime + TargetChainTime)
        collateral_penalty = 0.0

        wait_duration = 0.0
        if wait_candidate.subtask.duration and wait_candidate.subtask.duration.interval:
            wait_duration = wait_candidate.subtask.duration.interval

        if target_candidate:
            target_chain_duration, target_chain_members = self._get_chain_info(
                current_node, target_candidate.subtask
            )

            # The robot is effectively "busy" (waiting or doing chain) from NOW until (Wait + NavToTarget + Chain)
            target_nav = target_candidate.estimated_first_nav_duration or 0.0
            total_block_time = wait_duration + target_nav + target_chain_duration

            collateral_penalty = self._check_collateral_damage(
                current_node,
                wait_candidate,  # Dummy candidate for context
                total_block_time,
                target_chain_members,
                all_candidates,
            )

        # [NEW] Wait Duration Penalty: Penalize wasting time
        # [Revised 251216] Increase wait penalty significantly.
        # Waiting is non-productive. If there is ANY productive task (Safe & Feasible),
        # the agent should prefer it over waiting.
        # Cost of 1.0 was too low compared to task execution costs (which include future work).
        # We increase it to 5.0 to make "Waiting 10s" cost 50 points, discouraging lazy waits.
        wait_time_penalty = wait_duration * 5.0

        total_heuristic_cost = (
            self.beta * wait_urgency_cost + self.gamma * remaining_work_cost
        )
        step_adjustment = collateral_penalty + wait_time_penalty

        log.info(
            f"  Heuristic for '{wait_candidate.subtask.name}': Risk={risk_level}, "
            f"WaitUrg({self.beta:.1f}*{wait_urgency_cost:.2f})={self.beta * wait_urgency_cost:.2f}, "
            f"RemWork({self.gamma:.1f}*Rem[{cp_dur:.2f}+{mst_time:.2f}])={self.gamma * remaining_work_cost:.2f}, "
            f"Collateral={collateral_penalty:.2f}, "
            f"WaitPenalty={wait_time_penalty:.2f}"
        )
        log.info(
            f"  => Total Heuristic Cost for '{wait_candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return risk_level, total_heuristic_cost, step_adjustment

    # ========================================================================
    # Helper Functions - Future Workload (Volume, CP, MST)
    # ========================================================================

    def _get_chain_info(
        self, current_node: SimulationNode, start_subtask: Subtask
    ) -> Tuple[float, Set[str]]:
        """
        Calculates total duration and members of a critical chain starting from start_subtask.
        A chain is defined by consecutive tasks with Interval <= EPSILON.
        """
        total_duration = self._get_estimated_pure_interaction_time(start_subtask)
        curr_name = start_subtask.name
        chain_members = {curr_name}

        while True:
            # Find immediate critical successor with zero interval
            next_name = None
            out_edges = current_node.state.constraints.out_edges(curr_name, data=True)
            for _, target, data in out_edges:
                info = data.get("info", {})
                # Check for critical chain link (IsCritical AND Interval ~ 0)
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) <= constants.EPSILON
                ):
                    next_name = target
                    break

            if next_name and next_name not in chain_members:
                chain_members.add(next_name)
                # Find the subtask object to get duration
                next_sub = next(
                    (
                        t
                        for t in current_node.state.remaining_subtasks
                        if t.name == next_name
                    ),
                    None,
                )
                if next_sub:
                    total_duration += self._get_estimated_pure_interaction_time(
                        next_sub
                    )
                    curr_name = next_name
                    continue
            break

        return total_duration, chain_members

    def _check_collateral_damage(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        chain_duration: float,
        chain_members: Set[str],
        all_candidates: List[Candidate],
    ) -> float:
        """
        Checks if executing the candidate (and its subsequent chain) would cause
        ANY OTHER urgent task to miss its deadline.
        Returns a high penalty cost if a violation is likely.
        """
        if not all_candidates:
            return 0.0

        current_time = current_node.state.current_time
        # Effective finish time of the entire blocking chain
        # We include candidate's nav time + total chain interaction time
        nav_duration = candidate.estimated_first_nav_duration or 0.0
        chain_finish_time = current_time + nav_duration + chain_duration

        penalty = 0.0

        # 1. Immediate Blocking Check
        for other in all_candidates:
            # Skip if 'other' is part of the chain (it will be handled sequentially)
            if other.subtask.name in chain_members:
                continue

            # Skip if 'other' has no deadline
            if not other.scheduling_due or other.scheduling_due.due_date == float(
                "inf"
            ):
                continue

            # Skip if 'other' is already finished (shouldn't happen in all_candidates but safe check)
            other_deadline = other.scheduling_due.due_date

            # Estimate if we can reach 'other' after chain finishes
            # Ideally we calculate Nav(ChainEnd -> Other).
            # For simplicity/speed, we use a heuristic or 0 nav (conservative).
            # If ChainFinish > OtherDeadline, it's a definite violation.

            # Using 0 nav is conservative (might miss violation if nav is needed).
            # But adding arbitrary nav might be wrong.
            # Let's assume minimal nav or just check strictly against deadline.

            if chain_finish_time > other_deadline + constants.TIMING_TOLERANCE_ABS:
                # VIOLATION!
                # We are busy until chain_finish_time, but 'other' needed to start by other_deadline.
                violation_amount = chain_finish_time - other_deadline
                log.warning(
                    f"  [Collateral Check] Candidate '{candidate.subtask.name}' (ChainDur: {chain_duration:.2f}) "
                    f"blocks '{other.subtask.name}' (Due: {other_deadline:.2f}). "
                    f"Finish: {chain_finish_time:.2f} > Due. Overrun: {violation_amount:.2f}"
                )
                # Apply huge penalty
                penalty += 10000.0 + violation_amount * 100.0

        # 2. Future Deadline Conflict Prediction (Lookahead)
        # Check if candidate creates a future constraint that conflicts with other tasks' generated deadlines.

        # Check if candidate triggers a future critical chain (e.g. Start Microwave -> Turn Off Microwave)
        cand_interact = self._get_estimated_pure_interaction_time(candidate.subtask)
        start_offset = current_time + nav_duration + cand_interact

        future_block_start, future_block_end = self._find_future_constraint_block(
            current_node, candidate.subtask, start_offset
        )

        if future_block_start is not None:
            # Check if this future block conflicts with deadlines generated by OTHER candidates
            for other in all_candidates:
                if (
                    other.subtask.name == candidate.subtask.name
                    or other.subtask.name in chain_members
                ):
                    continue

                # Estimate 'other' start time (delayed by candidate)
                # We assume 'other' starts ASAP after candidate finishes
                est_start_other = start_offset
                other_interact = self._get_estimated_pure_interaction_time(
                    other.subtask
                )

                # Predict 'other's future deadline block
                other_block_start, _ = self._find_future_constraint_block(
                    current_node, other.subtask, est_start_other + other_interact
                )

                if other_block_start is not None:
                    # other_block_start is the DEADLINE for the task after 'other'
                    # Does this deadline fall inside [future_block_start, future_block_end]?

                    # We use a tolerance buffer
                    buffer = constants.TIMING_TOLERANCE_ABS
                    if (
                        future_block_start - buffer
                        <= other_block_start
                        <= future_block_end + buffer
                    ):
                        violation = other_block_start - future_block_start
                        log.warning(
                            f"  [Future Conflict] '{candidate.subtask.name}' creates block [{future_block_start:.1f}, {future_block_end:.1f}] "
                            f"which conflicts with '{other.subtask.name}' -> Generates Deadline {other_block_start:.1f}"
                        )
                        # Reduced penalty to allow "lesser evil" choices
                        penalty += 2000.0 + abs(violation) * 50.0

        return penalty

    def _find_future_constraint_block(
        self, current_node: SimulationNode, start_subtask: Subtask, time_cursor: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Traces forward from start_subtask to find a future critical constraint block.
        Returns (block_start_time, block_end_time) absolute time.
        """
        constraints = current_node.state.constraints
        queue = [(start_subtask, time_cursor)]
        visited = {start_subtask.name}

        # BFS/DFS limited depth
        max_depth = 3
        depth = 0

        while queue and depth < max_depth:
            curr, curr_time = queue.pop(0)
            depth += 1

            for _, target, data in constraints.out_edges(curr.name, data=True):
                info = data.get("info", {})

                # Case 1: Critical Interval found -> This defines the block
                if info.get("IsCritical") and info.get("Interval") is not None:
                    interval = info.get("Interval")
                    block_start = curr_time + interval

                    # Get duration of the target chain
                    target_sub = next(
                        (
                            t
                            for t in current_node.state.remaining_subtasks
                            if t.name == target
                        ),
                        None,
                    )
                    if target_sub:
                        chain_dur, _ = self._get_chain_info(current_node, target_sub)
                        return block_start, block_start + chain_dur

                # Case 2: Zero-interval successor -> Follow it
                elif info.get("Interval", 0.0) <= constants.EPSILON:
                    target_sub = next(
                        (
                            t
                            for t in current_node.state.remaining_subtasks
                            if t.name == target
                        ),
                        None,
                    )
                    if target_sub and target_sub.name not in visited:
                        visited.add(target_sub.name)
                        next_time = (
                            curr_time
                            + self._get_estimated_pure_interaction_time(target_sub)
                        )
                        queue.append((target_sub, next_time))

        return None, None

    def _calculate_volume_risk(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        deadline: float,
        target_critical_sub_name: str,
    ) -> Tuple[bool, float]:
        """Checks if remaining time is sufficient for required predecessor volume."""
        constraints = current_node.state.constraints
        if not constraints.has_node(target_critical_sub_name):
            return False, 0.0

        # 1. Identify Required Tasks
        ancestors = nx.ancestors(constraints, target_critical_sub_name)
        relevant_task_names = ancestors | {target_critical_sub_name}

        required_subtasks = [
            t
            for t in current_node.state.remaining_subtasks
            if t.name in relevant_task_names
            and t.name != candidate.subtask.name
            and t.name != target_critical_sub_name
        ]
        # [Fix 251216] Do NOT return 0.0 here.
        # If required_subtasks is empty, it means no intermediate tasks are needed.
        # We still need to calculate the slack based on (Deadline - FinishTime).
        # Returning 0.0 implies "Zero Slack" which triggers high penalty (Volume Pressure).
        # if not required_subtasks:
        #    return False, 0.0

        # 2. Calculate Total Volume (Interaction + MST Nav)
        sum_interaction = sum(
            self._get_estimated_pure_interaction_time(t) for t in required_subtasks
        )

        candidate_target_pos = self._get_task_interaction_location(
            candidate.subtask, current_node.state.scene_positions
        ) or tuple(current_node.state.scene_positions.get("agent", (0, 0, 0)))

        mst_nav_time = self._calculate_mst_navigation_time(
            candidate_target_pos,
            set(required_subtasks),
            current_node.state.scene_positions,
        )

        total_volume_needed = sum_interaction + mst_nav_time

        # 3. Calculate Time Available after Candidate
        cand_nav = candidate.estimated_first_nav_duration or 0.0
        cand_interact = 0.0
        if candidate.subtask.name.startswith("Wait for"):
            if candidate.subtask.duration:
                cand_interact = candidate.subtask.duration.interval
        else:
            cand_interact = self._get_estimated_pure_interaction_time(candidate.subtask)

        candidate_finish_time = (
            current_node.state.current_time + cand_nav + cand_interact
        )

        volume_slack = (deadline - candidate_finish_time) - total_volume_needed

        # [Volume Debug Log]
        if (
            volume_slack < -constants.TIMING_TOLERANCE_ABS
        ):  # Only log when things get tight
            log.debug(
                f"[Volume Check] Candidate: {candidate.subtask.name}\n"
                f"  - Target Critical: {target_critical_sub_name} (Due: {deadline:.2f})\n"
                f"  - Required Ancestors ({len(required_subtasks)}): {[t.name for t in required_subtasks]}\n"
                f"  - Volume: {total_volume_needed:.2f} (Interact: {sum_interaction:.2f} + MST: {mst_nav_time:.2f})\n"
                f"  - Time Avail: {deadline - candidate_finish_time:.2f} (Finish: {candidate_finish_time:.2f})\n"
                f"  - Volume Slack: {volume_slack:.2f}"
            )

        return volume_slack < 0, volume_slack

    def _calculate_remaining_work_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, float, float]:
        """Estimates cost of ALL remaining tasks after candidate."""

        # [Fix] 1. Identify Critical Chain
        _, chain_members = self._get_chain_info(current_node, candidate.subtask)

        # Determine excluded task (candidate itself)
        task_to_exclude = candidate.subtask.name
        if task_to_exclude.startswith("Wait for "):
            task_to_exclude = None
        elif task_to_exclude.startswith("MONITORING_FOR_"):
            task_to_exclude = task_to_exclude.replace("MONITORING_FOR_", "", 1)

        # Simulate execution for next state
        exec_info = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )

        next_pos = tuple(exec_info.scene_positions.get("agent"))

        # [Fix] 2. Filter Remaining Tasks (Exclude Entire Chain)
        next_tasks = {
            t
            for t in current_node.state.remaining_subtasks
            if t.name != task_to_exclude and t.name not in chain_members
        }

        next_constraints = current_node.state.constraints
        next_scene_pos = exec_info.scene_positions

        # Calculate Costs
        cp_duration = self._calculate_critical_path_interaction_duration(
            next_tasks, next_constraints, candidate.subtask
        )
        sum_interaction_time = sum(
            self._get_estimated_pure_interaction_time(t) for t in next_tasks
        )
        mst_time = self._calculate_mst_navigation_time(
            next_pos, next_tasks, next_scene_pos
        )

        # CP handles depth, Sum handles breadth. Max is a safe lower bound for sequential agent.
        base_work_time = max(cp_duration, sum_interaction_time)
        total_cost = base_work_time + mst_time

        return total_cost, cp_duration, mst_time

    # ========================================================================
    # Helper Functions - Estimation & Graph
    # ========================================================================

    def _get_estimated_pure_interaction_time(self, subtask: Subtask) -> float:
        if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
            return 0.0
        if subtask.duration and subtask.duration.interval is not None:
            return max(0.0, subtask.duration.interval)

        duration_sum = 0.0
        if subtask.execution and subtask.execution.primitive_actions:
            for action_str in subtask.execution.primitive_actions:
                action_type = action_str.split(" ", 1)[0].upper()
                if action_type not in ["NAVIGATE_TO", "WAIT", "MONITORING"]:
                    duration_map = {
                        "GRASP": GRASP_ACTION_DURATION,
                        "PLACE_INSIDE": PLACE_ACTION_DURATION,
                        "PLACE_ON_TOP": PLACE_ACTION_DURATION,
                        "OPEN": TOGGLE_ACTION_DURATION,
                        "CLOSE": TOGGLE_ACTION_DURATION,
                        "TOGGLE_ON": TOGGLE_ACTION_DURATION,
                        "TOGGLE_OFF": TOGGLE_ACTION_DURATION,
                        "SLICE": TOGGLE_ACTION_DURATION,
                        "FILL": PLACE_ACTION_DURATION,
                    }
                    duration_sum += duration_map.get(
                        action_type, TOGGLE_ACTION_DURATION
                    )
        return duration_sum

    def _get_task_interaction_location(
        self, subtask: Subtask, scene_positions: dict[str, any]
    ) -> Optional[Tuple[float, float, float]]:
        if not subtask.execution or not subtask.execution.primitive_actions:
            return None

        # Priority: NAVIGATE target -> First Action target
        for action_str in subtask.execution.primitive_actions:
            tokens = action_str.split(" ", 2)
            if len(tokens) > 1:
                target_id = tokens[1]
                if target_id in scene_positions:
                    return tuple(scene_positions[target_id])
        return None

    def _estimate_navigation_time_between_positions(
        self,
        pos1: Optional[Tuple[float, float, float]],
        pos2: Optional[Tuple[float, float, float]],
    ) -> float:
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0
        path = self.action_handler._find_shortest_path(pos1, pos2)
        return len(path) * NAV_STEP_DURATION if path else 0.0

    def _calculate_critical_path_interaction_duration(
        self,
        remaining_tasks: Set[Subtask],
        constraints: nx.DiGraph,
        executed_subtask: Optional[Subtask],
    ) -> float:
        if not remaining_tasks:
            return 0.0

        task_names = {sub.name for sub in remaining_tasks}
        subgraph = constraints.subgraph(task_names).copy()

        # Pre-calculate durations
        durations = {
            t.name: self._get_estimated_pure_interaction_time(t)
            for t in remaining_tasks
        }

        earliest_finish = {name: 0.0 for name in task_names}

        for node in nx.topological_sort(subgraph):
            max_pred_finish = 0.0
            for pred, _, data in subgraph.in_edges(node, data=True):
                if pred in earliest_finish:
                    interval = data.get("info", {}).get("Interval", 0.0)
                    max_pred_finish = max(
                        max_pred_finish, earliest_finish[pred] + interval
                    )

            earliest_finish[node] = max_pred_finish + durations.get(node, 0.0)

        cp_duration = max(earliest_finish.values()) if earliest_finish else 0.0

        # Apply credit for starting a critical chain
        if executed_subtask and constraints.has_node(executed_subtask.name):
            discount = 0.0
            for _, succ, data in constraints.out_edges(
                executed_subtask.name, data=True
            ):
                if succ in task_names and data.get("info", {}).get("IsCritical"):
                    discount += data.get("info", {}).get("Interval", 0.0)
            if discount > 0:
                cp_duration = max(0.0, cp_duration - discount)

        return cp_duration

    def _calculate_mst_navigation_time(
        self,
        current_agent_pos: Optional[Tuple[float, float, float]],
        remaining_tasks: Set[Subtask],
        scene_positions: dict[str, any],
    ) -> float:
        if not remaining_tasks:
            return 0.0

        locations = {current_agent_pos} if current_agent_pos else set()
        for t in remaining_tasks:
            loc = self._get_task_interaction_location(t, scene_positions)
            if loc:
                locations.add(loc)

        if len(locations) <= 1:
            return 0.0

        loc_list = list(locations)
        n = len(loc_list)
        dist_matrix = np.full((n, n), LARGE_NUMBER, dtype=float)

        for i in range(n):
            dist_matrix[i, i] = 0.0
            for j in range(i + 1, n):
                d = self._estimate_navigation_time_between_positions(
                    loc_list[i], loc_list[j]
                )
                dist_matrix[i, j] = dist_matrix[j, i] = d

        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import minimum_spanning_tree

        mst = minimum_spanning_tree(csr_matrix(dist_matrix))
        return mst.sum()
