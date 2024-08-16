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
        self.slot_handler = SlotHandler(
            ConstraintHandler(constraints), self._process_subtask
        )
        self.active_subtask = None

    def build_tree(self) -> Node:
        root_node = Node(
            name="Start", makespan=0, location=self.agent.location, type="Start"
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
    ) -> None:
        # 추가할 subtask를 제외한 리스트 생성 -> subtask의 자식노드에 쓰일 subtasks
        remaining_subtasks = subtasks[:]
        remaining_subtasks.remove(subtask)

        makespan = parent_node.makespan

        # 지정된 subtask를 위한 이동
        self.agent.location = parent_node.location

        goal_location = subtask.roi.asset if subtask.roi.asset else subtask.roi.room
        move_cost = self.agent.move(goal_location)

        if move_cost != 0:
            makespan += move_cost
            parent_node = Node(
                f"Move ({parent_node.location} -> {self.agent.location})",
                parent=parent_node,
                makespan=makespan,
                location=self.agent.location,
                type="Move",
            )

        # move 이후, subtask가 추가될 때, 고려해야할 time slot을 계산
        time_slot, urgency = self.slot_handler.compress_time_slots(parent_node, subtask)

        if time_slot > 0:
            wait_time = self.slot_handler.handle_time_slots(
                parent_node, subtask, makespan, remaining_subtasks, time_slot
            )
            parent_node = Node(
                name=f"Wait_for_{subtask.name}",
                parent=parent_node,
                makespan=makespan + wait_time,
                location=parent_node.location,
                type="Wait",
            )
            makespan += wait_time
            print(f"waiting time : {wait_time}")

        # Regular task processing
        makespan += subtask.duration.interval
        parent_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=f"{subtask.roi.room}:{subtask.roi.asset}",
            type=subtask.type,
        )

        # Expand the tree with remaining subtasks
        expandable_subtasks = (
            self.slot_handler.constraint_handler.get_expandable_subtasks(
                parent_node, remaining_subtasks
            )
        )

        for subtask in expandable_subtasks:
            self._process_subtask(parent_node, subtask, remaining_subtasks)
