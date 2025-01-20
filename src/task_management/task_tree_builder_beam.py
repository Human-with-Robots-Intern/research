import copy
import itertools
from queue import PriorityQueue
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

if TYPE_CHECKING:
    from task_management.subtask import Subtask

import networkx as nx
from anytree import Node

from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import create_module_logger, load_navigation_times, tasks_to_subtasks

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
        self, constraints: nx.DiGraph, beam_width: int = 1, simulation_depth: int = 5
    ):
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._expand_node)
        self.navigation_times = load_navigation_times()
        self.subtasks_info = None

        self.best_plan: Optional[Node] = None
        self.best_makespan: float = float("inf")
        self._counter = itertools.count()  # Tie-breaking을 위한 카운터.

    def build_tree(self, tasks: List[Any]) -> Node:
        # Convert tasks -> subtasks.
        all_subtasks = tasks_to_subtasks(tasks)
        self.subtasks_info = copy.deepcopy(all_subtasks)

        # Start with the root node and initialize the queue.
        current_node = self.tree.root_node
        remaining_subtasks = all_subtasks

        while remaining_subtasks:
            temporal_constraint = self._calculate_time_slot(current_node)
            simulated_paths = self._simulate_expansion(
                current_node, remaining_subtasks, temporal_constraint
            )

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            shortest_path, _ = self._prune_simulated_paths(simulated_paths)
            _, _, selected_subtask, updated_remaining = shortest_path

            current_node = self.tree.add_subtask_node(current_node, selected_subtask)
            remaining_subtasks = updated_remaining

        return self.tree.root_node

    def _simulate_expansion(
        self,
        parent_node: Node,
        remaining_subtasks: List[Any],
        temporal_constraint: Tuple[int, bool] = None,
    ) -> List[Tuple[int, int, Any, List[Any]]]:
        """
        Simulate up to 'simulation_depth' expansions from the given parent_node.
        Use the time slot to schedule maximum subtasks.
        """
        queue = PriorityQueue()
        queue.put((0, 0, next(self._counter), parent_node, remaining_subtasks))
        separation_interval, is_time_critical = temporal_constraint

        simulated_paths = []
        visited_nodes = set()  # Prevent duplicate expansions

        while not queue.empty():
            total_cost, current_depth, _, current_node, remaining_subtasks = queue.get()

            # Create a unique identifier for the node and its state
            state_id = (id(current_node), tuple(sub.name for sub in remaining_subtasks))
            if state_id in visited_nodes:
                continue
            visited_nodes.add(state_id)

            if current_depth >= self.simulation_depth or not remaining_subtasks:
                continue

            if separation_interval > 0:
                self._handle_time_slot_case(
                    current_node,
                    remaining_subtasks,
                    simulated_paths,
                    total_cost,
                    current_depth,
                    separation_interval,
                    is_time_critical,
                )
            else:
                expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
                    current_node, remaining_subtasks
                )
                for expandable_subtask in expandable_subtasks:
                    cost, child_node, updated_remaining = self._expand_node(
                        current_node,
                        expandable_subtask,
                        remaining_subtasks,
                        current_depth,
                    )
                    if child_node:
                        queue.put(
                            (
                                total_cost + cost,
                                current_depth + 1,
                                next(self._counter),
                                child_node,
                                updated_remaining,
                            )
                        )
                        if current_depth == 0:
                            simulated_paths.append(
                                (
                                    total_cost + cost,
                                    current_depth + 1,
                                    expandable_subtask,
                                    updated_remaining,
                                )
                            )

        return simulated_paths

    def _handle_time_slot_case(
        self,
        current_node,
        remaining_subtasks,
        simulated_paths,
        total_cost,
        current_depth,
        separation_interval,
        is_time_critical,
    ):
        """
        Handle cases where a time slot is available for subtasks.
        """
        scheduled_subtasks, updated_remaining = self.fill_time_slot(
            remaining_subtasks, (separation_interval, is_time_critical)
        )

        if is_time_critical:
            for i, scheduled_subtask in enumerate(scheduled_subtasks):
                navigate_time = (
                    self._calc_navigate_time(
                        scheduled_subtasks[i - 1], scheduled_subtask
                    )
                    if i > 0
                    else 0
                )
                current_node = self.tree.add_subtask_node(
                    current_node, scheduled_subtask
                )

                # Reduce separation interval by task duration + navigate time
                separation_interval -= (
                    scheduled_subtask.duration.interval + navigate_time
                )

            if separation_interval > 0:
                current_node = self.tree.add_wait_node(
                    parent=current_node,
                    subtask_name="Time-Critical Wait",
                    wait_time=separation_interval,
                )

            if updated_remaining:
                next_subtask = updated_remaining[0]
                cost, child_node, updated_remaining = self._expand_node(
                    current_node, next_subtask, updated_remaining, current_depth
                )
                if child_node:
                    simulated_paths.append(
                        (
                            total_cost + cost,
                            current_depth + 1,
                            next_subtask,
                            updated_remaining,
                        )
                    )
        else:
            for i, scheduled_subtask in enumerate(scheduled_subtasks):
                navigate_time = (
                    self._calc_navigate_time(
                        scheduled_subtasks[i - 1], scheduled_subtask
                    )
                    if i > 0
                    else 0
                )
                current_node = self.tree.add_subtask_node(
                    current_node, scheduled_subtask
                )
                separation_interval -= (
                    scheduled_subtask.duration.interval + navigate_time
                )

    def fill_time_slot(
        self, remaining_subtasks: List[Any], temporal_constraint: Tuple[int, bool]
    ) -> Tuple[List[Any], List[Any]]:
        """
        Fill the given time slot with the maximum number of subtasks, considering navigate time.
        """
        separation_interval, _ = temporal_constraint
        remaining_subtasks = sorted(
            remaining_subtasks, key=lambda task: task.duration.interval
        )
        scheduled_subtasks = []

        for i, task in enumerate(remaining_subtasks[:]):
            # Calculate navigate time from the last scheduled task
            navigate_time = (
                self._calc_navigate_time(scheduled_subtasks[-1], task)
                if scheduled_subtasks
                else 0
            )

            # Total time required for this task
            total_time = task.duration.interval + navigate_time

            if total_time <= separation_interval:
                scheduled_subtasks.append(task)
                separation_interval -= total_time
                remaining_subtasks.remove(task)
            else:
                break  # No more tasks fit within the time slot

        return scheduled_subtasks, remaining_subtasks

    def _calculate_time_slot(self, node: Node) -> Tuple[int, bool]:
        outgoing_time_slot, _ = self.constraint_handler.get_temporal_constraints(
            node.name
        )
        outgoing_time_slot, incoming_time_slot = (
            self.constraint_handler.get_temporal_constraints(node.name)
        )
        if not outgoing_time_slot:
            log.warning(
                f"No time slot available for node {node.name}. Defaulting to 0."
            )
        return outgoing_time_slot

    def _expand_node(
        self,
        parent_node: Node,
        child_candidate: Any,
        remaining_subtasks: List[Any],
        parent_depth: int,
    ) -> Tuple[int, Optional[Node], List[Any]]:
        """
        Attempt to expand 'parent_node' with 'child_candidate'.
        """
        outgoing_time_slot, incoming_time_slot = (
            self.constraint_handler.get_temporal_constraints(child_candidate.name)
        )

        if outgoing_time_slot is None or incoming_time_slot is None:
            log.warning(
                f"Subtask '{child_candidate.name}' has no valid time slot. Skipping."
            )
            return (float("inf"), None, remaining_subtasks)

        # 이동 시간 계산
        navigate_time = self._calc_navigate_time(parent_node, child_candidate)

        # 새 노드 생성
        child_node = self.tree.add_subtask_node(parent_node, child_candidate)
        new_remaining_subtasks = [
            sub for sub in remaining_subtasks if sub.name != child_candidate.name
        ]

        # 총 비용 계산 (이동 시간 포함)
        cost_val = (3 - parent_depth) * (
            child_candidate.duration.interval
            - outgoing_time_slot[0]
            + incoming_time_slot[0]
            + navigate_time  # 이동 시간 포함
        )

        return (cost_val, child_node, new_remaining_subtasks)

    def _prune_simulated_paths(self, paths):
        """
        Prune the paths to the top `beam_width` paths and return the best path.
        """
        pruned_paths = sorted(paths, key=lambda x: (x[0], x[1]))[: self.beam_width]
        return pruned_paths[0], pruned_paths

    def _calc_navigate_time(
        self, source_subtask: Node, target_subtask: "Subtask"
    ) -> float:
        """
        Calculate the navigation time from the source subtask's last destination
        to the target subtask's first destination.

        Args:
            source_subtask (Node): The current task node (previous subtask).
            target_subtask (Subtask): The next target subtask.

        Returns:
            float: Navigation time based on the predefined distance table.
        """
        source_name = source_subtask.name
        source_subtask_info = next(
            (sub for sub in self.subtasks_info if sub.name == source_name), None
        )
        if not source_subtask_info:
            log.warning(f"Source subtask '{source_name}' not found in subtasks_info.")
            return float("inf")

        source_actions = source_subtask_info.execution.primitive_actions
        last_source_location = next(
            (
                action.split()[-1]
                for action in reversed(source_actions)
                if action.startswith("NAVIGATE_TO")
            ),
            None,
        )
        if not last_source_location:
            log.warning(
                f"No 'NAVIGATE_TO' action found in source subtask '{source_name}'."
            )
            return float("inf")

        target_actions = target_subtask.execution.primitive_actions
        first_target_location = next(
            (
                action.split()[-1]
                for action in target_actions
                if action.startswith("NAVIGATE_TO")
            ),
            None,
        )
        if not first_target_location:
            log.warning(
                f"No 'NAVIGATE_TO' action found in target subtask '{target_subtask.name}'."
            )
            return float("inf")

        matched_source_key = next(
            (
                key
                for key in self.navigation_times
                if key.startswith(last_source_location)
            ),
            None,
        )
        if not matched_source_key:
            log.warning(
                f"No source key matched for '{source_name}' in navigation times."
            )
            return float("inf")

        matched_target_key = next(
            (
                key
                for key in self.navigation_times.get(matched_source_key, {})
                if first_target_location in key
            ),
            None,
        )
        if not matched_target_key:
            log.warning(
                f"No target key matched for '{first_target_location}' under source key '{matched_source_key}'."
            )
            return float("inf")

        move_time = self.navigation_times[matched_source_key].get(
            matched_target_key, None
        )
        if move_time is None:
            log.warning(
                f"Navigation time from '{matched_source_key}' to '{matched_target_key}' not found. Defaulting to infinity."
            )
            return float("inf")

        log.info(
            f"Navigation time from '{last_source_location}' to '{first_target_location}' is {move_time} seconds."
        )
        return move_time
