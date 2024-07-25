from typing import Tuple

from anytree import Node, RenderTree

from concept.agent import Agent
from concept.task import *


class TaskHandler:
    def __init__(self, agent: Agent):
        self.agent = agent

    def handle_movement(
        self, parent_node: Node, subtask: Subtask, makespan: int
    ) -> Tuple[Node, int]:
        move_cost = self.agent.move(subtask.location)
        if move_cost != 0:
            makespan += move_cost
            parent_node = Node(
                f"Move {parent_node.location} -> {self.agent.location}",
                parent_node,
                makespan=makespan,
                location=subtask.location,
            )
        return parent_node, makespan

    def handle_wait_time(
        self, parent_node: Node, subtask: Subtask, makespan: int
    ) -> Tuple[Node, int]:
        wait_time = self.calculate_wait_time(parent_node, subtask)
        if wait_time > 0:
            makespan += wait_time
            parent_node = Node(
                f"Wait {wait_time} units",
                parent_node,
                makespan=makespan,
                location=self.agent.location,
            )
        return parent_node, makespan

    def calculate_wait_time(self, parent_node: Node, subtask: Subtask) -> int:
        temporal_constraint_subtask = subtask.constraints.get("After")
        temporal_constraint_duration = subtask.constraints.get("Interval", 0)

        if not temporal_constraint_subtask:
            return 0

        node_trajectory = [node for node in parent_node.path]
        for dependency_node in node_trajectory:
            if dependency_node.name == temporal_constraint_subtask:
                wait_time = (
                    dependency_node.makespan
                    + temporal_constraint_duration
                    - parent_node.makespan
                )
                return max(0, wait_time)

        return 0
