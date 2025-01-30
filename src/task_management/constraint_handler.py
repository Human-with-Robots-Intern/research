from typing import Any, List, NamedTuple, Optional, Tuple  # NamedTuple 임포트 추가

import networkx as nx
import numpy as np

from core.task import Subtask
from utils.dataclass import TimeSlot
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class ConstraintHandler:
    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def get_temporal_constraints(self, subtask_name: str, direction: str) -> TimeSlot:
        """
        subtask_name 기준으로 in/out 방향의 모든 엣지 중,
        'Interval'이 가장 작은 엣지를 찾아 TimeSlot(NamedTuple)으로 반환.
        엣지가 없다면 TimeSlot(0, False, None)을 반환.
        """
        if direction == "out":
            edges = list(self.constraints.out_edges(subtask_name, data=True))
        elif direction == "in":
            edges = list(self.constraints.in_edges(subtask_name, data=True))
        else:
            raise ValueError("direction must be either 'in' or 'out'.")

        if not edges:
            log.debug(
                f"No {direction} edges found for subtask {subtask_name}. "
                "Returning default TimeSlot(0, False, None)."
            )
            return TimeSlot(0, False, None)

        # interval이 가장 작은 엣지를 선택
        min_edge = min(
            (
                (
                    data["info"]["Interval"],
                    data["info"]["IsCritical"],
                    (
                        v if direction == "out" else u
                    ),  # out이면 (subtask -> v), in이면 (u -> subtask)
                )
                for u, v, data in edges
            ),
            key=lambda x: x[0],  # interval 기준 최소값
        )
        return TimeSlot(*min_edge)

    def validate_candidate_subtask(
        self, current_state: Any, candidate_subtask: Subtask
    ) -> bool:
        # (1) candidate_subtask의 선행 서브태스크가 완료되었는지
        constraint_subtasks = self._get_constraint_subtasks(
            current_state, candidate_subtask.name
        )
        # (2) 실제 incoming constraints
        all_incoming_time_slots = self.get_incoming_constraints(candidate_subtask.name)

        if len(constraint_subtasks) != len(all_incoming_time_slots):
            return False

        return self.valid_time_slot(current_state, all_incoming_time_slots)

    def valid_time_slot(self, current_state: Any, time_slots: List[TimeSlot]) -> bool:
        """
        critical -> 새 subtask 시작 시간 == (선행 end_time + interval)
        non-critical -> 새 subtask 시작 시간 >= (선행 end_time + interval)
        """
        new_subtask_start = current_state.current_time

        for ts in time_slots:
            # 현재 completed_subtasks는 [CompletedEntry(subtask, start_time, end_time), ...]
            pred_entry = next(
                (
                    ce
                    for ce in current_state.completed_subtasks
                    if ce.subtask.name == ts.related_subtask_name
                ),
                None,
            )
            if not pred_entry:
                return False

            pred_end_time = pred_entry.end_time
            required_start = pred_end_time + ts.interval

            if ts.is_critical:
                # critical => ==
                if new_subtask_start == required_start:
                    return False
            else:
                # non-critical => >=
                if new_subtask_start < required_start:
                    return False

        return True

    def get_expandable_subtasks(self, node: Any) -> List["Subtask"]:
        """
        현재 상태에서 (모든 제약이 충족되어) 바로 실행 가능한 서브태스크들을 반환.
        """
        return [
            subtask
            for subtask in node.state.remaining_subtasks
            if self.validate_candidate_subtask(node.state, subtask)
        ]

    # -----------------------------------------------------------------------
    #  Private helpers
    # -----------------------------------------------------------------------
    def _get_constraint_subtasks(
        self, current_state: Any, subtask_name: str
    ) -> List[Subtask]:
        """
        'subtask_name'의 선행 서브태스크(그래프 기준) 중
        이미 완료된 Subtask를 찾는다.
        """
        incoming_nodes = {u for u, _ in self.constraints.in_edges(subtask_name)}
        # completed_subtasks => List[CompletedEntry]
        # CompletedEntry.subtask 가 실제 Subtask 객체

        return [
            ce.subtask
            for ce in current_state.completed_subtasks
            if ce.subtask.name in incoming_nodes
        ]

    def get_incoming_constraints(self, subtask_name: str) -> List[TimeSlot]:
        """
        subtask_name으로 들어오는 모든 엣지 정보를 TimeSlot 리스트로 반환.
        (interval, is_critical, 선행노드명)
        """
        return [
            TimeSlot(
                data["info"]["Interval"],
                data["info"]["IsCritical"],
                u,  # u->v 형태에서 u가 선행
            )
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def compress_time_slots(
        self,
        current_state: Any,
        subtask: Subtask,
    ) -> Tuple[Optional[int], Optional[bool]]:
        """
        여러 constraints(TimeSlot) 중 하나를 선택하는 로직.
        우선순위(긴급/비긴급)와 interval 값에 따라 하나의 (interval, is_critical) 쌍을 결정하거나,
        모호/충돌 시 (None, None)을 반환한다.

        1) 여러 critical(critical) time_slots가 존재하는데 interval이 제각각이면 -> 충돌 => (None, None)
           - 만약 interval 값이 전부 동일하면 그중 하나 선택.

        2) critical time_slot과 non_critical time_slot이 동시에 존재할 때:
           - critical의 interval이 non_critical 중 최댓값보다 크면 critical 선택.
           - 그렇지 않으면 충돌 => (None, None)

        3) critical time_slot만 있다면, 그 하나를 선택.

        4) non_critical time_slot만 있다면, interval이 가장 큰 것을 선택.

        5) 그 외(음수나 0 등으로 바로 실행가능하다고 해석) 'expandable'한 time_slots가 있다면, 첫 번째를 선택.

        6) 아무것도 만족하지 못하면 => (None, None)
        """

        # 예: get_time_slots는 subtask로 들어오는 모든 constraint를
        # TimeSlot(interval, is_critical, related_subtask_name) 형태로 반환한다고 가정
        time_slots = self._get_time_slots(current_state, subtask)

        # (interval, is_critical) 형태로 필드를 추출
        # 여기서는 subtask_name은 우선 사용하지 않는다고 가정
        raw_slots = [(ts.interval, ts.is_critical) for ts in time_slots]

        # 1) 긴급(critical) & interval > 0
        critical_time_slots = [
            (interval, crit) for interval, crit in raw_slots if crit and interval > 0
        ]
        # 2) 비긴급(non-critical) & interval > 0
        not_critical_time_slots = [
            (interval, crit)
            for interval, crit in raw_slots
            if not crit and interval > 0
        ]
        # 3) 즉시/여유 허용 (여기서는 interval <= 0 은 '지체 없이 실행 가능' 등으로 해석)
        expandable_slots = [
            (interval, crit)
            for interval, crit in raw_slots
            if (crit and interval == 0) or (not crit and interval <= 0)
        ]

        # --- 판단 로직 ---

        # A. 긴급 time_slot이 여러 개 있는지?
        if len(critical_time_slots) > 1:
            # 모두 interval이 같은지 체크
            unique_intervals = {slot[0] for slot in critical_time_slots}
            if len(unique_intervals) == 1:
                # 예: 모두 interval=5, is_critical=True라면 -> pick
                return critical_time_slots[0]
            else:
                # 긴급인데 interval이 다르다면 충돌 -> None
                return None, None

        # B. 긴급과 비긴급이 모두 있는 경우
        elif critical_time_slots and not_critical_time_slots:
            # critical는 하나뿐이므로 critical_time_slots[0]
            critical_interval, _ = critical_time_slots[0]
            max_not_critical_interval = max(
                interval for interval, _ in not_critical_time_slots
            )
            if critical_interval > max_not_critical_interval:
                return critical_time_slots[0]  # 긴급 선택
            else:
                # 더 큰 비긴급이 존재 or 비교 불가 -> 충돌
                return None, None

        # C. 긴급만 있다면 (1개), 그거 선택
        elif critical_time_slots:
            return critical_time_slots[0]

        # D. 비긴급만 있다면, 그 중 interval이 가장 큰 것
        elif not_critical_time_slots:
            return max(not_critical_time_slots, key=lambda x: x[0])

        # E. 둘 다 없고 expandable만 있다면, 첫 번째 하나를 선택 (또는 다른 로직)
        elif expandable_slots:
            return expandable_slots[0]

        # F. 아무것도 없으면 (None, None)
        return None, None
