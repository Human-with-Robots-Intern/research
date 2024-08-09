from collections import namedtuple
from typing import List, Tuple

import networkx as nx
from anytree import Node

from concept.task import Subtask


class ConstraintHandler:
    Constraint = namedtuple(
        "Constraint", ["source", "target", "interval", "is_urgency"]
    )

    def __init__(self, agent, constraints: nx.DiGraph):
        self.agent = agent
        self.constraints = constraints

    def _gather_constraints(self, subtask_name: str) -> List[Constraint]:
        """Gather all constraints related to the given subtask."""
        return [
            self.Constraint(u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_constraint_nodes(self, parent_node: Node, subtask_name: str) -> List[Node]:
        """Get constraint nodes for the given subtask based on the task tree."""
        return [
            node
            for source, _, _ in self.constraints.in_edges(subtask_name, data=True)
            for node in parent_node.path
            if node.name == source
        ]

    def validate_ordering_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """Validate if a subtask satisfies ordering constraints to be added as a child node."""
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)
        constraints = self._gather_constraints(subtask.name)

        return len(constraint_nodes) == len(constraints)

    def get_time_slot_and_urgency(
        self, parent_node: Node, subtask: Subtask
    ) -> List[Tuple[int, bool]]:
        """Calculate and return the time slots and urgency for a given subtask."""
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)

        if not constraint_nodes:
            return [(0, False)]

        return [
            self._calculate_time_slot_for_constraint(parent_node, node, subtask)
            for node in constraint_nodes
        ]

    def validate_timing_constraints(
        self, time_slot_info: List[Tuple[int, bool]]
    ) -> bool:
        """Validate timing constraints for a given list of time slots and urgencies."""
        results = [
            self._is_valid_time_slot(time_slot, is_urgency)
            for time_slot, is_urgency in time_slot_info
        ]

        return all(results)

    def _is_valid_time_slot(self, time_slot: int, is_urgency: bool) -> bool:
        """Determine if a time slot is valid based on its urgency."""
        if is_urgency:
            return time_slot >= 0
        else:
            return time_slot <= 0

    def _calculate_time_slot_for_constraint(
        self, parent_node: Node, constraint_node: Node, subtask: Subtask
    ) -> Tuple[int, bool]:
        """Calculate the time slot for a single constraint node affecting a subtask."""
        constraint_info = self.constraints.get_edge_data(
            constraint_node.name, subtask.name
        )["info"]
        interval = constraint_info["Interval"]
        urgency = constraint_info["Urgency"]

        time_slot = constraint_node.makespan + interval - parent_node.makespan

        return time_slot, urgency
