import itertools
from queue import PriorityQueue
from typing import Any, List, Optional, Tuple

import networkx as nx
from anytree import Node

from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import create_module_logger, tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=False)


class TaskTree:
    """
    Manages a tree of tasks (subtasks or wait nodes).
    """

    def __init__(self):
        self.root_node = Node(name="Init", start=0, end=0, duration=0)

    def add_wait_node(self, parent: Node, subtask_name: str, wait_time: int) -> Node:
        wait_node = Node(
            name=f"Wait for {subtask_name}",
            parent=parent,
            start=parent.end,
            end=parent.end + wait_time,
            duration=wait_time,
        )
        log.debug(f"Added wait node: {wait_node.name}, duration={wait_time}")
        return wait_node

    def add_subtask_node(self, parent: Node, subtask: "Subtask") -> Node:
        subtask_node = Node(
            name=subtask.name,
            parent=parent,
            start=parent.end,
            end=parent.end + subtask.duration.interval,
            duration=subtask.duration.interval,
        )
        log.debug(
            f"Added subtask node: {subtask.name}, duration={subtask.duration.interval}"
        )
        return subtask_node


class TaskTreeBuilder:
    """
    Builds a TaskTree using 3-step simulation to select the first subtask of the shortest path.
    Includes tie-breaking to ensure consistent order for equal-cost paths.
    """

    def __init__(
        self, constraints: nx.DiGraph, beam_width: int = 1, simulation_depth: int = 3
    ):
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth  # 3번의 노드 확장을 수행.
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._expand_node_with_cost)
        self.best_plan: Optional[Node] = None
        self.best_makespan: float = float("inf")
        self._counter = itertools.count()  # Tie-breaking을 위한 카운터.

    def build_tree(self, tasks: List[Any]) -> Node:
        """
        Build the TaskTree by simulating 3 levels of expansion and selecting the shortest path.
        """
        # 1) Convert tasks -> subtasks.
        all_subtasks = tasks_to_subtasks(tasks)

        # 2) Start with the root node and initialize the queue.
        current_node = self.tree.root_node
        remaining_subtasks = all_subtasks

        while remaining_subtasks:
            # 3) Perform up to simulation_depth expansions.
            simulated_paths = self._simulate_expansion(current_node, remaining_subtasks)

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            # 4) Select the shortest path (with tie-breaking).
            shortest_path = min(
                simulated_paths, key=lambda x: (x[0], x[1])
            )  # 비용이 같을 경우 tie-break로 depth 고려.
            _, _, selected_subtask, updated_remaining = shortest_path

            # 5) Add the first subtask of the shortest path to the tree.
            current_node = self.tree.add_subtask_node(current_node, selected_subtask)
            remaining_subtasks = updated_remaining

        return self.tree.root_node

    def _simulate_expansion(
        self, parent_node: Node, remaining_subtasks: List[Any]
    ) -> List[Tuple[int, int, Any, List[Any]]]:
        """
        Simulate up to 'simulation_depth' expansions from the given parent_node.
        Returns:
            List of tuples: (total_cost, depth, first_subtask, updated_remaining_subtasks).
        """
        queue = PriorityQueue()
        queue.put((0, 0, next(self._counter), parent_node, remaining_subtasks))
        simulated_paths = []

        while not queue.empty():
            total_cost, depth, _, parent, remaining = queue.get()

            if depth >= self.simulation_depth or not remaining:
                continue  # 종료 조건: 최대 depth 도달 또는 남은 작업 없음.

            # 확장 가능한 서브태스크 가져오기.
            expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
                parent, remaining
            )
            for subtask in expandable_subtasks:
                cost, new_node, updated_remaining = self._expand_node_with_cost(
                    parent, subtask, remaining
                )
                if new_node is None:
                    continue

                # 첫 번째 서브태스크를 기록한 상태로 결과에 추가.
                if depth == 0:
                    simulated_paths.append(
                        (total_cost + cost, depth + 1, subtask, updated_remaining)
                    )

                # 다음 단계로 확장.
                queue.put(
                    (
                        total_cost + cost,
                        depth + 1,
                        next(self._counter),  # Tie-breaking 순서 보장.
                        new_node,
                        updated_remaining,
                    )
                )

        return simulated_paths

    def _expand_node_with_cost(
        self,
        parent_node: Node,
        child_candidate: Any,
        remaining_subtasks: List[Any],
    ) -> Tuple[int, Optional[Node], List[Any]]:
        """
        Attempt to expand 'parent_node' with 'child_candidate'.
        """
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            child_candidate,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        if time_slot is None:
            log.warning(
                f"Subtask '{child_candidate.name}' has no valid time slot. Skipping."
            )
            return (999999, None, remaining_subtasks)

        # Add child node.
        child_node = self.tree.add_subtask_node(parent_node, child_candidate)
        cost_val = self._compute_cost(parent_node, child_node)

        # Update remaining subtasks.
        new_remaining_subtasks = [
            sub for sub in remaining_subtasks if sub.name != child_candidate.name
        ]
        return (cost_val, child_node, new_remaining_subtasks)

    def _compute_cost(self, parent_node: Node, child_node: Node) -> int:
        """
        Compute the cost of adding 'child_node' under 'parent_node'.
        """
        return child_node.duration
