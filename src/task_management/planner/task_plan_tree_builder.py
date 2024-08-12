from typing import List, Tuple

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Subtask, Task, get_all_subtasks
from task_management.handler.constraint_handler import ConstraintHandler
from task_management.handler.slot_handler import SlotHandler


class TreeBuilder:
    def __init__(
        self,
        agent: Agent,
        tasks: List[Task],
        constraints: nx.DiGraph,
    ):
        self.agent = agent
        self.tasks = tasks
        self.constraint_handler = ConstraintHandler(agent, constraints)
        self.slot_handler = SlotHandler(self.constraint_handler, self._process_subtask)

    def build_tree(self) -> Node:
        root_node = Node(name="Start", makespan=0, location=self.agent.location)
        subtasks = get_all_subtasks(self.tasks)
        initial_subtasks = self._get_initial_subtasks(subtasks)

        for subtask in initial_subtasks:
            self._process_subtask(root_node, subtask, subtasks)

        return root_node

    def _get_initial_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        initial_nodes = {
            node
            for node, in_degree in self.constraint_handler.constraints.in_degree()
            if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def _process_subtask(
        self, parent_node: Node, subtask: Subtask, subtasks: List[Subtask]
    ) -> None:
        remaining_subtasks = subtasks[:]
        remaining_subtasks.remove(subtask)

        # Retrieve makespan and location from the parent node
        makespan = parent_node.makespan
        self.agent.location = parent_node.location

        # Move
        goal_location = subtask.roi.asset if subtask.roi.asset else subtask.roi.room
        move_cost = self.agent.move(goal_location)

        if move_cost > 0:
            makespan += move_cost
            parent_node = Node(
                f"Move ({parent_node.location} -> {self.agent.location})",
                parent_node,
                makespan=makespan,
                location=goal_location,
            )

        # Handle time slot urgencies
        parent_node, makespan = self.slot_handler.handle_time_slots(
            parent_node, subtask, makespan, remaining_subtasks
        )

        # Execute the subtask
        makespan += subtask.duration.interval
        child_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=f"{subtask.roi.room}:{subtask.roi.asset}",
        )

        # Expand the tree with remaining subtasks
        self._expand_tree(child_node, remaining_subtasks)

    def _expand_tree(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> None:
        eligible_subtasks = self.slot_handler._get_eligible_subtasks(
            parent_node, remaining_subtasks
        )

        for subtask in eligible_subtasks:
            self._process_subtask(parent_node, subtask, remaining_subtasks)
