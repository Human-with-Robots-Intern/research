import itertools
from queue import PriorityQueue
from typing import List, Optional, Tuple

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
        """
        Initialize with a root node (start=0, end=0, duration=0).
        """
        self.root_node = Node(name="Init", start=0, end=0, duration=0)

    def add_wait_node(self, parent: Node, subtask_name: str, wait_time: int) -> Node:
        """
        Insert a 'wait' node under the given parent node.

        Args:
            parent (Node): The parent node.
            subtask_name (str): Name of the subtask to wait for (for logging).
            wait_time (int): Amount of time to wait.

        Returns:
            Node: The created wait node.
        """
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
        """
        Insert a subtask node under the given parent node.

        Args:
            parent (Node): The parent node to attach the subtask node.
            subtask (Subtask): The subtask object (must have .name, .duration.interval).

        Returns:
            Node: The newly created subtask node.
        """
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
    Builds a TaskTree using Beam Search, limited by 'beam_width' at each level.
    """

    def __init__(self, constraints: nx.DiGraph, beam_width: int = 3):
        """
        Args:
            constraints (nx.DiGraph): Directed graph representing task constraints.
            beam_width (int): Number of top candidates to keep each level (the 'beam').
        """
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._expand_node_with_cost)

        # Optionally track the "best" solution (if implementing isComplete checks).
        self.best_plan: Optional[Node] = None
        self.best_makespan: float = float("inf")

    def build_tree(self, tasks: List["Task"]) -> Node:
        """
        Build the tree via Beam Search. Returns the tree's root or (optionally)
        some best-solution node if you track it.

        Args:
            tasks (List[Task]): The list of high-level tasks to plan.

        Returns:
            Node: The root node of the built tree (or a best-solution node).
        """
        # 1) Convert tasks -> subtasks
        all_subtasks = tasks_to_subtasks(tasks)

        # 2) Identify initial subtasks (no dependencies, etc.)
        initial_subtasks = self.constraint_handler.get_initial_subtasks(all_subtasks)

        # 3) Initialize the queue with root node at cost=0
        current_candidate_subtasks_queue = self._init_queue_with_root()

        # 4) Beam Search loop
        while not current_candidate_subtasks_queue.empty():
            # 4-1) Gather all states in current "level"
            # Root Node
            current_candidate_subtasks = self._drain_queue(
                current_candidate_subtasks_queue
            )

            # 4-2) Expand each node at this level
            next_candidate_subtasks_queue = self._simulate_subtask_expansion(
                current_candidate_subtasks, initial_subtasks, all_subtasks
            )

            # 4-3) Keep only top 'beam_width' for the next iteration
            pruned_next_candidate_subtasks_queue = self._prune_to_beam(
                next_candidate_subtasks_queue
            )

            current_candidate_subtasks_queue = pruned_next_candidate_subtasks_queue

        # 5) Return final result (root or best_node)
        return self._final_node()

    # --------------------------------------------------------------------------
    # Internal Beam Search Helpers
    # --------------------------------------------------------------------------

    def _simulate_subtask_expansion(
        self,
        parent_candidates: List[Tuple[int, int, Node]],
        child_candidates: List["Subtask"],
        all_subtasks: List["Subtask"],
    ) -> PriorityQueue:
        """부모노드를 확장하여 후보 서브태스크(자식 노드 후보)를 생성하고, 이를 다음 레벨의 노드로 확장한다.

        Args:
            current_nodes (List[Tuple[int, int, Node]]): _description_
            candidate_subtasks (List[&quot;Subtask&quot;]): _description_
            all_subtasks (List[&quot;Subtask&quot;]): _description_

        Returns:
            PriorityQueue: _description_
        """
        pq_next = PriorityQueue()
        uid_counter = itertools.count()

        for accumulated_cost, _, parent_candidate in parent_candidates:
            # (1) 모든 subtasks가 완료되었는지 확인
            if self.check_all_subtasks_done(parent_candidate, all_subtasks):
                self._update_best_solution(parent_candidate)
                continue  # No need to expand further

            # (2) 모든 subtasks가 완료되지 않았다면, 자식 노드 후보 생성
            for child_candidate in child_candidates:
                # 부모 노드에서 해당 자식 노드로 확장 가능하지 않으면 스킵
                if not self._can_expand(
                    parent_candidate, child_candidate, all_subtasks
                ):
                    continue

                # 자식 노드 추가
                new_cost, new_child = self._expand_node_with_cost(
                    parent_candidate, child_candidate, all_subtasks
                )

                if new_child is None:
                    continue

                new_cost = accumulated_cost + self._compute_cost(
                    new_child, child_candidate
                )
                pq_next.put((new_cost, next(uid_counter), new_child))

        return pq_next

    def _expand_node_with_cost(
        self,
        parent_node: Node,
        child_candidate: "Subtask",
        all_subtasks: List["Subtask"],
    ) -> Tuple[int, Optional[Node]]:
        """
        Attempt to expand 'parent_node' by adding 'subtask' as a child node.
        Includes time-slot handling, wait node insertion, cost calculation, etc.

        Returns:
            Tuple[int, Optional[Node]]:
            - cost (int): The cost for the newly created node.
            - new_node (Node or None): The resulting node, or None if expansion fails.
        """
        # (1) Check time slots feasibility
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            child_candidate,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        if time_slot is None:
            log.warning(f"No time slot for '{child_candidate.name}', skipping.")
            return (999999, None)

        # (2) Handle waiting if needed
        if time_slot > 0:
            updated_parent, wait_time, remaining_subtasks = (
                self.slot_handler.handle_time_slots(
                    parent_node,
                    child_candidate,
                    all_subtasks,
                    time_slot,
                    self.constraint_handler.get_expandable_subtasks,
                )
            )
            if wait_time > 0:
                updated_parent = self.tree.add_wait_node(
                    updated_parent, child_candidate.name, wait_time
                )

            parent_node = updated_parent
            # separation interval (time_slot)을 채우고, 남은 서브태스크를 반환
            effective_subtasks = remaining_subtasks
        else:
            # separation interval이 없다면, 모든 서브태스크를 유지
            effective_subtasks = all_subtasks

        # (3) Add subtask node
        new_node = self.tree.add_subtask_node(parent_node, child_candidate)

        # (4) Compute cost
        cost_val = self._compute_cost(new_node, child_candidate)
        return (cost_val, new_node)

    def _compute_cost(self, node: Node, subtask: "Subtask") -> int:
        """
        Compute cost for the newly created node.
        You may add penalties for conflicts, etc.

        Args:
            node (Node): The newly created node.
            subtask (Subtask): The subtask that led to this node.

        Returns:
            int: The cost (lower is better).
        """
        duration_cost = subtask.duration.interval
        # e.g. extra penalties:
        # soft_constraint_penalty = self.constraint_handler.get_soft_constraint_penalty(node, subtask)
        # conflict_penalty = self.constraint_handler.get_conflict_penalty(node, subtask)
        # total_penalty = soft_constraint_penalty + conflict_penalty
        return duration_cost  # + total_penalty

    # --------------------------------------------------------------------------
    # Utilities for PriorityQueue Handling
    # --------------------------------------------------------------------------

    def _can_expand(
        self,
        parent_node: Node,
        child_candidate: "Subtask",
    ) -> bool:
        """
        Check basic feasibility (time slot, constraints) for expansion.
        """
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            child_candidate,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        return time_slot is not None

    def _init_queue_with_root(self) -> PriorityQueue:
        """
        Create a priority queue with the root node at cost=0.
        """
        pq = PriorityQueue()
        uid_counter = itertools.count()
        root_cost = 0
        pq.put((root_cost, next(uid_counter), self.tree.root_node))
        return pq

    def _drain_queue(self, pq: PriorityQueue) -> List[Tuple[int, int, Node]]:
        """
        Pop all items from a priority queue and return as a list.
        """
        items = []
        while not pq.empty():
            items.append(pq.get())
        return items

    def _prune_to_beam(self, pq_next: PriorityQueue) -> PriorityQueue:
        """
        Take top 'beam_width' items from pq_next and return a new PQ.
        """
        pq_result = PriorityQueue()
        for _ in range(min(self.beam_width, pq_next.qsize())):
            cost_val, uid, nd = pq_next.get()
            pq_result.put((cost_val, uid, nd))
        return pq_result

    def _final_node(self) -> Node:
        """
        Return the final node.
        If you track best_node, you might return that. Otherwise, return the root.
        """
        # if self.best_node:
        #     return self.best_node
        return self.tree.root_node

    def _update_best_solution(self, node: Node):
        """
        If node.end < self.best_makespan, update best_makespan and best_node.
        """
        if node.end < self.best_makespan:
            self.best_makespan = node.end
            self.best_plan = node
            log.info(f"New best solution: end={self.best_makespan}, node={node.name}")

    def check_all_subtasks_done(
        self, node: Node, all_subtasks: List["Subtask"]
    ) -> bool:
        """
        Check if 'node' (and its ancestors) contain all subtasks from all_subtasks.
        Simplest approach: collect names of subtask nodes, compare with all_subtasks list.
        """
        # 1) Gather the set of subtask names completed so far
        completed_names = set()
        for ancestor in node.path:  # node + all parents up to root
            # Exclude wait nodes
            if not ancestor.name.startswith("Wait for ") and ancestor.name != "Init":
                completed_names.add(ancestor.name)

        # 2) Compare with the total subtask names in 'all_subtasks'
        required_names = set(s.name for s in all_subtasks)
        return completed_names == required_names
