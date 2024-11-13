from typing import List, Tuple
from xml.dom import Node

import networkx as nx

from core.task import Subtask


class ConstraintHandler:
    """constraint graph를 통한 subtask 제약 조건 처리"""

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def validate_constraints(self, parent_node: Node, subtask: Subtask) -> bool:
        """
        서브태스크가 모든 제약 조건을 만족하는지 확인
        """
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)
        constraints = self._get_constraints(subtask.name)

        if len(constraint_nodes) != len(constraints):
            return False

        time_slots = self.get_time_slot_and_urgency(parent_node, subtask)
        return all(
            time_slot >= 0 if is_urgency else True
            for time_slot, is_urgency in time_slots
        )

    def get_initial_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        """시작 제약 조건이 존재하지 않는 서브태스크를 반환합니다."""
        # TODO 시작 task가 decompose된 경우도 고려되는가?
        initial_nodes = {
            node for node, in_degree in self.constraints.in_degree() if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def get_expandable_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:
        """
        실행 가능한 서브태스크를 반환합니다.
        """
        eligible_subtasks = [
            subtask
            for subtask in remaining_subtasks
            if self.validate_constraints(parent_node, subtask)
        ]
        return eligible_subtasks

    def get_time_slot_and_urgency(
        self, parent_node: Node, subtask: Subtask
    ) -> List[Tuple[int, bool]]:
        """서브태스크에 대한 시간 슬롯과 긴급성을 계산."""
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)

        if not constraint_nodes:
            return [(0, False)]

        time_slots = [
            self._calculate_time_slot_for_constraint(parent_node, node, subtask)
            for node in constraint_nodes
        ]
        return time_slots

    def _get_constraints(self, subtask_name: str) -> List[Tuple]:
        """주어진 서브태스크와 관련된 모든 제약 조건을 수집합니다."""
        return [
            (u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_constraint_nodes(self, parent_node: Node, subtask_name: str) -> List[Node]:
        """subtask에 영향을 주는 제약 노드 반환"""
        constraint_nodes = [
            node
            for source, _, _ in self.constraints.in_edges(subtask_name, data=True)
            for node in parent_node.path
            if node.name.startswith(source)
        ]
        return constraint_nodes

    def _calculate_time_slot_for_constraint(
        self, parent_node: Node, constraint_node: Node, subtask: Subtask
    ) -> Tuple[int, bool]:
        """단일 제약 노드에 대한 시간 슬롯을 계산"""
        constraint_info = self.constraints.get_edge_data(
            constraint_node.name, subtask.name
        )["info"]
        interval = constraint_info["Interval"]
        urgency = constraint_info["Urgency"]

        time_slot = constraint_node.makespan + interval - parent_node.makespan

        return time_slot, urgency
