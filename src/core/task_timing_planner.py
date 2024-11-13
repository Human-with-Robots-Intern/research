from typing import List, Optional, Tuple

import networkx as nx
import numpy as np
from anytree import Node, PreOrderIter

from task_management import TaskTreeBuilder


class TaskTimingPlanner:
    def __init__(self, agent: "Agent", tasks: List["Task"], constraints: nx.DiGraph):
        self.tree_builder = TaskTreeBuilder(agent, tasks, constraints)
        self.task_tree = self.tree_builder.build_tree()

    # def get_optimal_paths(self) -> Optional[Tuple[Node, Node]]:
    #     """Generate valid task plans and set the optimal task plan."""

    #     # Tree에서 optimal path 찾기
    #     # leaf_paths = self._find_complete_leaf_paths()
    #     # if not leaf_paths:
    #     #     print("No complete paths found.")
    #     #     return None

    #     optimal_paths, min_makespan = self._find_optimal_paths(leaf_paths)
    #     self._print_plan_summary(optimal_paths, leaf_paths, min_makespan)

    #     filtered_tree_root = self._filter_optimal_tree(optimal_paths)
    #     self.task_tree = (
    #         filtered_tree_root  # Update the subtask tree to the optimal one
    #     )

    #     # Convert the optimal tree to a task plan
    #     self.task_plan = self.convert_tree_to_schedule(filtered_tree_root)

    #     return self.task_tree, filtered_tree_root

    # def _find_complete_leaf_paths(self) -> List[Node]:
    #     """Find all leaf paths that include all subtasks."""
    #     leaf_paths = []
    #     # Assuming your Task class has a method to get all subtasks
    #     all_subtask_names = {
    #         subtask.name for task in self.tasks for subtask in task.subtasks
    #     }

    #     for leaf in self.task_tree.leaves:
    #         included_subtask_names = {
    #             node.name
    #             for node in leaf.path
    #             if not (node.name.startswith(("Move", "Wait")) or node.name == "Start")
    #         }

    #         if all_subtask_names == included_subtask_names:
    #             leaf_paths.append(leaf)

    #     return leaf_paths

    # def _find_optimal_paths(self, leaf_paths: List[Node]) -> Tuple[List[Node], float]:
    #     """Find the optimal paths with the minimum makespan."""
    #     min_makespan_leaf = min(leaf_paths, key=lambda leaf: leaf.makespan)
    #     min_makespan = min_makespan_leaf.makespan
    #     optimal_paths = [leaf for leaf in leaf_paths if leaf.makespan == min_makespan]
    #     return optimal_paths, min_makespan

    # # def _print_plan_summary(
    # #     self, optimal_paths: List[Node], leaf_paths: List[Node], min_makespan: float
    # # ) -> None:
    # #     """Print a summary of the number of optimal paths and their makespan."""
    # #     print(f"Number of ordered paths: {len(optimal_paths)}/{len(leaf_paths)}")
    # #     print(f"Makespan: {min_makespan}")
    # #     for idx, optimal_path in enumerate(optimal_paths, start=1):
    # #         path_names = [node.name for node in optimal_path.path]
    # #         print(f"Optimal Path {idx}: {path_names}")
    # #     print()

    # def _filter_optimal_tree(self, optimal_paths: List[Node]) -> Node:
    #     """Filter the task tree to include only the optimal nodes."""
    #     optimal_nodes = {node for leaf in optimal_paths for node in leaf.path}

    #     def filter_tree(node: Node) -> Optional[Node]:
    #         if node not in optimal_nodes:
    #             return None
    #         new_node = Node(
    #             node.name,
    #             makespan=node.makespan,
    #             duration=node.duration,
    #             type=node.type,
    #         )
    #         for child in node.children:
    #             new_child = filter_tree(child)
    #             if new_child is not None:
    #                 new_child.parent = new_node
    #         return new_node

    #     return filter_tree(self.task_tree)

    # @staticmethod
    # def convert_tree_to_schedule(root: Node) -> List["ScheduledTask"]:
    #     """Convert the task tree into a schedule of tasks."""
    #     schedules = []

    #     def traverse_tree(node, current_path):
    #         task = ScheduledTask(
    #             name=node.name,
    #             start=node.makespan - node.duration,
    #             end=node.makespan,
    #             duration=node.duration,
    #         )
    #         if not node.children:
    #             schedules.append(current_path + [task])
    #         for child in node.children:
    #             traverse_tree(
    #                 child,
    #                 current_path + [task],
    #             )

    #     traverse_tree(root, [])
    #     return schedules[0] if schedules else []

    # def simulate_task_plan(self) -> List["ScheduledTask"]:
    #     """Simulate the execution of the task plan by adding noise to the durations."""
    #     if self.task_plan is None:
    #         raise ValueError("No task plan available to simulate.")

    #     sim_schedule = []
    #     current_time = 0

    #     for task in self.task_plan:
    #         sim_task_duration = max(np.random.normal(task.duration, 0.1), 0.1)
    #         sim_task_start_time = round(current_time, 3)
    #         sim_task_end_time = sim_task_start_time + sim_task_duration

    #         sim_task = ScheduledTask(
    #             name=task.name,
    #             start=sim_task_start_time,
    #             end=sim_task_end_time,
    #             duration=sim_task_duration,
    #         )
    #         sim_schedule.append(sim_task)

    #         current_time = sim_task_end_time

    #     return sim_schedule
