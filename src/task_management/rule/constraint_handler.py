from typing import List, Tuple

import networkx as nx
from anytree import Node

from core.task import Subtask


class ConstraintHandler:

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def _get_constraints(self, subtask_name: str) -> List[Tuple]:
        """Gather all constraints related to the given subtask."""
        return [
            (u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_constraint_nodes(self, parent_node: Node, subtask_name: str) -> List[Node]:
        """Get constraint nodes for the given subtask based on the task tree."""
        constraint_nodes = [
            node
            for source, _, _ in self.constraints.in_edges(subtask_name, data=True)
            for node in parent_node.path
            if node.name.startswith(source)
        ]
        return constraint_nodes

    def validate_constraints(self, parent_node: Node, subtask: Subtask) -> bool:
        """
        Validate if a subtask satisfies all constraints to be added as a child node.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to validate.

        Returns:
            bool: True if all constraints are satisfied, False otherwise.
        """
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)
        constraints = self._get_constraints(subtask.name)

        if len(constraint_nodes) != len(constraints):
            return False

        time_slots = self._get_time_slot_and_urgency(parent_node, subtask)
        return all(
            time_slot >= 0 if is_urgency else True
            for time_slot, is_urgency in time_slots
        )

    def _get_time_slot_and_urgency(
        self, parent_node: Node, subtask: Subtask
    ) -> List[Tuple[int, bool]]:
        """Calculate and return the time slots and urgency for a given subtask."""
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)

        if not constraint_nodes:
            return [(0, False)]

        time_slots = [
            self._calculate_time_slot_for_constraint(parent_node, node, subtask)
            for node in constraint_nodes
        ]
        return time_slots

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

    def get_initial_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        initial_nodes = {
            node for node, in_degree in self.constraints.in_degree() if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def get_expandable_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:
        """
        Retrieves a list of subtasks that are eligible for execution based on constraints.

        Args:
            parent_node (Node): The parent node in the task tree.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            List[Subtask]: List of subtasks that meet the constraints and can be executed.
        """

        eligible_subtasks = [
            subtask
            for subtask in remaining_subtasks
            if self.validate_constraints(parent_node, subtask)
        ]

        return eligible_subtasks
