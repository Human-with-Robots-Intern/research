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
        remaining_subtasks = subtasks[:]
        remaining_subtasks.remove(subtask)

        # Monitoring일 때, 함께 작업할 subtask의 makespan을 monitoring시작에 위치
        # 함께 병렬처리할 subtask의 부모는 일단 monitoring
        if parent_node.type == "Monitoring":
            makespan = parent_node.parent.makespan
        else:
            makespan = parent_node.makespan

        # Move to the subtask location if necessary
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

        # Debugging
        print("노드 path", [path_node.name for path_node in parent_node.path])
        print(
            f"추가할 task : {subtask.name} ({parent_node.makespan}~{parent_node.makespan + subtask.duration.interval})"
        )
        print(
            "남은 task : ",
            [remaining_subtask.name for remaining_subtask in remaining_subtasks],
        )
        print()

        # Parallel execution check
        if subtask.type == "Monitoring":
            # This monitoring task can have parallel interaction tasks
            self.slot_handler.handle_monitoring_slots(
                parent_node, subtask, makespan, remaining_subtasks
            )
        else:
            # Regular task processing
            self.slot_handler.handle_time_slots(
                parent_node, subtask, makespan, remaining_subtasks
            )
            makespan += subtask.duration.interval
            parent_node = Node(
                subtask.name,
                parent=parent_node,
                makespan=makespan,
                location=f"{subtask.roi.room}:{subtask.roi.asset}",
                type=subtask.type,
            )

            # Expand the tree with remaining subtasks
            eligible_subtasks = (
                self.slot_handler.constraint_handler.get_eligible_subtasks(
                    parent_node, remaining_subtasks
                )
            )

            for subtask in eligible_subtasks:
                self._process_subtask(parent_node, subtask, remaining_subtasks)
