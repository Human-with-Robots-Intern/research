from typing import Tuple

from anytree import Node

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
                f"Move ({parent_node.location} -> {self.agent.location})",
                parent_node,
                makespan=makespan,
                location=subtask.location,
            )
        return parent_node, makespan

    def handle_wait_time(
        self, parent_node: Node, subtask: Subtask, wait_time: int, makespan: int
    ) -> Tuple[Node, int]:
        makespan += wait_time

        parent_node = Node(
            f"Wait {wait_time} units",
            parent_node,
            makespan=makespan,
            location=self.agent.location,
        )
        return parent_node, makespan
