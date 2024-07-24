from anytree import Node, RenderTree

from concept.agent import Agent
from concept.task import Task, get_all_subtasks


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

    def _expand_tree(self, parent_node: Node, remaining_subtasks: list[Task]) -> None:
        """Expands the tree by adding eligible subtasks as children to the parent node."""
        eligible_subtasks = []

        for subtask in remaining_subtasks:
            precedence_task = subtask.constraints.get("After")

            # precedence subtask와 현재 subtask 사이에 temporal constraints가 존재하는 경우
            if subtask.constraints.get("After", []) in parent_node.path:
                # precedence subtask의 정보와 time constraints를 불러옴
                precedence_node = find_node_by_name(self.subtask_tree, precedence_task)
                tc_duration = subtask.constraints.get("Interval", 0)

                # temporal constraints가 충족되는지 확인
                if precedence_node.makespan + tc_duration <= parent_node.makespan:
                    eligible_subtasks.append(subtask)
            else:
                eligible_subtasks.append(subtask)

            for subtask in eligible_subtasks:
                new_remaining_subtasks = remaining_subtasks[:]
                new_remaining_subtasks.remove(subtask)
                self._add_subtask_to_tree(parent_node, subtask, new_remaining_subtasks)

    def _add_subtask_to_tree(
        self, parent_node: Node, subtask: Task, remaining_subtasks: list[Task]
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

    def get_optimal_schedule(self):
        """Finds and returns the optimal schedule."""
        pass

    def generate_schedule(self) -> None:
        """Generates and prints the schedule tree."""
        leaf_nodes = list(set(self.subtask_tree.leaves))

        print("Leaf nodes:")
        for idx, leaf in enumerate(leaf_nodes):
            print(idx, leaf)


def find_node_by_name(root: Node, name: str) -> Node:
    """Recursively searches for a node with the given name starting from the root node."""
    if root.name == name:
        return root
    for child in root.children:
        result = find_node_by_name(child, name)
        if result is not None:
            return result
    return None
