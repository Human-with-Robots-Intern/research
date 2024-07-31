from typing import List

import networkx as nx
from anytree import Node

from concept.agent import Agent
from concept.task import Task, get_all_subtasks
from task_management.constraint_manager import ConstraintHandler
from task_management.handler.dynamic_task_handler import TaskHandler
from task_management.planner.task_plan_tree_builder import TreeBuilder


class ExhaustiveScheduler:
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
                if not node_name.startswith(("Move", "Wait", "Start"))
            }

            if all_subtask_names == included_subtask_names:
                leaf_paths.append(leaf)

        if not leaf_paths:
            print("No complete paths found.")
            return None

        min_makespan_leaf = min(leaf_paths, key=lambda leaf: leaf.makespan)
        min_makespan = min_makespan_leaf.makespan
        optimal_paths = [leaf for leaf in leaf_paths if leaf.makespan == min_makespan]

        print(f"Number of ordered paths: {len(optimal_paths)}")
        print(f"Makespan: {min_makespan}")
        for optimal_path in optimal_paths:
            pass

        return self.subtask_tree


# def _calculate_wait_time(self, parent_node: Node, subtask: Subtask) -> int:
#     tc_nodes = self.constraint_handler.get_temporal_constraint_nodes(
#         parent_node, subtask.name
#     )
#     wait_times = []
#     if tc_nodes:
#         for tc_node in tc_nodes:
#             tc_interval = self.constraint_handler.constraints.get_edge_data(
#                 tc_node.name, subtask.name
#             )["info"]["Interval"]
#             wait_time = tc_node.makespan + tc_interval - parent_node.makespan
#             wait_times.append(wait_time)
#         return max(wait_times)
#     else:
#         return 0

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

# # Move
# parent_node, makespan = self.task_handler.handle_movement(
#     parent_node, subtask, makespan
# )

# # Wait
# wait_time = self._calculate_wait_time(parent_node, subtask)

# if wait_time > 0:
#     parent_node, makespan = self.task_handler.handle_wait_time(
#         parent_node, subtask, wait_time, makespan
#     )
# def get_urgency_constraints(self, subtask: Node):
#     # subtask에서 outgoing하는 urgency constraints를 반환
#     results = {}
#     for _, target, data in self.constraints.out_edges(subtask.name, data=True):
#         if data["info"]["Urgency"]:
#             target_start_time = subtask.makespan + data["info"]["Interval"]
#             results[target] = target_start_time
#     return results
