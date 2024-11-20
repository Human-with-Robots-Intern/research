import copy
from typing import List, Optional, Tuple

import networkx as nx
import numpy as np
from anytree import AsciiStyle, Node, RenderTree

from core import Agent, Task
from task_management import TaskTreeBuilder


class TaskTimingPlanner:
    def __init__(self, agent: Agent, tasks: List[Task], constraints: nx.DiGraph):
        self.tasks = tasks
        self.tree_builder = TaskTreeBuilder(agent, self.tasks, constraints)
        self.task_tree = self.tree_builder.build_tree()

    def get_task_trees(self) -> Node:
        opt_task_tree = self._get_optimal_tree()
        self._print_plan(opt_task_tree)
        return self.task_tree, opt_task_tree

    def _get_optimal_tree(self) -> Node:
        """Traverse self.task_tree to find the optimal path and return it

        Returns:
            Node: Node from self.task_tree with only the optimal path left
        """
        task_tree = copy.deepcopy(self.task_tree)
        leaf_nodes = self._get_leaf_nodes(task_tree)

        all_subtask_names = {
            subtask.name for task in self.tasks for subtask in task.subtasks
        }

        # 리프 노드들 중 모든 subtask name을 path에 포함하는 노드 찾기
        complete_leaf_paths = []

        for leaf_node in leaf_nodes:
            included_subtask_names = set()
            current = leaf_node

            while current:
                # Exclude "Move", "Wait", and "Init" nodes
                if not (
                    current.name.startswith(("Move", "Wait")) or current.name == "Init"
                ):
                    included_subtask_names.add(current.name)
                current = current.parent

            # 모든 subtask name이 포함되어 있으면 complete path로 판단
            if included_subtask_names == all_subtask_names:
                complete_leaf_paths.append(leaf_node)

        if not complete_leaf_paths:
            raise ValueError("No complete paths found.")

        # 최적 경로를 갖는 leaf 노드들 찾기
        min_makespan = min(leaf.end for leaf in complete_leaf_paths)
        optimal_leaf_nodes = [
            leaf for leaf in complete_leaf_paths if leaf.end == min_makespan
        ]

        # Create a set of subtask nodes that are on the optimal paths
        optimal_nodes_set = set()
        for leaf_node in optimal_leaf_nodes:
            current = leaf_node
            while current:
                optimal_nodes_set.add(current)
                current = current.parent

        # Step 6: Recursively prune nodes that are not in optimal_nodes_set
        def prune_tree(node):
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

        # Step 7: Get the filtered tree containing only the optimal paths
        filtered_tree_root = prune_tree(task_tree)

        return filtered_tree_root

    # 모든 leaf 노드 찾기
    def _get_leaf_nodes(self, node):
        if not node.children:
            return [node]
        else:
            leaves = []
            for child in node.children:
                leaves.extend(self._get_leaf_nodes(child))
            return leaves

    def _print_plan(self, tree_root: Node) -> None:
        print(RenderTree(tree_root, style=AsciiStyle()).by_attr())
        print("total_time_cost :", tree_root.leaves[0].end)

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
