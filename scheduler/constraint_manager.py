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

        return True

    def get_urgency_constraints(self, subtask: Node):
        # subtask에서 outgoing하는 urgency constraints를 반환
        results = []
        for source, target, data in self.constraints.out_edges(subtask.name, data=True):
            if data["info"]["Urgency"]:
                interval = data["info"]["Interval"]
                target_start_time = subtask.makespan + interval
                print(f"{target} must start at {target_start_time}")
                print(subtask)
                return True
