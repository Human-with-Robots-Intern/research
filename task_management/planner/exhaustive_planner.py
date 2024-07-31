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
        valid_leaf_nodes = []
        all_subtasks = get_all_subtasks(self.tasks)
        all_subtask_names = {subtask.name for subtask in all_subtasks}

        for valid_leaf_node in self.subtask_tree.leaves:
            included_subtasks = [node.name for node in valid_leaf_node.path]
            included_subtask_names = {
                node_name
                for node_name in included_subtasks
                if not node_name.startswith(("Move", "Wait", "Start"))
            }

            if all_subtask_names == included_subtask_names:
                valid_leaf_nodes.append(valid_leaf_node)

        if not valid_leaf_nodes:
            print("No complete paths found.")
            return None

        min_makespan_leaf = min(valid_leaf_nodes, key=lambda leaf: leaf.makespan)
        min_makespan = min_makespan_leaf.makespan
        optimal_paths = [
            valid_leaf_node.path
            for valid_leaf_node in valid_leaf_nodes
            if valid_leaf_node.makespan == min_makespan
        ]
        print()
        print(f"Number of ordered paths: {len(optimal_paths)}/{len(valid_leaf_nodes)}")
        print(f"Makespan: {min_makespan}")

        return self.subtask_tree, optimal_paths
