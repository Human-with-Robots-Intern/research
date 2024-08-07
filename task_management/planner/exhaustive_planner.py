from typing import List

import networkx as nx
from anytree import Node
from anytree.exporter import UniqueDotExporter

from concept.agent import Agent
from concept.task import Task, get_all_subtasks
from task_management.handler.dynamic_task_handler import TaskHandler
from task_management.planner.task_plan_tree_builder import TreeBuilder


class ExhaustivePlanner:
    def __init__(
        self, agent: Agent, tasks: List[Task], constraints: nx.DiGraph
    ) -> None:
        self.tasks = tasks
        self.tree_builder = TreeBuilder(agent, tasks, TaskHandler(agent), constraints)
        self.subtask_tree = self.tree_builder.build_tree()

    def generate_valid_plans(self) -> Node:
        leaf_paths = []
        all_subtasks = get_all_subtasks(self.tasks)
        all_subtask_names = {subtask.name for subtask in all_subtasks}

        for leaf in self.subtask_tree.leaves:
            included_subtasks = [node.name for node in leaf.path]
            included_subtask_names = {
                node_name
                for node_name in included_subtasks
                if not (node_name.startswith(("Move", "Wait")) or node_name == "Start")
            }

            if all_subtask_names == included_subtask_names:
                leaf_paths.append(leaf)

        if not leaf_paths:
            print("No complete paths found.")
            return None

        min_makespan_leaf = min(leaf_paths, key=lambda leaf: leaf.makespan)
        min_makespan = min_makespan_leaf.makespan
        optimal_paths = [leaf for leaf in leaf_paths if leaf.makespan == min_makespan]

        print(f"Number of ordered paths: {len(optimal_paths)}/{len(leaf_paths)}")
        print(f"Makespan: {min_makespan}")

        # optimal paths에 대한 시각화
        optimal_nodes = set()
        for leaf in optimal_paths:
            for node in leaf.path:
                optimal_nodes.add(node)

        # Filter the tree to include only optimal nodes
        def filter_tree(node):
            if node not in optimal_nodes:
                return None
            new_node = Node(node.name, parent=node.parent)
            for child in node.children:
                new_child = filter_tree(child)
                if new_child is not None:
                    new_child.parent = new_node
            return new_node

        # Create a filtered tree
        filtered_tree_root = filter_tree(self.subtask_tree.root)
        UniqueDotExporter(self.subtask_tree).to_picture("results/task_tree.png")
        UniqueDotExporter(filtered_tree_root).to_picture("results/opt_task_tree.png")

        return self.subtask_tree
