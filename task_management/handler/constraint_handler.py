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

    def validate_constraints(self, parent_node: Node, subtask: Subtask):
        pass

    def validate_temporal_constraints(self, parent_node: Node, subtask: Subtask):
        pass

    def validate_ordering_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """
        Validates if the subtask can be added as a child node.
        Returns True if all constraints are satisfied when the subtask has a 'Scheduled' status.
        """
        # 논리적으로 문제 없는 로직
        tc_nodes = self._get_temporal_constraint_nodes(parent_node, subtask.name)
        constraints = self._gather_constraints(subtask.name)

        return bool(constraints) == bool(tc_nodes) and len(tc_nodes) == len(constraints)

    def get_time_slot(self, parent_node: Node, subtask: Subtask) -> int:
        time_slots = []
        tc_nodes = self._get_temporal_constraint_nodes(parent_node, subtask.name)

        if not tc_nodes:
            return 0

        for tc_node in tc_nodes:
            # tc_node path와 parent_node path
            untracked_nodes = [
                untracked_node
                for untracked_node in parent_node.path[len(tc_node.path) - 1 :]
            ]
            tc_to_parent_interval = (
                untracked_nodes[-1].makespan - untracked_nodes[0].makespan
            )
            print([untracked_node.name for untracked_node in untracked_nodes[1:]])
            print(f"tc_to_parent_time : {tc_to_parent_interval}")
            
            
            tc_info = self.constraints.get_edge_data(tc_node.name, subtask.name)["info"]
            tc_interval, tc_urgency = tc_info["Interval"], tc_info["Urgency"]
            # print(
            #     tc_node.name,
            #     tc_node.makespan,
            #     tc_interval,
            #     tc_urgency,
            #     parent_node.name,
            #     parent_node.makespan,
            # )
            time_slot = tc_node.makespan + tc_interval - parent_node.makespan
            time_slots.append((time_slot, tc_urgency))
        time_slots.sort(key=lambda x: x[0])
        # print(time_slots)
        return time_slots[0]
