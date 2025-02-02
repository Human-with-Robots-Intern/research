import logging
from typing import Any, Optional

from core.task import Subtask
from utils.task import load_navigation_times

log = logging.getLogger(__name__)

COST_WEIGHT = 3


class HeuristicManager:
    """
    - Subtask 실행 시 발생하는 휴리스틱 비용 계산
    - Wait 시 발생하는 비용 계산
    """

    def __init__(self, constraint_handler):
        self.constraint_handler = constraint_handler
        self.cost_weight = COST_WEIGHT

    def calc_heuristic_cost(
        self,
        current_node: Any,
        subtask: Subtask,
        navigate_time: float,
    ) -> float:
        """
        기존 코드의 휴리스틱 공식:
          cost_val = (cost_weight - current_depth) * (
        subtask.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
        """
        in_time_slot = self.constraint_handler.get_temporal_constraints(
            subtask.name, "in"
        )
        out_time_slot = self.constraint_handler.get_temporal_constraints(
            subtask.name, "out"
        )
        time_diff = out_time_slot.interval - in_time_slot.interval

        factor = max(self.cost_weight - current_node.depth, 1)
        cost_val = factor * (subtask.duration.interval + time_diff + navigate_time)
        return cost_val


class NavigationManager:
    """
    Manages navigation time calculations between locations for the robot.
    - Finds the robot's current location if not known.
    - Parses NAVIGATE_TO actions in the next subtask.
    - Looks up travel times from a navigation time table (dictionary).
    """

    def __init__(self):
        self.navigation_times = load_navigation_times()

    def compute_navigation_time(
        self, current_node: Any, next_subtask: Subtask
    ) -> float:
        """
        Compute how long the robot will spend navigating in 'next_subtask'.
        Steps:
          1) Confirm the robot's current location from current_node.state.
             If unknown, attempt to find it from completed_subtasks' NAVIGATE_TO history.
          2) Parse all NAVIGATE_TO actions in 'next_subtask'.
          3) For each NAVIGATE_TO action, look up travel time from the current location
             to the target location, and accumulate.
          4) Update current_node.state.agent_location at the end.

        Returns:
            The total navigation time (float).
        """
        # If the subtask type is Monitor or no movement needed, return 0 immediately
        if next_subtask.type == "Monitor":
            return 0.0, current_node.state.agent_location
        start_location = None
        # 1) Ensure we have a known robot location
        start_location = self._ensure_agent_location(current_node)
        if start_location is None:
            start_location = "agent"

        nav_time_total = 0.0
        current_source = start_location

        # 2) If no primitive_actions or no NAVIGATE_TO, no nav time needed
        if not next_subtask.execution or not next_subtask.execution.primitive_actions:
            return 0.0, current_node.state.agent_location

        # 3) Accumulate travel time for each NAVIGATE_TO
        for action in next_subtask.execution.primitive_actions:
            if action.startswith("NAVIGATE_TO"):
                # e.g. "NAVIGATE_TO Kitchen"
                target_loc = action.split("NAVIGATE_TO", 1)[-1].strip()
                step_time = self._lookup_navigation_time(current_source, target_loc)
                nav_time_total += step_time
                current_source = target_loc

        # 4) Update the current location in the state
        return nav_time_total, current_source

    # ----------------------------------------------------------------------
    #  Internal Helpers
    # ----------------------------------------------------------------------
    def _ensure_agent_location(self, current_node: Any) -> Optional[str]:
        """
        Check if 'current_node.state.agent_location' is already known.
        If None or empty, try to deduce it by looking at the most recent
        NAVIGATE_TO in completed_subtasks + current_node.state.subtask.
        Returns:
            The (possibly updated) location string, or None if not found.
        """
        loc = current_node.state.agent_location
        if loc:
            return loc

        # Attempt to find from the plan's history
        found_loc = self._find_last_location(current_node)
        if found_loc:
            current_node.state.agent_location = found_loc
            return found_loc

        # If not found, return None
        return None

    def _find_last_location(self, current_node: Any) -> Optional[str]:
        """
        Traverse completed_subtasks (and current subtask) from the end,
        searching for the last NAVIGATE_TO action. Return its target location.
        """
        plan = current_node.state.completed_subtasks + [current_node.state.subtask]
        # Traverse in reverse to find the most recent NAVIGATE_TO
        for st in reversed(plan):
            if not st or not st.execution or not st.execution.primitive_actions:
                continue
            for action in reversed(st.execution.primitive_actions):
                if action.startswith("NAVIGATE_TO"):
                    return action.split("NAVIGATE_TO", 1)[-1].strip()
        return None

    def _lookup_navigation_time(self, source: str, target: str) -> float:
        """
        Look up the travel time from 'source' to 'target' in navigation_times.
        If not found, return 0.0 and log a warning.

        Note: If you need partial matching or fuzzy matching,
              adapt the dictionary access logic accordingly.
        """
        matched_source_key = next(
            (k for k in self.navigation_times if k.startswith(source)), None
        )
        if not matched_source_key:
            log.warning(f"No source key matched for '{source}' in navigation times.")
            return 0.0

        matched_target_key = next(
            (k for k in self.navigation_times[matched_source_key] if target in k),
            None,
        )
        if not matched_target_key:
            log.warning(
                f"No target key matched for '{target}' under '{matched_source_key}'."
            )
            return 0.0

        move_time = self.navigation_times[matched_source_key].get(
            matched_target_key, None
        )
        if move_time is None:
            log.warning(
                f"Navigation time from '{matched_source_key}' to '{matched_target_key}' not found."
            )
            return 0.0
        return move_time
