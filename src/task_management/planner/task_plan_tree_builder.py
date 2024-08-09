from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Subtask, Task, get_all_subtasks
from task_management.handler.constraint_handler import ConstraintHandler
from task_management.handler.dynamic_task_handler import TaskHandler
from task_management.handler.slot_handler import SlotHandler


class TreeBuilder:
    def __init__(
        self,
        agent: Agent,
        tasks: List[Task],
        task_handler: TaskHandler,
        constraints: nx.DiGraph,
    ):
        self.agent = agent
        self.tasks = tasks
        self.task_handler = task_handler
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

        # Handle movement
        parent_node, makespan = self.task_handler.handle_movement(
            parent_node, subtask, makespan
        )

        # Handle time slot urgencies
        makespan = self.slot_handler.handle_time_slots(
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
