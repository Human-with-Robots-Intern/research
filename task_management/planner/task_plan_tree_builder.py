from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Subtask, Task, get_all_subtasks
from task_management.handler.constraint_handler import ConstraintHandler
from task_management.handler.dynamic_task_handler import TaskHandler


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
        self.constraint_handler = ConstraintHandler(constraints)

    def build_tree(self) -> Node:
        root_node = Node(name="Start", makespan=0, location=self.agent.location)
        subtasks = get_all_subtasks(self.tasks)
        initial_subtasks = self._get_initial_subtasks(subtasks)

        for subtask in initial_subtasks:
            remaining_subtasks = subtasks[:]
            remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(root_node, subtask, remaining_subtasks)

        return root_node

    def _get_initial_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        initial_nodes = {
            node
            for node, in_degree in self.constraint_handler.constraints.in_degree()
            if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def _add_subtask_to_tree(
        self, parent_node: Node, subtask: Subtask, remaining_subtasks: List[Subtask]
    ) -> None:

        # 부모 노드 데이터 읽기
        makespan = parent_node.makespan
        self.agent.location = parent_node.location

        # Time Slot
        time_slot = self.constraint_handler.get_time_slot(parent_node, subtask)

        # Move
        parent_node, makespan = self.task_handler.handle_movement(
            parent_node, subtask, makespan
        )

        # if wait_time > 0:
        #     parent_node, makespan = self.task_handler.handle_wait_time(
        #         parent_node, subtask, wait_time, makespan
        #     )

        makespan += subtask.duration.interval
        child_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=subtask.roi.room,
        )

        self._expand_tree(child_node, remaining_subtasks)

    def _expand_tree(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> None:
        eligible_subtasks = self._get_eligible_subtasks(parent_node, remaining_subtasks)

        for subtask in eligible_subtasks:
            new_remaining_subtasks = remaining_subtasks[:]
            new_remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _get_eligible_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:
        return [
            subtask
            for subtask in remaining_subtasks
            if self.constraint_handler.validate_ordering_constraints(
                parent_node, subtask
            )
        ]
