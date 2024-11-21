from typing import List, Tuple

import networkx as nx
from anytree import Node

from task_management.rule import ConstraintHandler, SlotHandler


class TaskTree:
    def __init__(self, agent: "Agent"):  # type: ignore
        self.agent = agent
        self.root_node = Node(
            name="Init",
            start=0,
            end=0,
            duration=0,
        )

    def add_move_node(self, parent_node: Node, move_cost: int) -> Node:
        return Node(
            name=f"Move ({parent_node.location} -> {self.agent})",
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + move_cost,
            duration=move_cost,
        )

    def add_wait_node(
        self, parent_node: Node, subtask: "Subtask", wait_time: int  # type: ignore
    ) -> Node:
        return Node(
            name=f"Wait_for_{subtask.name}",
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + wait_time,
            duration=wait_time,
        )

    def add_subtask_node(self, parent_node: Node, subtask: "Subtask") -> Node:  # type: ignore
        return Node(
            name=subtask.name,
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + subtask.duration.interval,
            duration=subtask.duration.interval,
        )


class TaskTreeBuilder:
    def __init__(
        self,
        agent: "Agent",  # type: ignore
        tasks: List["Task"],  # type: ignore
        constraints: nx.DiGraph,
    ):
        # TODO Util the Agent Knowledge
        """이 단계에서 Agent의 Knowledge를 활용할 수 있어야 함"""
        self.agent = agent
        self.tasks = tasks
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._node_expansion)
        self.tree = TaskTree(agent)

    def build_tree(self) -> Node:
        subtasks = [subtask for task in self.tasks for subtask in task.subtasks]
        initial_subtasks = self.constraint_handler.get_initial_subtasks(subtasks)
        for initial_subtask in initial_subtasks:
            self._node_expansion(self.tree.root_node, initial_subtask, subtasks)

        return self.tree.root_node

    def _node_expansion(
        self, parent_node: Node, subtask: "Subtask", subtasks: List["Subtask"]  # type: ignore
    ) -> None:
        remaining_subtasks = subtasks[:]
        remaining_subtasks.remove(subtask)

        # TODO RRT로 이동 비용 계산 -> environment 정보 필요
        move_cost = 0
        if move_cost:
            parent_node = self.tree.add_move_node(parent_node, move_cost)

        # 시간 슬롯 처리
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node,
            subtask,
            self.constraint_handler.get_time_slot_and_urgency,
        )
        if time_slot is None:
            return

        if time_slot > 0:
            # agent의 지식을 활용하여 서브태스크의 예상 소요 시간 로드
            subtask.duration.interval = self.agent.get_task_duration(subtask)

            # 시간 슬롯 내에서 서브태스크 처리
            parent_node, wait_time, remaining_subtasks = (
                self.slot_handler.handle_time_slots(
                    parent_node,
                    subtask,
                    remaining_subtasks,
                    time_slot,
                    self.constraint_handler.get_expandable_subtasks,
                )
            )
            if wait_time > 0:
                parent_node = self.tree.add_wait_node(parent_node, subtask, wait_time)

        # 서브태스크 노드 추가
        parent_node = self.tree.add_subtask_node(parent_node, subtask)

        # 확장 가능한 서브태스크 처리
        expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
            parent_node, remaining_subtasks
        )
        for next_subtask in expandable_subtasks:
            self._node_expansion(parent_node, next_subtask, remaining_subtasks)
