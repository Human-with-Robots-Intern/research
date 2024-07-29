from typing import List

from anytree import Node

from concept.agent import Agent
from concept.task import Subtask, Task, get_all_subtasks
from scheduler.dynamic_task_handler import TaskHandler


class TreeBuilder:
    def __init__(self, agent: Agent, tasks: List[Task], task_handler: TaskHandler):
        self.agent = agent
        self.tasks = tasks
        self.task_handler = task_handler

    def build_tree(self) -> Node:
        root_node = Node(name="Start", makespan=0, location=self.agent.location)
        subtasks = get_all_subtasks(self.tasks)
        initial_subtasks = self._get_initial_subtasks(subtasks)

        for subtask in initial_subtasks:
            remaining_subtasks = subtasks[:]
            remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(root_node, subtask, remaining_subtasks)

        return root_node

    def _expand_tree(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> None:
        eligible_subtasks = self._get_eligible_subtasks(parent_node, remaining_subtasks)

        for subtask in eligible_subtasks:
            new_remaining_subtasks = remaining_subtasks[:]
            new_remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _add_subtask_to_tree(
        self, parent_node: Node, subtask: Subtask, remaining_subtasks: List[Subtask]
    ) -> None:
        makespan = parent_node.makespan
        self.agent.location = parent_node.location

        parent_node, makespan = self.task_handler.handle_movement(
            parent_node, subtask, makespan
        )
        wait_time = self._calculate_wait_time(parent_node, subtask)

        if wait_time > 0:
            parent_node, makespan = self.task_handler.handle_wait_time(
                parent_node, subtask, wait_time, makespan
            )

        makespan += subtask.duration
        child_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=subtask.location,
        )

        self._expand_tree(child_node, remaining_subtasks)

    def _get_initial_subtasks(self, subtasks: List[Subtask]) -> List[Subtask]:
        return [subtask for subtask in subtasks if not subtask.constraints.get("After")]

    def _get_eligible_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:
        return [
            subtask
            for subtask in remaining_subtasks
            if self._validate_temporal_constraints(parent_node, subtask)
        ]

    def _validate_temporal_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        tc_name = subtask.constraints.get("After")
        if not tc_name:
            return True
        return self._get_temporal_constraint_node(parent_node, subtask) is not None

    def _get_temporal_constraint_node(
        self, parent_node: Node, subtask: Subtask
    ) -> Node:
        tc_name = subtask.constraints.get("After")
        if tc_name:
            for node in parent_node.path:
                if node.name == tc_name:
                    return node
        return None

    def _calculate_wait_time(self, parent_node: Node, subtask: Subtask) -> int:
        tc_interval = subtask.constraints.get("Interval", 0)
        tc_node = self._get_temporal_constraint_node(parent_node, subtask)

        if tc_node:
            wait_time = tc_node.makespan + tc_interval - parent_node.makespan
            return max(0, wait_time)
        return 0
