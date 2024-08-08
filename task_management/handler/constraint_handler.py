from collections import namedtuple
from typing import List, Optional, Tuple

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
        return [
            self.Constraint(u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_temporal_constraint_nodes(
        self, parent_node: Node, subtask_name: str
    ) -> List[Node]:
        """
        Returns the constraint nodes for the given subtask name.
        """
        return [
            node
            for source, _, _ in self.constraints.in_edges(subtask_name, data=True)
            for node in parent_node.path
            if node.name == source
        ]

    def validate_ordering_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """
        Validates if the subtask can be added as a child node.
        Returns True if all constraints are satisfied when the subtask has a 'Scheduled' status.
        """
        tc_nodes = self._get_temporal_constraint_nodes(parent_node, subtask.name)
        constraints = self._gather_constraints(subtask.name)

        return bool(constraints) == bool(tc_nodes) and len(tc_nodes) == len(constraints)

    def get_time_slot_and_urgency(
        self, parent_node: Node, subtask: Subtask
    ) -> List[Tuple[int, bool]]:
        """
        Calculate the appropriate time slot for the given subtask.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask for which the time slot is being calculated.
            tolerance (int): A tolerance value to adjust the time slot calculation.

        Returns:
            List[Tuple[int, bool]]: The sorted list of calculated time slots and their urgency.
        """
        constraint_nodes = self._get_temporal_constraint_nodes(
            parent_node, subtask.name
        )

        if not constraint_nodes:
            return [(0, False)]

        results = []

        for constraint_node in constraint_nodes:
            time_slot, is_urgency = self._calculate_time_slot_for_constraint(
                parent_node, constraint_node, subtask
            )
            results.append((time_slot, is_urgency))
        return results

    def validate_timing_constraints(self, inputs) -> List[Tuple[int, bool]]:
        results = []
        time_slot_handling_needed_list = []
        for time_slot, is_urgency in inputs:
            if is_urgency:
                if time_slot == 0:
                    # Expandable
                    is_valid = True
                elif time_slot > 0:
                    # fill the time slot then, expandable
                    time_slot_handling_needed_list.append((time_slot, is_urgency))
                    is_valid = True
                else:
                    # Pruning
                    is_valid = False
            else:
                if time_slot <= 0:
                    # Expandable
                    is_valid = True
                else:
                    # fill the time slot then, expandable
                    time_slot_handling_needed_list.append((time_slot, is_urgency))
                    is_valid = True
            if time_slot_handling_needed_list:
                print(time_slot_handling_needed_list)

            results.append(is_valid)

        if False in results:
            return False
        else:
            return True

    def _calculate_time_slot_for_constraint(
        self, parent_node: Node, constraint_node: Node, subtask: Subtask
    ) -> Tuple[int, bool]:
        """
        Calculate the time slot for a single constraint node.

        Args:
            parent_node (Node): The parent node in the task tree.
            constraint_node (Node): The constraint node affecting the subtask.
            subtask (Subtask): The subtask for which the time slot is being calculated.

        Returns:
            Tuple[int, bool]: The calculated time slot and its urgency.
        """

        constraint_info = self.constraints.get_edge_data(
            constraint_node.name, subtask.name
        )["info"]
        constraint_interval = constraint_info["Interval"]
        constraint_urgency = constraint_info["Urgency"]

        calculated_time_slot = (
            constraint_node.makespan + constraint_interval - (parent_node.makespan)
        )

        # NOTE! Do not Erase it, use for debugging
        # if calculated_time_slot >= 0:
        # print(
        #     f"Calculated_time_slot between '{constraint_node.name}' and '{subtask.name}': {calculated_time_slot}"
        # )
        # print(f"Urgency is {constraint_urgency}")
        # print()
        return calculated_time_slot, constraint_urgency
