from anytree import Node, RenderTree

from concept.agent import Agent
from concept.task import *


class ExhaustiveScheduler:
    def __init__(self, agent: Agent, tasks: list[Task]) -> None:
        """Initializes the scheduler with an agent and a list of tasks."""
        self.agent = agent
        self.tasks = tasks
        self.subtask_tree = self.build_tree()

    def build_tree(self) -> Node:
        """Builds a tree of subtasks with makespan and location information."""
        root_node = Node(name="Start", makespan=0, location=self.agent.location)
        subtasks = get_all_subtasks(self.tasks, mode="all")

        initial_subtasks = [
            subtask for subtask in subtasks if not subtask.constraints.get("After")
        ]

        for subtask in initial_subtasks:
            remaining_subtasks = subtasks[:]
            remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(root_node, subtask, remaining_subtasks)

        return root_node

    def _add_subtask_to_tree(
        self, parent_node: Node, subtask: Subtask, remaining_subtasks: list[Subtask]
    ) -> None:
        """Adds a subtask to the tree under the specified parent node and expands the tree recursively."""
        makespan = parent_node.makespan
        self.agent.location = parent_node.location
        parent_node, makespan = self._handle_movement(parent_node, subtask, makespan)
        parent_node, makespan = self._handle_wait_time(parent_node, subtask, makespan)

        if subtask.type == "Monitoring":
            pass

        makespan += subtask.duration
        child_node = Node(
            subtask.name, parent_node, makespan=makespan, location=subtask.location
        )
        self._expand_tree(child_node, remaining_subtasks)

    def _handle_movement(
        self, parent_node: Node, subtask: Subtask, makespan: int
    ) -> int:
        """Handles agent movement and updates makespan accordingly."""
        move_cost = self.agent.move(subtask.location)
        if move_cost != 0:
            makespan += move_cost
            parent_node = Node(
                f"Move {parent_node.location} -> {self.agent.location}",
                parent_node,
                makespan=makespan,
                location=subtask.location,
            )
        return parent_node, makespan

    def _handle_wait_time(
        self, parent_node: Node, subtask: Subtask, makespan: int
    ) -> int:
        """Handles wait time before starting a subtask and updates makespan accordingly."""
        wait_time = self._calculate_wait_time(parent_node, subtask)
        if wait_time > 0:
            makespan += wait_time
            parent_node = Node(
                f"Wait {wait_time} units",
                parent_node,
                makespan=makespan,
                location=self.agent.location,
            )
        return parent_node, makespan

    def _handle_parallel(
        self,
        parent_node: Node,
        subtask: Subtask,
        parallelable_subtasks: List[Subtask],
        makespan: int,
    ):
        pass

    def _expand_tree(
        self, parent_node: Node, remaining_subtasks: list[Subtask]
    ) -> None:
        """Expands the tree by adding eligible subtasks as children to the parent node."""

        eligible_subtasks = []
        for subtask in remaining_subtasks:
            is_valid = self._validate_temporal_constraints(parent_node, subtask)

            if is_valid:
                eligible_subtasks.append(subtask)

        for subtask in eligible_subtasks:
            new_remaining_subtasks = remaining_subtasks[:]
            new_remaining_subtasks.remove(subtask)
            self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _validate_temporal_constraints(self, parent_node: Node, subtask: Subtask):
        """Parent node의 Trajectory에 subtask의 constraint subtask가 존재하는지 확인"""
        # return True # For complete node expansion
        temporal_constraint_subtask = subtask.constraints.get("After")
        temporal_constraint_interval = subtask.constraints.get("Interval")
        is_urgency = subtask.constraints.get("Urgency")

        if not temporal_constraint_subtask:
            return True

        node_trajectory = [node for node in parent_node.path]
        for dependency_node in node_trajectory:
            # Waiting time이
            # wait_time = self._calculate_wait_time(parent_node, subtask)
            if dependency_node.name == temporal_constraint_subtask:
                return True

        return False

    def _calculate_wait_time(self, parent_node: Node, subtask: Subtask) -> int:
        """Calculates the required wait time for a subtask based on temporal constraints."""
        temporal_constraint_subtask = subtask.constraints.get("After")
        temporal_constraint_duration = subtask.constraints.get("Interval")

        if not temporal_constraint_subtask:
            return 0

        node_trajectory = [node for node in parent_node.path]
        for dependency_node in node_trajectory:
            if dependency_node.name == temporal_constraint_subtask:
                wait_time = (
                    dependency_node.makespan
                    + temporal_constraint_duration
                    - parent_node.makespan
                )
                return max(0, wait_time)

        return 0

    def generate_schedule(self) -> None:
        """Generates and prints the schedule tree if all subtasks are included."""
        leaf_paths = []
        # Get all subtasks from the initial tasks
        all_subtasks = get_all_subtasks(self.tasks, mode="all")
        all_subtask_names = set(subtask.name for subtask in all_subtasks)
        # Collect all subtasks included in the schedule tree
        for leaf in self.subtask_tree.leaves:
            included_subtasks = [node.name for node in leaf.path]
            included_subtask_names = set(
                node_name
                for node_name in included_subtasks
                if not node_name.startswith(("Move", "Wait", "Start"))
            )

            # Check if all subtasks are included in the schedule
            if all_subtask_names == included_subtask_names:
                leaf_paths.append(leaf)

        min_value = min(
            leaf_paths, key=lambda node_makespan: node_makespan.makespan
        ).makespan

        min_value_leaves = [path for path in leaf_paths if path.makespan == min_value]

        print(f"length of optimal_path : {len(min_value_leaves)}")
        print(f"makespan : {min_value}")
        # for leaf in min_value_leaves:
        #     print(leaf)

        return self.subtask_tree
