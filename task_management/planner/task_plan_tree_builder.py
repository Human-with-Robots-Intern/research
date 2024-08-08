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
        self.constraint_handler = ConstraintHandler(agent, constraints)

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

        # Retrieve the makespan and location from the parent node
        makespan = parent_node.makespan
        self.agent.location = parent_node.location

        # Handle movement
        parent_node, makespan = self.task_handler.handle_movement(
            parent_node, subtask, makespan
        )

        # Check for time slot handling needs
        time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
            parent_node, subtask
        )

        # Process each time slot urgency
        for time_slot, is_urgency in time_slot_urgencies:
            if time_slot > 0:
                if is_urgency:
                    # Check if other quick tasks can be performed in this time slot
                    available_subtasks = self._get_eligible_subtasks(
                        parent_node, remaining_subtasks
                    )
                    time_spent = 0

                    for available_subtask in available_subtasks:
                        if (
                            available_subtask.duration.interval
                            <= time_slot - time_spent
                        ):
                            self._add_subtask_to_tree(
                                parent_node, available_subtask, remaining_subtasks
                            )
                            time_spent += available_subtask.duration.interval
                            remaining_subtasks.remove(available_subtask)

                            if time_spent >= time_slot:
                                break

                    # Add waiting time if there is still some time left after quick tasks
                    if time_spent < time_slot:
                        wait_time = time_slot - time_spent
                        wait_node = Node(
                            name=f"Wait_for_{subtask.name}",
                            parent=parent_node,
                            makespan=makespan + wait_time,
                            location=parent_node.location,
                        )
                        makespan += wait_time
                        parent_node = wait_node
                else:
                    # If urgency is False, just wait the specified time
                    wait_node = Node(
                        name=f"Wait_for_{subtask.name}",
                        parent=parent_node,
                        makespan=makespan + time_slot,
                        location=parent_node.location,
                    )
                    makespan += time_slot
                    parent_node = wait_node

        # Add the subtask execution
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
        eligible_subtasks = self._get_eligible_subtasks(parent_node, remaining_subtasks)

        for subtask in eligible_subtasks:
            new_remaining_subtasks = remaining_subtasks[:]
            new_remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _get_eligible_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:

        results = []

        for subtask in remaining_subtasks:
            if self.constraint_handler.validate_ordering_constraints(
                parent_node, subtask
            ):
                time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
                    parent_node, subtask
                )

                if self.constraint_handler.validate_timing_constraints(
                    time_slot_urgencies
                ):
                    results.append(subtask)

        return results
