from typing import List, Tuple

import networkx as nx
from anytree import Node

from archive.task import Subtask, Task, get_all_subtasks
from task_management.rule import ConstraintHandler, SlotHandler


class TaskTreeBuilder:
    def __init__(
        self,
        agent: Agent,
        tasks: List[Task],
        constraints: nx.DiGraph,
    ):
        self.agent = agent
        self.tasks = tasks
        self.slot_handler = SlotHandler(
            ConstraintHandler(constraints), self._process_subtask
        )
        self.active_subtask = None

    def build_tree(self) -> Node:
        root_node = Node(
            name="Start",
            makespan=0,
            duration=0,
            location=self.agent.position,
            type="Start",
        )
        subtasks = get_all_subtasks(self.tasks)
        initial_subtasks = self.slot_handler.constraint_handler.get_initial_subtasks(
            subtasks
        )
        for subtask in initial_subtasks:
            self._process_subtask(root_node, subtask, subtasks)

        return root_node

    def _process_subtask(
        self, parent_node: Node, subtask: Subtask, subtasks: List[Subtask]
    ) -> Node:
        remaining_subtasks = subtasks[:]
        remaining_subtasks.remove(subtask)

        move_cost = self.agent.move(
            subtask.roi.asset if subtask.roi.asset else subtask.roi.room
        )

        if move_cost != 0:
            parent_node = Node(
                f"Move ({parent_node.location} -> {self.agent.position})",
                parent=parent_node,
                makespan=parent_node.makespan + move_cost,
                duration=move_cost,
                location=self.agent.position,
                type="Move",
            )

        time_slot, _ = self.slot_handler.compress_time_slots(parent_node, subtask)

        if time_slot is None:
            return

        if time_slot > 0:
            # subtask가 monitoring type일 때, 해당 시간동안 subtask로 채워야 함
            parent_node, wait_time, remaining_subtasks = (
                self.slot_handler.handle_time_slots(
                    parent_node,
                    subtask,
                    remaining_subtasks,
                    time_slot,
                )
            )
            # time slot에 들어갈 작업이 없는 경우 wait 처리
            parent_node = Node(
                name=f"Wait_for_{subtask.name}",
                parent=parent_node,
                makespan=parent_node.makespan + wait_time,
                duration=wait_time,
                location=parent_node.location,
                type="Wait",
            )

        parent_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=parent_node.makespan + subtask.duration.interval,
            duration=subtask.duration.interval,
            location=f"{subtask.roi.room}:{subtask.roi.asset}",
            type=subtask.type,
        )

        expandable_subtasks = (
            self.slot_handler.constraint_handler.get_expandable_subtasks(
                parent_node, remaining_subtasks
            )
        )

        for subtask in expandable_subtasks:
            self._process_subtask(parent_node, subtask, remaining_subtasks)
