# navigation_manager.py
import logging
from typing import Optional

from core.task import Subtask

log = logging.getLogger(__name__)


class NavigationManager:
    """
    - 마지막 위치 탐색
    - 다음 Subtask의 목적지 탐색
    - 네비게이션 테이블에서 이동 시간 조회
    """

    def __init__(self, navigation_times: dict, all_subtasks_info: list):
        """
        Args:
            navigation_times: { "agent_location1": {"agent_location2": 시간, ...}, ... }
            all_subtasks_info: 전체 Subtask 정보 (네비게이션 위치 추적 등에 사용)
        """
        self.navigation_times = navigation_times
        self.subtasks_info = all_subtasks_info

    def calculate_navigation_time(
        self, current_subtask_name: str, partial_plan: list, candidate_subtask: Subtask
    ) -> float:
        """
        이동 시간 계산 메인 함수.
        """
        if isinstance(candidate_subtask, str):
            for subtask in self.subtasks_info:
                if subtask.name == candidate_subtask:
                    candidate_subtask = subtask
                    break

        if current_subtask_name.startswith("Wait") or candidate_subtask.name.startswith(
            "Wait"
        ):
            return 0.0

        # Init
        if current_subtask_name == "Init":
            last_location = "agent"
        else:
            last_location = self._find_last_location(partial_plan) or "agent"

        target_location = self._find_first_location(candidate_subtask)
        if not target_location:
            return 0.0

        return self._lookup_navigation_time(last_location, target_location)

    def _find_last_location(self, partial_plan: list) -> Optional[str]:
        """
        partial_plan을 뒤에서부터 확인하여 NAVIGATE_TO가 마지막으로 등장한 위치를 찾는다.
        """
        for subtask in reversed(partial_plan):
            if subtask.name.startswith("Wait"):
                continue

            # subtask_info 검색
            subtask_info = next(
                (s for s in self.subtasks_info if s.name == subtask.name), None
            )
            if (
                subtask_info
                and subtask_info.execution
                and subtask_info.execution.primitive_actions
            ):
                for action in reversed(subtask_info.execution.primitive_actions):
                    if action.startswith("NAVIGATE_TO"):
                        return action.split()[-1]
        return None

    def _find_first_location(self, subtask: Subtask) -> Optional[str]:
        """
        subtask 내부의 primitive_actions 중 첫 NAVIGATE_TO 위치를 찾는다.
        """
        if subtask.execution and subtask.execution.primitive_actions:
            for action in subtask.execution.primitive_actions:
                if action.startswith("NAVIGATE_TO"):
                    return action.split()[-1]
        return None

    def _lookup_navigation_time(self, source: str, target: str) -> float:
        """
        navigation_times 테이블에서 (source -> target) 시간 조회
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
