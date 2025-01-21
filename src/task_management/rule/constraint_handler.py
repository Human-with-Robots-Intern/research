from typing import Any, List, Tuple
from xml.dom import Node

import networkx as nx

from utils.util import log


class ConstraintHandler:
    """constraint graph를 통한 subtask 제약 조건 처리"""

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def validate_constraints(self, current_state: "Subtask", candidate_subtask: "Subtask") -> bool:  # type: ignore
        """
        서브태스크가 모든 제약 조건을 만족하는지 확인
        """
        constraint_subtasks = self._get_constraint_subtasks(
            current_state, candidate_subtask.name
        )
        constraints = self._get_constraints(candidate_subtask.name)

        if len(constraint_subtasks) != len(constraints):
            return False

        time_slots = self.get_time_slot_and_urgency(current_state, candidate_subtask)
        return all(
            time_slot >= 0 if is_urgency else True
            for time_slot, is_urgency in time_slots
        )

    def get_initial_subtasks(self, subtasks: List["Subtask"]) -> List["Subtask"]:  # type: ignore
        """시작 제약 조건이 존재하지 않는 서브태스크를 반환합니다."""
        initial_nodes = {
            node for node, in_degree in self.constraints.in_degree() if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def get_expandable_subtasks(
        self, state  # type: ignore
    ) -> List["Subtask"]:  # type: ignore
        """
        실행 가능한 서브태스크를 반환합니다.
        """
        eligible_subtasks = [
            subtask
            for subtask in state.remaining_subtasks
            if self.validate_constraints(state, subtask)
        ]
        return eligible_subtasks

    def get_time_slot_and_urgency(
        self, current_state: Any, subtask: "Subtask"  # type: ignore
    ) -> List[Tuple[int, bool]]:
        """서브태스크에 대한 시간 슬롯과 긴급성을 계산."""
        constraint_subtasks = self._get_constraint_subtasks(current_state, subtask.name)

        if not constraint_subtasks:
            return [(0, False)]

        time_slots = [
            self._calculate_time_slot_for_constraint(current_state, node, subtask)
            for node in constraint_subtasks
        ]
        return time_slots

    def get_temporal_constraints(
        self, subtask_name: str, type: str  # type: ignore
    ) -> Tuple[Tuple[int, bool], Tuple[int, bool]]:
        """
        Calculate the time slot and urgency for a given subtask.

        Args:
            subtask_name (Subtask): The name of the subtask for which constraints are calculated.

        Returns:
            Tuple[Tuple[int, bool], Tuple[int, bool]]:
                - Outgoing time slot and urgency.
                - Incoming time slot and urgency.
        """

        def extract_constraints(edges: List[Tuple[Any, Any, dict]]) -> Tuple[int, bool]:
            if not edges:
                log.debug(
                    f"No edges found for subtask {subtask_name}. Returning default (0, False)."
                )
                return 0, False, None
            return min(
                [
                    (data["info"]["Interval"], data["info"]["Urgency"], v)
                    for _, v, data in edges
                ],
                key=lambda x: x[0],
            )

        # Retrieve edges for outgoing and incoming constraints
        if type == "out":
            edges = list(self.constraints.out_edges(subtask_name, data=True))
        elif type == "in":
            edges = list(self.constraints.in_edges(subtask_name, data=True))

        # Calculate constraints
        time_slot = extract_constraints(edges)

        return time_slot

    def _get_constraints(self, subtask_name: str) -> List[Tuple]:
        """주어진 서브태스크와 관련된 모든 제약 조건을 수집합니다."""
        return [
            (u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_constraint_subtasks(
        self, current_state: Any, subtask_name: str
    ) -> List["Subtask"]:
        """subtask에 영향을 주는 제약 노드 반환"""
        constraint_nodes = [
            done_subtask
            for source, _, _ in self.constraints.in_edges(subtask_name, data=True)
            for done_subtask in current_state.partial_plan
            if done_subtask.name.startswith(source)
        ]
        return constraint_nodes

    def _calculate_time_slot_for_constraint(
        self, current_state: Any, constraint_subtask: Node, subtask: "Subtask"  # type: ignore
    ) -> Tuple[int, bool]:
        """단일 제약 노드에 대한 시간 슬롯을 계산"""
        constraint_info = self.constraints.get_edge_data(
            constraint_subtask.name, subtask.name
        )["info"]
        interval = constraint_info["Interval"]
        urgency = constraint_info["Urgency"]

        time_slot = interval

        return time_slot, urgency
