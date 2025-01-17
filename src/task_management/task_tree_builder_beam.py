import itertools
from queue import PriorityQueue
from typing import List, Tuple

import networkx as nx
from anytree import Node

from utils.util import create_module_logger
from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=False)


class TaskTree:
    def __init__(self):
        """
        Initialize the TaskTree with a root node.
        """
        self.root_node = Node(
            name="Init",
            start=0,
            end=0,
            duration=0,
        )

    def add_wait_node(
        self, parent_node: Node, subtask_name: str, wait_time: int
    ) -> Node:
        """
        Add a wait node to the task tree.
        """
        wait_node = Node(
            name=f"Wait for {subtask_name}",
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + wait_time,
            duration=wait_time,
        )
        log.debug(f"Added wait node: {wait_node.name} with duration {wait_time}")
        return wait_node

    def add_subtask_node(self, parent_node: Node, subtask: "Subtask") -> Node:  # type: ignore
        """
        Add a subtask node to the task tree.
        """
        subtask_node = Node(
            name=subtask.name,
            parent=parent_node,
            start=parent_node.end,
            end=parent_node.end + subtask.duration.interval,
            duration=subtask.duration.interval,
        )
        log.debug(
            f"Added subtask node: {subtask.name} with duration {subtask.duration.interval}"
        )
        return subtask_node


class TaskTreeBuilder:
    def __init__(self, constraints: nx.DiGraph, beam_width: int = 3):
        """
        Initialize the TaskTreeBuilder with Beam Search.

        Args:
            constraints (nx.DiGraph): Directed graph representing task constraints.
            beam_width (int): The number of top nodes to expand at each level.
        """
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._node_expansion_with_cost)

        # [추가] best_solution 관리를 위해 추가
        self.best_solution_node = None
        self.best_makespan = float("inf")

    def build_tree(self, tasks: List["Task"]) -> Node:  # type: ignore
        """
        Build the task tree using Beam Search.

        Args:
            tasks (List[Task]): A list of tasks to build the tree from.

        Returns:
            Node: The root node of the built task tree.
        """
        # 1) 초기 Subtasks 추출
        subtasks = tasks_to_subtasks(tasks)
        initial_subtasks = self.constraint_handler.get_initial_subtasks(subtasks)

        # 2) 초기 상태(= 트리의 루트 노드) 우선순위 큐에 삽입
        #    여기서 우선순위는 0으로 두고, tie-break 용 id는 counter로 생성
        pq_current_level = PriorityQueue()
        counter = itertools.count()
        init_cost = 0  # 루트 노드의 코스트는 0으로 가정
        pq_current_level.put((init_cost, next(counter), self.tree.root_node))

        # 3) 빔 서치 루프
        while not pq_current_level.empty():
            # 이번 레벨의 상태들을 모두 꺼내서 확장
            current_level_list = []
            while not pq_current_level.empty():
                current_level_list.append(pq_current_level.get())

            # 다음 레벨 후보를 담을 우선순위 큐
            pq_next_level = PriorityQueue()

            # (A) 이번 레벨의 각 상태(노드)에 대해 확장 시도
            for cost_val, _, parent_node in current_level_list:

                # [추가] 만약 모든 Subtask가 끝났다는 로직이 있다면, 여기에 배치
                # isComplete() 같은 함수를 만들 수도 있음.
                # 여기서는 "더 이상 확장할 subtask가 없다면"을 체크 예시:
                # if self.constraint_handler.check_all_subtasks_done(parent_node, subtasks):
                #    if parent_node.end < self.best_makespan:
                #        self.best_makespan = parent_node.end
                #        self.best_solution_node = parent_node
                #    continue

                # (B) 현재 노드에서 확장할 수 있는 subtask를 순회
                for subtask in initial_subtasks:
                    # 확장 가능 여부
                    if not self._can_expand_node(parent_node, subtask, subtasks):
                        continue
                    # 실제 확장 수행 => 자식 상태(노드) 생성
                    new_cost, new_node = self._node_expansion_with_cost(
                        parent_node, subtask, subtasks
                    )
                    if new_node is None:
                        continue

                    # (C) 새로 만들어진 노드를 next_level 후보에 삽입
                    pq_next_level.put((new_cost, next(counter), new_node))

            # (D) next_level 후보 중 상위 beam_width만 다음 루프에서 사용
            pq_current_level = PriorityQueue()
            for _ in range(min(self.beam_width, pq_next_level.qsize())):
                cost, uid, node = pq_next_level.get()
                pq_current_level.put((cost, uid, node))

        # 4) 빔 서치 종료 후, root_node 반환 (또는 best_solution_node)
        #    연구 목적에 따라, self.best_solution_node가 있다면 그걸 리턴해도 됨.
        return self.tree.root_node

    def _node_expansion_with_cost(
        self, parent_node: Node, subtask: "Subtask", remaining_subtasks: List["Subtask"]
    ) -> Tuple[int, Node or None]:
        """
        Expand a node in the task tree (with cost evaluation).
        """
        # 1) SlotHandler로 time slot 체크
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node, subtask, self.constraint_handler.get_time_slot_and_urgency
        )
        if time_slot is None:
            log.warning(
                f"No available time slot for subtask '{subtask.name}'. Skipping."
            )
            return (999999, None)

        # 2) 대기 시간 등 처리
        if time_slot > 0:
            (updated_parent, wait_time, updated_subtasks) = (
                self.slot_handler.handle_time_slots(
                    parent_node,
                    subtask,
                    remaining_subtasks,
                    time_slot,
                    self.constraint_handler.get_expandable_subtasks,
                )
            )
            # 대기가 필요하면 기다린 후에 subtask 노드 추가
            if wait_time > 0:
                updated_parent = self.tree.add_wait_node(
                    updated_parent, subtask.name, wait_time
                )
            parent_node = updated_parent
            new_subtasks = updated_subtasks
        else:
            # time_slot == 0이라면 바로 시작 가능
            new_subtasks = remaining_subtasks

        # 3) Subtask 노드 추가
        new_node = self.tree.add_subtask_node(parent_node, subtask)

        # 4) 비용 계산
        cost_val = self._evaluate_node(new_node, subtask)

        return (cost_val, new_node)

    def _can_expand_node(
        self, parent_node: Node, subtask: "Subtask", subtasks: List["Subtask"]
    ) -> bool:
        """
        Check if we can expand this parent_node with the given subtask.
        """
        time_slot, _ = self.slot_handler.compress_time_slots(
            parent_node, subtask, self.constraint_handler.get_time_slot_and_urgency
        )
        return time_slot is not None

    def _evaluate_node(self, node: Node, subtask: "Subtask") -> int:
        """
        Evaluate the cost of the newly created node.
        """
        duration_cost = subtask.duration.interval
        # soft_constraint_penalty = self.constraint_handler.get_soft_constraint_penalty(
        #     node, subtask
        # )
        # conflict_penalty = self.constraint_handler.get_conflict_penalty(node, subtask)
        # total_penalty = soft_constraint_penalty + conflict_penalty
        total_penalty = 0
        return duration_cost + total_penalty
