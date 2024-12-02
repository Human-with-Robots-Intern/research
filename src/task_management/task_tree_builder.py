from typing import List

import networkx as nx
from anytree import Node

from omnigibson.utils.ui_utils import create_module_logger
from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=True)


class TaskTree:
    def __init__(self):
        """
        Initialize the TaskTree with a root node.
        """
        self.root_node = Node(
            name="Init",
            start=0,
            end=0,
            duration=0,
        )

    def add_move_node(self, parent_node: Node, move_cost: int) -> Node:
        """
        Add a move node to the task tree.

        Args:
            parent_node (Node): The parent node to attach the move node to.
            move_cost (int): The cost (duration) of the move.

        Returns:
            Node: The newly created move node.
        """
        move_node = Node(
            name=f"Move for {parent_node.name}",
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + move_cost,
            duration=move_cost,
        )
        log.debug(f"Added move node: {move_node.name} with duration {move_cost}")
        return move_node

    def add_wait_node(
        self, parent_node: Node, subtask_name: str, wait_time: int
    ) -> Node:
        """
        Add a wait node to the task tree.

        Args:
            parent_node (Node): The parent node to attach the wait node to.
            subtask_name (str): The name of the subtask to wait for.
            wait_time (int): The duration of the wait.

        Returns:
            Node: The newly created wait node.
        """
        wait_node = Node(
            name=f"Wait for {subtask_name}",
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + wait_time,
            duration=wait_time,
        )
        log.debug(f"Added wait node: {wait_node.name} with duration {wait_time}")
        return wait_node

    def add_subtask_node(self, parent_node: Node, subtask: "Subtask") -> Node:  # type: ignore
        """
        Add a subtask node to the task tree.

        Args:
            parent_node (Node): The parent node to attach the subtask node to.
            subtask (Subtask): The subtask to add.

        Returns:
            Node: The newly created subtask node.
        """
        subtask_node = Node(
            name=subtask.name,
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + subtask.duration.interval,
            duration=subtask.duration.interval,
        )
        log.debug(
            f"Added subtask node: {subtask.name} with duration {subtask.duration.interval}"
        )
        return subtask_node


class TaskTreeBuilder:
    def __init__(self, constraints: nx.DiGraph):
        """
        Initialize the TaskTreeBuilder.

        Args:
            constraints (nx.DiGraph): A directed graph representing task constraints.
        """
        self.tree = TaskTree()
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._node_expansion)

    def build_tree(self, tasks: List["Task"]) -> Node:  # type: ignore
        """
        Build the task tree based on the given tasks and constraints.

        Args:
            tasks (List[Task]): A list of tasks to build the tree from.

        Returns:
            Node: The root node of the built task tree.
        """
        subtasks = tasks_to_subtasks(tasks)
        initial_subtasks = self.constraint_handler.get_initial_subtasks(subtasks)
        log.info(f"Initial subtasks: {[subtask.name for subtask in initial_subtasks]}")

        for initial_subtask in initial_subtasks:
            self._node_expansion(self.tree.root_node, initial_subtask, subtasks)

        return self.tree.root_node

    def _node_expansion(
        self, parent_node: Node, subtask: "Subtask", subtasks: List["Subtask"]  # type: ignore
    ) -> None:
        """
        Recursively expand nodes in the task tree.

        Args:
            parent_node (Node): The parent node to expand from.
            subtask (Subtask): The subtask to process.
            subtasks (List[Subtask]): Remaining subtasks to consider.
        """
        remaining_subtasks = subtasks.copy()
        remaining_subtasks.remove(subtask)

        # TODO: Calculate move cost using RRT or other path planning methods
        move_cost = self._calculate_move_cost(parent_node, subtask)

        if move_cost > 0:
            parent_node = self.tree.add_move_node(parent_node, move_cost)

        # Handle time slots
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            subtask,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        log.info(f"Time slot for {subtask.name}: {time_slot}")

        if time_slot is None:
            log.warning(
                f"No available time slot for subtask '{subtask.name}'. Skipping."
            )
            return

        if time_slot > 0:
            # Handle subtasks within the time slot
            parent_node, wait_time, remaining_subtasks = (
                self.slot_handler.handle_time_slots(
                    parent_node,
                    subtask,
                    remaining_subtasks,
                    time_slot,
                    self.constraint_handler.get_expandable_subtasks,
                )
            )
            if wait_time > 0:
                parent_node = self.tree.add_wait_node(
                    parent_node, subtask.name, wait_time
                )

        # Add subtask node
        parent_node = self.tree.add_subtask_node(parent_node, subtask)

        # Process expandable subtasks
        expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
            parent_node, remaining_subtasks
        )
        log.debug(
            f"Expandable subtasks from '{subtask.name}': {[s.name for s in expandable_subtasks]}"
        )

        for next_subtask in expandable_subtasks:
            self._node_expansion(parent_node, next_subtask, remaining_subtasks)

    def _calculate_move_cost(self, parent_node: Node, subtask: "Subtask") -> int:  # type: ignore
        """
        Calculate the move cost to the subtask's location.

        Args:
            parent_node (Node): The current node in the task tree.
            subtask (Subtask): The subtask to move to.

        Returns:
            int: The calculated move cost.
        """
        # Placeholder implementation; replace with actual environment-based calculation
        move_cost = 0
        log.debug(f"Calculated move cost to '{subtask.name}': {move_cost}")
        return move_cost
