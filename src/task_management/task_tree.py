# task_tree.py
import logging

from anytree import Node

from core.task import Subtask

log = logging.getLogger(__name__)


class TaskTree:
    """
    실행이 확정된 Subtask(또는 Wait)를 트리 구조로 관리하기 위한 클래스.
    """

    def __init__(self):
        """
        초기 루트 노드를 "Init"으로 생성합니다.
        """
        self.root_node = Node(name="Init", start=0, end=0, duration=0)

    def _add_node(self, parent: Node, name: str, start: int, end: int) -> Node:
        """
        주어진 부모 노드 아래에 새 노드를 추가합니다.
        """
        new_node = Node(
            name=name,
            parent=parent,
            start=start,
            end=end,
            duration=end - start,
        )
        log.debug(f"Added node: {new_node.name}, duration={new_node.duration}")
        return new_node

    def add_wait_node(self, parent: Node, subtask_name: str, wait_time: int) -> Node:
        """
        Wait 노드를 생성하여 트리에 추가합니다.
        """
        return self._add_node(
            parent=parent,
            name=f"Wait for {subtask_name}",
            start=parent.end,
            end=parent.end + wait_time,
        )

    def add_subtask_node(
        self, parent: Node, subtask: Subtask, navigate_time: int = 0
    ) -> Node:
        """
        실제 Subtask 노드를 트리에 추가합니다.
        """
        return self._add_node(
            parent=parent,
            name=subtask.name,
            start=parent.end,
            end=parent.end + navigate_time + subtask.duration.interval,
        )
