from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Task, get_all_subtasks
from task_management.handler.constraint_handler import ConstraintHandler
from task_management.handler.dynamic_task_handler import TaskHandler
from task_management.planner.task_plan_tree_builder import TreeBuilder


class ExhaustiveScheduler:
    def __init__(self, optimal_paths: List[Node], constraints: nx.DiGraph) -> None:
        self.optimal_paths = optimal_paths
        self.constraint_handler = ConstraintHandler(constraints)

    def generate_schedule(self):
        # Urgent (Hard-constraints)
        # print(self.optimal_paths)
        for optimal_path in self.optimal_paths:
            for node in optimal_path:
                urgent_constraints = self.constraint_handler.gather_constraints(
                    node.name
                )
                if urgent_constraints:

                    print(f"urgent_constraints : {urgent_constraints}")
