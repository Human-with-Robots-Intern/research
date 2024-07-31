from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Task, get_all_subtasks
from task_management.handler.constraint_handler import ConstraintHandler
from task_management.handler.dynamic_task_handler import TaskHandler
from task_management.planner.task_plan_tree_builder import TreeBuilder


class ExhaustiveScheduler:
    def __init__(self, task_plans) -> None:
        pass


# # Urgent (Hard-constraints)
# urgent_constraints = self.constraint_handler.get_urgency_constraints(
#     parent_node
# )
# if urgent_constraints:
#     print()
#     print(f"urgent_constraints : {urgent_constraints}")
#     print(f"remaining subtasks : {remaining_subtasks}")

#     for remaining_subtask in remaining_subtasks:
#         for key, value in urgent_constraints.items():
#             if key == remaining_subtask.name:
#                 print(key, value)
#                 print(parent_node.path)
#                 print()


# def get_urgency_constraints(self, subtask: Node):
#     # subtask에서 outgoing하는 urgency constraints를 반환
#     results = {}
#     for _, target, data in self.constraints.out_edges(subtask.name, data=True):
#         if data["info"]["Urgency"]:
#             target_start_time = subtask.makespan + data["info"]["Interval"]
#             results[target] = target_start_time
#     return results
