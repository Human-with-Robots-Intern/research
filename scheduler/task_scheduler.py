from collections import deque
from queue import PriorityQueue

from anytree import Node, RenderTree

from concept.env import Env
from concept.task import Task


class TaskProfiler:
    def __init__(self, env: Env):
        self.env = env

    def unctl_priority_scoring(self, task: Task) -> int:
        """Priority scoring for Uncontrollable task"""
        priority_score = 0
        for subtask in task.subtasks:
            if subtask.type == "Uncontrollable":
                risk_score = 2 if subtask.constraints == "Temperature" else 1
                priority_score -= subtask.duration * risk_score + self.env.get_cost(
                    task.location
                )
        return priority_score

    def ctl_priority_scoring(self, task: Task) -> int:
        """Priority scoring for Controllable task"""
        priority_score = 0
        for subtask in task.subtasks:
            priority_score -= subtask.duration + self.env.get_cost(task.location)
        return priority_score

    def priority_classify(
        self, tasks: list[Task]
    ) -> tuple[PriorityQueue, PriorityQueue]:
        """Classify tasks into uncontrollable and controllable priority queues"""
        unctl_task_que = PriorityQueue()
        ctl_task_que = PriorityQueue()

        for task in tasks:
            if task.is_contain_uncontrollable():
                unctl_task_que.put((self.unctl_priority_scoring(task), task))
            else:
                ctl_task_que.put((self.ctl_priority_scoring(task), task))

        return unctl_task_que, ctl_task_que


class TaskScheduler:
    def __init__(
        self, env: Env, task_ques: tuple[PriorityQueue, PriorityQueue]
    ) -> None:
        """Initialize the TaskScheduler with environment and task queues"""
        self.env = env
        self.in_progress_que = deque()
        self.unctl_task_que, self.ctl_task_que = task_ques
        self.root_node = None
        self.init_tree()

    def init_tree(self):
        if not self.unctl_task_que.empty():
            self.process_first_unctl_task()
        else:
            print("No uncontrollable tasks available to initialize the tree.")

    def process_first_unctl_task(self):
        _, task = self.unctl_task_que.get()
        subtask = task.subtasks.popleft()

        if self.env.current_location != subtask.location:
            self.root_node = Node(self.env.move(subtask.location))
            child_node = Node(subtask, parent=self.root_node)
            self.in_progress_que.append(task)
            self.construct_tree(child_node)
        else:
            self.root_node = Node(subtask)
            self.env.current_location = subtask.location
            self.in_progress_que.append(task)
            self.construct_tree(self.root_node)

    def construct_tree(self, parent):
        while not self.queues_are_empty():
            next_subtask, task, queue_type = self.select_next_subtask()
            if next_subtask is None:
                break
            self.update_queues(task, queue_type)

            if self.env.current_location != next_subtask.location:
                move_node = Node(self.env.move(next_subtask.location), parent=parent)
                child_node = Node(next_subtask, parent=move_node)
            else:
                child_node = Node(next_subtask, parent=parent)

            parent = child_node  # Move to the next node

    def queues_are_empty(self):
        return (
            self.ctl_task_que.empty()
            and self.unctl_task_que.empty()
            and not self.in_progress_que
        )

    def select_next_subtask(self):
        ctl_score, ctl_subtask, ctl_task = self.get_next_task(self.ctl_task_que)
        unctl_score, unctl_subtask, unctl_task = self.get_next_task(self.unctl_task_que)
        in_progress_score, in_progress_subtask, in_progress_task = (
            self.get_in_progress_task()
        )

        scores = [
            (ctl_score, ctl_subtask, ctl_task, "ctl"),
            (unctl_score, unctl_subtask, unctl_task, "unctl"),
            (in_progress_score, in_progress_subtask, in_progress_task, "in_progress"),
        ]

        min_score, next_subtask, task, queue_type = min(scores, key=lambda x: x[0])
        return next_subtask, task, queue_type

    def get_next_task(self, queue):
        if queue.empty():
            return float("inf"), None, None
        task = queue.queue[0][1]
        if not task.subtasks:
            return float("inf"), None, None
        subtask = task.subtasks[0]
        score = subtask.duration + self.env.get_cost(task.location)
        return score, subtask, task

    def get_in_progress_task(self):
        if not self.in_progress_que:
            return float("inf"), None, None
        scores = [
            (
                task.subtasks[0].duration + self.env.get_cost(task.location),
                task.subtasks[0],
                task,
            )
            for task in self.in_progress_que
            if task.subtasks
        ]
        if not scores:
            return float("inf"), None, None
        return min(scores, key=lambda x: x[0])

    def update_queues(self, task, queue_type):
        if queue_type == "ctl":
            self.ctl_task_que.get()
        elif queue_type == "unctl":
            self.unctl_task_que.get()
        task.subtasks.popleft()
        if task.subtasks:
            self.in_progress_que.append(task)
        elif task in self.in_progress_que:
            self.in_progress_que.remove(task)

    def generate_plan(self):
        plan = []

        for _, _, node in RenderTree(self.root_node):
            plan.append(node.name)

        return plan
