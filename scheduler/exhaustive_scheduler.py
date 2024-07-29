from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Task, get_all_subtasks
from scheduler.dynamic_task_handler import TaskHandler
from scheduler.tree_builder import TreeBuilder


class ExhaustiveScheduler:
    def __init__(
        self, agent: Agent, tasks: List[Task], constraints: nx.DiGraph
    ) -> None:
        self.tasks = tasks
        self.tree_builder = TreeBuilder(agent, tasks, TaskHandler(agent), constraints)
        self.subtask_tree = self.tree_builder.build_tree()

    def generate_schedule(self) -> Node:
        leaf_paths = []
        all_subtasks = get_all_subtasks(self.tasks)
        all_subtask_names = {subtask.name for subtask in all_subtasks}

        for leaf in self.subtask_tree.leaves:
            included_subtasks = [node.name for node in leaf.path]
            included_subtask_names = {
                node_name
                for node_name in included_subtasks
                if not node_name.startswith(("Move", "Wait", "Start"))
            }

            if all_subtask_names == included_subtask_names:
                leaf_paths.append(leaf)

        if not leaf_paths:
            print("No complete paths found.")
            return self.subtask_tree

        min_makespan_leaf = min(leaf_paths, key=lambda leaf: leaf.makespan)
        min_makespan = min_makespan_leaf.makespan
        optimal_paths = [leaf for leaf in leaf_paths if leaf.makespan == min_makespan]

        print(f"Number of optimal paths: {len(optimal_paths)}")
        print(f"Makespan: {min_makespan}")

        return self.subtask_tree
