from collections import namedtuple
from typing import List, Optional

import networkx as nx
from anytree import Node

from concept.task import Subtask


class ConstraintHandler:
    Constraint = namedtuple(
        "Constraint", ["source", "target", "interval", "is_urgency"]
    )

    def __init__(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def gather_constraints(self, subtask_name: str) -> List[Constraint]:
        constraints = []

        for u, v, data in self.constraints.in_edges(subtask_name, data=True):
            constraints.append(
                self.Constraint(
                    u,
                    v,
                    data["info"]["Interval"],
                    data["info"]["Urgency"],
                )
            )
        return constraints

    def validate_temporal_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        constraints = self.gather_constraints(subtask.name)

        if not constraints:
            return True

        for constraint in constraints:
            if not self.check_constraint(parent_node, subtask, constraint):
                return False

        return True

    def check_constraint(
        self, parent_node: Node, subtask: Subtask, constraint: namedtuple
    ) -> bool:
        tc_node = self.get_temporal_constraint_node(parent_node, constraint.source)

        if not tc_node:
            return False

        if tc_node.makespan + constraint.interval <= parent_node.makespan:
            return True
        else:
            return False

    def get_temporal_constraint_node(
        self, parent_node: Node, source_name: str
    ) -> Optional[Node]:
        for node in parent_node.path:
            if node.name == source_name:
                return node
        return None
