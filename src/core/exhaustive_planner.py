from typing import List, Optional, Tuple

import networkx as nx
from anytree import Node

from core.task import Task, get_all_subtasks
from task_management.task_plan_builder import TreeBuilder


class ExhaustivePlanner:
    def __init__(
        self, agent: Agent, tasks: List[Task], constraints: nx.DiGraph
    ) -> None:
        self.agent = agent
        self.tasks = tasks
        self.constraints = constraints
        self.tree_builder = TreeBuilder(agent, tasks, constraints)
        self.subtask_tree = self.tree_builder.build_tree()

    def generate_valid_plans(self) -> Optional[Node]:
        """Generate valid task plans and return the optimal task tree."""
        leaf_paths = self._find_complete_leaf_paths()

        if not leaf_paths:
            print("No complete paths found.")
            return None

        optimal_paths, min_makespan = self._find_optimal_paths(leaf_paths)
        self._print_plan_summary(optimal_paths, leaf_paths, min_makespan)

        filtered_tree_root = self._filter_optimal_tree(optimal_paths)

        return self.subtask_tree, filtered_tree_root

    def _find_complete_leaf_paths(self) -> List[Node]:
        """Find all leaf paths that include all subtasks."""
        leaf_paths = []
        all_subtask_names = {subtask.name for subtask in get_all_subtasks(self.tasks)}

        for leaf in self.subtask_tree.leaves:
            included_subtask_names = {
                node.name
                for node in leaf.path
                if not (node.name.startswith(("Move", "Wait")) or node.name == "Start")
            }

            if all_subtask_names == included_subtask_names:
                leaf_paths.append(leaf)

        return leaf_paths

    def _find_optimal_paths(self, leaf_paths: List[Node]) -> Tuple[List[Node], int]:
        """Find the optimal paths with the minimum makespan."""
        min_makespan_leaf = min(leaf_paths, key=lambda leaf: leaf.makespan)
        min_makespan = min_makespan_leaf.makespan
        optimal_paths = [leaf for leaf in leaf_paths if leaf.makespan == min_makespan]
        return optimal_paths, min_makespan

    def _print_plan_summary(
        self, optimal_paths: List[Node], leaf_paths: List[Node], min_makespan: int
    ) -> None:
        """Print a summary of the number of optimal paths and their makespan."""
        print(f"Number of ordered paths: {len(optimal_paths)}/{len(leaf_paths)}")
        print(f"Makespan: {min_makespan}")
        print(
            f"Optimal Paths : {[node.name for optimal_path in optimal_paths for node in optimal_path.path ]}"
        )
        print()

    def _filter_optimal_tree(self, optimal_paths: List[Node]) -> Node:
        """Filter the task tree to include only the optimal nodes."""
        optimal_nodes = {node for leaf in optimal_paths for node in leaf.path}

        def filter_tree(node: Node) -> Optional[Node]:
            if node not in optimal_nodes:
                return None
            new_node = Node(
                node.name,
                makespan=node.makespan,
                duration=node.duration,
                type=node.type,
            )
            for child in node.children:
                new_child = filter_tree(child)
                if new_child is not None:
                    new_child.parent = new_node
            return new_node

        return filter_tree(self.subtask_tree.root)
