import copy
from typing import List, Optional

import networkx as nx
from anytree import AsciiStyle, Node, RenderTree

from omnigibson.utils.ui_utils import create_module_logger
from task_management.task_tree_builder import TaskTreeBuilder
from utils.util import tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=True)


class TaskTimingPlanner:
    def __init__(self, agent: "Agent", tasks: List["Task"], constraints: nx.DiGraph):  # type: ignore
        """
        Initialize the TaskTimingPlanner.

        Args:
            agent (Agent): The agent performing the tasks.
            tasks (List[Task]): The list of tasks to plan.
            constraints (nx.DiGraph): A directed graph representing task constraints.
        """
        self.agent = agent
        self.tasks = self.agent.adjust_subtask_duration(tasks)
        self.tree_builder = TaskTreeBuilder(constraints)
        self.task_tree = self.tree_builder.build_tree(self.tasks)

    def get_task_trees(self) -> tuple[Node, Node]:
        """
        Get the full task tree and the optimal task tree.

        Returns:
            Tuple[Node, Node]: A tuple containing the full task tree and the optimal task tree.
        """
        opt_task_tree = self._get_optimal_tree()
        self._print_plan(opt_task_tree)
        return self.task_tree, opt_task_tree

    def convert_to_tasks(self, opt_task_tree: Node) -> List["Subtask"]:  # type: ignore
        """
        Convert the optimal task tree back into a list of subtasks.

        Args:
            opt_task_tree (Node): The root of the optimal task tree.

        Returns:
            List[Subtask]: A list of subtasks extracted from the optimal task tree.
        """
        all_subtask_names = tasks_to_subtasks(self.tasks, mode="name")
        log.debug(f"All subtask names: {all_subtask_names}")

        subtasks_in_plan = []
        for node in opt_task_tree.leaves[0].path[1:]:
            if node.name in all_subtask_names:
                subtasks_in_plan.append(node.name)

        log.info(f"Subtasks in optimal plan: {subtasks_in_plan}")
        return subtasks_in_plan

    def _get_optimal_tree(self) -> Node:
        """
        Traverse the task tree to find the optimal path and return it.

        Returns:
            Node: The root node of the optimal task tree.
        """
        task_tree_copy = copy.deepcopy(self.task_tree)
        leaf_nodes = self._get_leaf_nodes(task_tree_copy)
        all_subtask_names = set(tasks_to_subtasks(self.tasks, mode="name"))
        log.debug(f"All subtask names: {all_subtask_names}")

        # Find leaf nodes whose paths include all subtask names
        complete_leaf_paths = []
        for leaf_node in leaf_nodes:
            included_subtask_names = self._get_included_subtask_names(leaf_node)

            if included_subtask_names == all_subtask_names:
                complete_leaf_paths.append(leaf_node)

        if not complete_leaf_paths:
            raise ValueError("No complete paths found in the task tree.")

        # Find leaf nodes with the minimal makespan
        min_makespan = min(leaf.end for leaf in complete_leaf_paths)
        optimal_leaf_nodes = [
            leaf for leaf in complete_leaf_paths if leaf.end == min_makespan
        ]

        # Collect nodes that are part of the optimal paths
        optimal_nodes_set = set()
        for leaf_node in optimal_leaf_nodes:
            current = leaf_node
            while current:
                optimal_nodes_set.add(current)
                current = current.parent

        # Prune the tree to include only optimal paths
        def prune_tree(node: Node) -> Optional[Node]:
            if node not in optimal_nodes_set:
                return None
            else:
                pruned_children = []
                for child in node.children:
                    pruned_child = prune_tree(child)
                    if pruned_child is not None:
                        pruned_children.append(pruned_child)
                node.children = pruned_children
                return node

        filtered_tree_root = prune_tree(task_tree_copy)
        if filtered_tree_root is None:
            raise ValueError("Failed to prune task tree to optimal path.")

        return filtered_tree_root

    def _get_leaf_nodes(self, node: Node) -> List[Node]:
        """
        Recursively get all leaf nodes in the tree.

        Args:
            node (Node): The node to start from.

        Returns:
            List[Node]: A list of leaf nodes.
        """
        if not node.children:
            return [node]
        else:
            leaves = []
            for child in node.children:
                leaves.extend(self._get_leaf_nodes(child))
            return leaves

    def _get_included_subtask_names(self, leaf_node: Node) -> set:
        """
        Get the set of subtask names included in the path to the given leaf node.

        Args:
            leaf_node (Node): The leaf node to trace back from.

        Returns:
            set: A set of subtask names included in the path.
        """
        included_subtask_names = set()
        current = leaf_node
        while current:
            if not (
                current.name.startswith(("Move", "Wait")) or current.name == "Init"
            ):
                included_subtask_names.add(current.name)
            current = current.parent
        log.debug(
            f"Included subtask names for leaf '{leaf_node.name}': {included_subtask_names}"
        )
        return included_subtask_names

    def _print_plan(self, tree_root: Node) -> None:
        """
        Print the optimal plan.

        Args:
            tree_root (Node): The root of the tree to print.
        """
        print(RenderTree(tree_root, style=AsciiStyle()).by_attr())
        total_time_cost = tree_root.leaves[0].end
        print(f"Total time cost: {total_time_cost}")
        log.info(f"Optimal plan total time cost: {total_time_cost}")
