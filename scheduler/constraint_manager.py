from collections import namedtuple
from typing import Optional

import networkx as nx
from anytree import Node

from concept.task import Subtask


class ConstraintHandler:
    Constraint = namedtuple(
        "Constraint", ["source", "target", "type", "interval", "is_urgency"]
    )

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def gather_constraints(self, parent_node: Node, subtask: Subtask) -> set:
        constraints = set()

        for u, v, data in self.constraints.in_edges(subtask.name, data=True):
            constraints.add(
                self.Constraint(
                    u,
                    v,
                    data["info"]["Type"],
                    data["info"]["Interval"],
                    data["info"]["Urgency"],
                )
            )

        for ancestor_node in parent_node.path:
            for u, v, data in self.constraints.out_edges(ancestor_node.name, data=True):
                constraints.add(
                    self.Constraint(
                        u,
                        v,
                        data["info"]["Type"],
                        data["info"]["Interval"],
                        data["info"]["Urgency"],
                    )
                )

        return constraints

    def validate_ordering_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """순서 제약을 검사"""
        constraints = self.gather_constraints(parent_node, subtask)

        if self.constraints.in_degree(subtask.name) == 0:
            return True

        for constraint in constraints:
            if constraint.target == subtask.name:
                if self.get_temporal_constraint_node(parent_node, subtask):
                    return True

        return False

    def get_temporal_constraint_node(
        self, parent_node: Node, subtask: Subtask
    ) -> Optional[Node]:
        for u, _, _ in self.constraints.in_edges(subtask.name, data=True):
            for node in parent_node.path:
                if node.name == u:
                    return node
        return None
