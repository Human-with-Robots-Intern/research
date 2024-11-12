import json
from pathlib import Path

import networkx as nx
from anytree import Node

from utils.util import ROOT_PATH


# Assuming Task, Subtask, and TemporalConstraint classes are defined
class TaskGenerator:
    def setUp(self):
        # JSON 데이터 로드
        file_path = Path(ROOT_PATH) / f"assets/tasks/task_new.json"

        with open(file_path, "r") as file:
            self.json_data = json.load(file)

    @staticmethod
    def generate_constraints(tasks: list) -> nx.DiGraph:
        """Generate a constraints graph for the given tasks."""
        G = nx.DiGraph()

        for task in tasks:
            for subtask in task.subtasks:
                G.add_node(subtask.name, subtask_type=subtask.type)

                for constraint in subtask.temporal_constraints:
                    if constraint.subtask:
                        if constraint.type == "After":
                            G.add_edge(
                                constraint.subtask,
                                subtask.name,
                                interval=constraint.interval,
                            )
                        elif constraint.type == "Before":
                            G.add_edge(
                                subtask.name,
                                constraint.subtask,
                                interval=constraint.interval,
                            )

        return G

    @staticmethod
    def generate_tree(tasks: list) -> Node:
        """Generate a task tree for visualization or planning."""
        root = Node("Root")

        task_nodes = {}
        for task in tasks:
            task_node = Node(task.name, parent=root)
            task_nodes[task.name] = task_node

            for subtask in task.subtasks:
                Node(subtask.name, parent=task_node)

        return root
