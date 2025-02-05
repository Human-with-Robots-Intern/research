import logging
from typing import Any, Optional

from core.task import Subtask
from scheduler.dataclass import Candidate, SimulationNode
from utils.constants import SIMULATION_DEPTH
from utils.task import load_navigation_times
from utils.util import create_module_logger

log = create_module_logger(__name__)


class HeuristicManager:
    """
    - Subtask 실행 시 발생하는 휴리스틱 비용 계산
    - Wait 시 발생하는 비용 계산
    """

    def __init__(self, constraint_handler):
        self.constraint_handler = constraint_handler
        self.cost_weight = SIMULATION_DEPTH

    def calc_heuristic_cost(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        navigate_time: float,
    ) -> float:
        """
        기존 코드의 휴리스틱 공식:
          cost_val = (cost_weight - current_depth) * (
        subtask.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
        """
        bonus = 0
        # 첫번째 확장에서는 모니터링과 타이밍이 도래한 critical subtask를 우선적으로 실행
        if current_node.depth == 0:
            if candidate.subtask.type == "Monitor":
                bonus += 1000
            # 현재 시간과 candidate subtask의 시작 시간이 같고, critical인 경우
            if (
                abs(candidate.earliest_start - current_node.state.current_time) < 1e-9
                and candidate.is_critical
            ):
                bonus += 1000

        # 이전 실행에 가까울수록 높은 우선 순위를 부여
        factor = -max(self.cost_weight - current_node.depth, 1)

        # 현재 노드의 in/out 타임 슬롯을 가져옴
        in_time_slot = self.constraint_handler.get_temporal_constraints(
            candidate.subtask.name, current_node.state.constraints, "in"
        )
        # 병렬 작업은 빠르게 시작해야 함
        out_time_slot = self.constraint_handler.get_temporal_constraints(
            candidate.subtask.name, current_node.state.constraints, "out"
        )
        # 병렬이 끝나는 것은 느리게, 병렬 시작은 빠르게
        time_diff = out_time_slot.interval - in_time_slot.interval

        # Priority queue는 작은 값이 높은 우선 순위
        cost_val = (
            factor * (candidate.subtask.duration.interval + navigate_time + time_diff)
            - self._find_parallel_window(current_node)
            - bonus
        )

        # 최소값 반환
        return cost_val

    def _find_parallel_window(self, current_node: SimulationNode) -> float:
        """
        (예시) 이미 '진행 중'인 Uncontrollable 서브태스크가 있으면,
        그 작업의 남은 시간을 병렬 구간으로 보고 반환한다.
        - 여기서는 단순히 'type이 Uncontrollable이고 end_time > 현재'인 서브태스크 중 최댓값을 찾는 예시
        """

        now = current_node.state.current_time
        max_remaining = 0.0

        # completed_subtasks는 '이미 끝난' 작업이라는 점에서 'in-progress' 확인이 애매하지만,
        # 만약 "끝나지 않은" subtask를 별도 관리한다면 여기서 참조.

        for ce in current_node.state.completed_subtasks:
            temporal_constraint = self.constraint_handler.get_temporal_constraints(
                ce.subtask.name, current_node.state.constraints, "out"
            )
            parallel_window_end_time_candidate = (
                ce.end_time + temporal_constraint.interval
            )
            if parallel_window_end_time_candidate > now:
                # 아직 종료 안 되었다고 가정
                remaining = ce.end_time - now
                if remaining > max_remaining:
                    max_remaining = remaining

        return max_remaining


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
        self, current_node: SimulationNode, next_subtask: Subtask
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
    def _ensure_agent_location(self, current_node: SimulationNode) -> Optional[str]:
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

    def _find_last_location(self, current_node: SimulationNode) -> Optional[str]:
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
