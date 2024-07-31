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

    def get_temporal_constraint_nodes(
        self, parent_node: Node, subtask_name: str
    ) -> Optional[Node]:
        tc_nodes = []
        for source, _, _ in self.constraints.in_edges(subtask_name, data=True):
            for node in parent_node.path:
                if node.name == source:
                    tc_nodes.append(node)
        return tc_nodes

    def validate_temporal_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        constraints = self.gather_constraints(subtask.name)

        if not constraints:
            return True

        for constraint in constraints:
            tc_nodes = self.get_temporal_constraint_nodes(
                parent_node, constraint.target
            )
            if not tc_nodes:
                return False

            for tc_node in tc_nodes:
                interval = self.constraints.get_edge_data(tc_node.name, subtask.name)[
                    "info"
                ]["Interval"]
                urgency = self.constraints.get_edge_data(tc_node.name, subtask.name)[
                    "info"
                ]["Urgency"]
                time_diff = parent_node.makespan - tc_node.makespan

                if urgency and time_diff > interval:
                    return False
                elif not urgency and time_diff < interval:
                    return False

        return True
