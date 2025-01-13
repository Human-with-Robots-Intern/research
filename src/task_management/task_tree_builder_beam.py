import itertools
from queue import PriorityQueue
from typing import List

import networkx as nx
from anytree import Node

from omnigibson.utils.ui_utils import create_module_logger
from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=False)


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
    def __init__(self, constraints: nx.DiGraph, beam_width: int = 3):
        """
        Initialize the TaskTreeBuilder with Beam Search.

        Args:
            constraints (nx.DiGraph): Directed graph representing task constraints.
            beam_width (int): The number of top nodes to expand at each level.
        """
        self.tree = TaskTree()
        self.constraint_handler = ConstraintHandler(constraints)
        self.beam_width = beam_width

        self.slot_handler = SlotHandler(self._node_expansion)
        self.counter = itertools.count()

    def build_tree(self, tasks: List["Task"]) -> Node:  # type: ignore
        """
        Build the task tree using Beam Search.

        Args:
            tasks (List[Task]): A list of tasks to build the tree from.

        Returns:
            Node: The root node of the built task tree.
        """
        subtasks = tasks_to_subtasks(tasks)
        initial_subtasks = self.constraint_handler.get_initial_subtasks(subtasks)

        # Priority queue for beam search
        current_level = PriorityQueue()
        counter = itertools.count()  # Unique ID generator for tie-breaking
        current_level.put((0, next(counter), self.tree.root_node))  # (cost, id, node)

        while not current_level.empty():
            next_level = PriorityQueue()

            # Process current level's nodes
            for _ in range(min(self.beam_width, current_level.qsize())):
                _, _, parent_node = current_level.get()

                # Expand subtasks for each node
                for subtask in initial_subtasks:
                    if not self._can_expand_node(parent_node, subtask, subtasks):
                        continue

                    self._node_expansion(
                        parent_node, subtask, subtasks, next_level, counter
                    )

            # Limit to top-k nodes for the next level
            current_level = PriorityQueue()
            for _ in range(min(self.beam_width, next_level.qsize())):
                cost, id, node = next_level.get()
                current_level.put((cost, id, node))

        return self.tree.root_node

    def _node_expansion(
        self,
        parent_node: Node,
        subtask: "Subtask",
        remaining_subtasks: List["Subtask"],
        next_level: PriorityQueue,
        counter: itertools.count,
    ) -> None:
        """
        Expand a node in the task tree using SlotHandler and add it to the next level.

        Args:
            parent_node (Node): The parent node to expand from.
            subtask (Subtask): The subtask to process.
            remaining_subtasks (List[Subtask]): Remaining subtasks to consider.
            next_level (PriorityQueue): Priority queue for the next level.
            counter (itertools.count): Unique counter for generating IDs.
        """
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
        new_node = self.tree.add_subtask_node(parent_node, subtask)

        # Calculate cost and add to next level with unique ID
        cost = self._evaluate_node(new_node, subtask)
        next_level.put((cost, next(counter), new_node))

    def _can_expand_node(
        self, parent_node: Node, subtask: "Subtask", subtasks: List["Subtask"]
    ) -> bool:
        """
        Check if a node can be expanded based on constraints.

        Args:
            parent_node (Node): Current parent node.
            subtask (Subtask): Subtask to check.
            subtasks (List[Subtask]): List of remaining subtasks.

        Returns:
            bool: True if the node can be expanded, False otherwise.
        """
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            subtask,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        return time_slot is not None

    def _evaluate_node(self, node: Node, subtask: "Subtask") -> int:
        """
        Evaluate the cost of a node.

        Args:
            node (Node): The node to evaluate.
            subtask (Subtask): The associated subtask.

        Returns:
            int: The calculated cost.
        """
        # Example cost function: duration + soft constraint penalty
        duration_cost = subtask.duration.interval
        soft_constraint_penalty = 0
        soft_constraint_penalty = self.constraint_handler.get_soft_constraint_penalty(
            node, subtask
        )
        conflict_penalty = self.constraint_handler.get_conflict_penalty(node, subtask)
        soft_constraint_penalty += conflict_penalty
        # self.constraint_handler.get_soft_constraint_penalty(node, subtask)
        return duration_cost + soft_constraint_penalty
