from collections import namedtuple
from typing import List, Tuple

import networkx as nx
from anytree import Node

from concept.task import Subtask


class ConstraintHandler:
    Constraint = namedtuple(
        "Constraint", ["source", "target", "interval", "is_urgency"]
    )

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def _gather_constraints(self, subtask_name: str) -> List[Constraint]:
        """Gather all constraints related to the given subtask."""
        return [
            self.Constraint(u, v, data["info"]["Interval"], data["info"]["Urgency"])
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

    def validate_ordering_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """Validate if a subtask satisfies ordering constraints to be added as a child node."""
        constraint_nodes = self._get_constraint_nodes(parent_node, subtask.name)
        constraints = self._gather_constraints(subtask.name)

        return len(constraint_nodes) == len(constraints)

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
            return True

    def get_time_slot_and_urgency(
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

    def get_eligible_subtasks(
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
        eligible_subtasks = []
        for subtask in remaining_subtasks:
            # Check ordering constraints
            if self.validate_ordering_constraints(parent_node, subtask):
                # Check timing constraints
                time_slot_urgencies = self.get_time_slot_and_urgency(
                    parent_node, subtask
                )
                if self.validate_timing_constraints(time_slot_urgencies):
                    if subtask.name == "Flipping Steak":
                        print()
                        print(time_slot_urgencies)
                    eligible_subtasks.append(subtask)

        return eligible_subtasks
