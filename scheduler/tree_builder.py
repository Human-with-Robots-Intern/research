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

    def _validate_temporal_constraints(
        self, parent_node: Node, subtask: Subtask
    ) -> bool:
        """
        Valid란? Waiting / Move / Subtask가 Add될 수 있는 상황
        Urgency가 True / False일 때 별로 서로 다른 temporal constraints checking 로직을 따른다."""

        is_tc_exist = subtask.constraints.get("After")
        is_urgency = subtask.constraints.get("Urgency")

        # Subtask node에 시간 제약이 없는 경우
        if not is_tc_exist:
            return True
        # Subtask node에 시간 제약이 있는 경우
        else:
            tc_node = _get_temporal_constraint_node(parent_node, subtask)
            tc_interval = subtask.constraints.get("Interval")

            if tc_node:
                return (
                    True
                    if tc_node.makespan + tc_interval <= parent_node.makespan
                    else False
                )
            else:
                return False
            # Urgency task인 경우, Subtask의 제약이 충족되는 즉시,
            if is_urgency:
                pass
            # Urgency task가 아닌 경우,
            else:
                # wait time이 음수면 False 나머지 경우 True
                return is_tc_exist in node_trajectory


def _get_temporal_constraint_node(parent_node: Node, subtask: Subtask):
    tc_name = subtask.constraints.get("After")

    node_trajectory = [node for node in parent_node.path]
    for dependency_node in node_trajectory:
        if dependency_node.name == tc_name:
            return dependency_node
