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
        root_node = Node(
            name="Start", makespan=0, location=self.agent.location, type="Start"
        )
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

        if parent_node.type == "Monitoring":
            makespan = parent_node.parent.makespan
        else:
            makespan = parent_node.makespan
        self.agent.location = parent_node.location

        # Move to the subtask location if necessary
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

        # print("노드 path", [path_node.name for path_node in parent_node.path])
        # # print(f"부모 노드 : {parent_node.name}")
        # print(
        #     f"추가할 task : {subtask.name} ({parent_node.makespan}~{parent_node.makespan + subtask.duration.interval})"
        # )
        # print(
        #     "남은 task : ",
        #     [remaining_subtask.name for remaining_subtask in remaining_subtasks],
        # )
        # print()

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
        child_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=f"{subtask.roi.room}:{subtask.roi.asset}",
            type=subtask.type,
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
