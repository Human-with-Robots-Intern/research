from anytree import Node, RenderTree

from concept.agent import Agent
from concept.task import Subtask, Task, get_all_subtasks


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
        # Parent의 노드 정보를 불러옴
        makespan = parent_node.makespan
        self.agent.location = parent_node.location

        # agent를 이동시키고, 이동 cost를 반환
        move_cost = self.agent.move(subtask.location)

        # 방을 이동한경우, 이동 node를 추가
        if move_cost != 0:
            makespan += move_cost
            parent_node = Node(
                f"move {parent_node.location} -> {self.agent.location}",
                parent_node,
                makespan=makespan,
                location=subtask.location,
            )

        makespan += subtask.duration
        child_node = Node(
            subtask.name, parent_node, makespan=makespan, location=subtask.location
        )

        self._expand_tree(child_node, remaining_subtasks)

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
        temporal_constraint_subtask = subtask.constraints.get("After")
        node_trajectory = [node for node in parent_node.path]

        for dependency_node in node_trajectory:
            if dependency_node.name == temporal_constraint_subtask:
                return True

        # 얘를 True로 만들면 순서 제약조건 무관하게 모든 노드가 expansion됨 (Completness)
        return True

    def get_optimal_schedule(self):
        """Finds and returns the optimal schedule."""
        pass

    def generate_schedule(self) -> None:
        """Generates and prints the schedule tree."""
        # leaf_nodes = self.subtask_tree.leaves

        # print("Leaf nodes:")
        # for idx, leaf in enumerate(leaf_nodes):
        #     print(idx, leaf)
        print(RenderTree(self.subtask_tree))
