from typing import List

from anytree import Node

from concept.agent import Agent
from concept.task import *
from scheduler.dynamic_task_handler import TaskHandler


class TreeBuilder:
    def __init__(self, agent: Agent, tasks: List[Task], task_handler: TaskHandler):
        self.agent = agent
        self.tasks = tasks
        self.task_handler = task_handler

    def build_tree(self) -> Node:
        root_node = Node(name="Start", makespan=0, location=self.agent.location)
        subtasks = get_all_subtasks(self.tasks, mode="all")

        initial_subtasks = [
            subtask for subtask in subtasks if not subtask.constraints.get("After")
        ]

        for subtask in initial_subtasks:
            remaining_subtasks = subtasks[:]
            remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(root_node, subtask, remaining_subtasks)

        return root_node

    def _add_subtask_to_tree(
        self, parent_node: Node, subtask: Subtask, remaining_subtasks: List[Subtask]
    ) -> None:
        makespan = parent_node.makespan
        self.agent.location = parent_node.location
        parent_node, makespan = self.task_handler.handle_movement(
            parent_node, subtask, makespan
        )
        parent_node, makespan = self.task_handler.handle_wait_time(
            parent_node, subtask, makespan
        )

        makespan += subtask.duration
        child_node = Node(
            subtask.name, parent_node, makespan=makespan, location=subtask.location
        )
        self._expand_tree(child_node, remaining_subtasks)

    def _expand_tree(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> None:
        eligible_subtasks = [
            subtask
            for subtask in remaining_subtasks
            if self._validate_temporal_constraints(parent_node, subtask)
        ]

        for subtask in eligible_subtasks:
            new_remaining_subtasks = remaining_subtasks[:]
            new_remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _validate_temporal_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        temporal_constraint_subtask = subtask.constraints.get("After")
        temporal_constraint_interval = subtask.constraints.get("Interval")
        is_urgency = subtask.constraints.get("Urgency")

        if not temporal_constraint_subtask:
            return True
        else:
            # 시간에 대한 고려 시작
            node_trajectory = [node.name for node in parent_node.path]
            # Urgency task인 경우, constraint_subtask makespan
            if 
        return temporal_constraint_subtask in node_trajectory
