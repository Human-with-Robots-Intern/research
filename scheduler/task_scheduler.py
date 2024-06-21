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
                if subtask.constraints == "Temperature":
                    risk_score = 2
                else:
                    risk_score = 1

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
    def __init__(self, env: Env, task_ques: tuple) -> None:
        """Initialize the TaskScheduler with environment and task queues"""
        self.env = env
        self.in_progress_que = deque()
        self.unctl_task_que, self.ctl_task_que = task_ques
        self.init_tree()
        self.render_tree

    def init_tree(self):
        if self.unctl_task_que.qsize() > 0:
            # Get the first uncontrollable task's subtask
            _, task = self.unctl_task_que.get()
            subtask = task.subtasks.popleft()

            # Insert subtask into the tree node
            root_node = Node(subtask)
            self.env.current_location = task.location

            # Add task to in-progress queue
            self.in_progress_que.append(task)
            self.construct_tree(root_node)
        else:
            print("No uncontrollable tasks available to initialize the tree.")

    def construct_tree(self, parent):
        if (
            self.ctl_task_que.qsize() == 0
            and self.unctl_task_que.qsize() == 0
            and len(self.in_progress_que) == 0
        ):
            return  # Base case to stop recursion

        ctl_score = unctl_score = in_progress_score = float("inf")
        ctl_subtask = unctl_subtask = in_progress_subtask = None

        # Check controllable task queue
        if self.ctl_task_que.qsize() > 0:
            ctl_task = self.ctl_task_que.queue[0][1]
            ctl_subtask = ctl_task.subtasks[0]
            ctl_score = ctl_subtask.duration + self.env.get_cost(ctl_task.location)

        # Check uncontrollable task queue
        if self.unctl_task_que.qsize() > 0:
            unctl_task = self.unctl_task_que.queue[0][1]
            unctl_subtask = unctl_task.subtasks[0]
            unctl_score = unctl_subtask.duration + self.env.get_cost(
                unctl_task.location
            )

        # Check in-progress queue
        in_progress_scores = []
        for i in range(len(self.in_progress_que)):
            in_progress_task = self.in_progress_que[i]
            in_progress_subtask = in_progress_task.subtasks[0]
            in_progress_score = in_progress_subtask.duration + self.env.get_cost(
                in_progress_task.location
            )
            in_progress_scores.append(in_progress_score)

        if in_progress_scores:
            in_progress_score = min(in_progress_scores)
            in_progress_idx = in_progress_scores.index(in_progress_score)
            in_progress_task = self.in_progress_que[in_progress_idx]
            in_progress_subtask = in_progress_task.subtasks[0]

        # Determine minimum score and select the next subtask
        min_score = min(ctl_score, in_progress_score, unctl_score)

        if min_score == ctl_score:
            _, task = self.ctl_task_que.get()
            subtask = task.subtasks.popleft()
            self.env.current_location = task.location
            self.in_progress_que.append(task)
            child_node = Node(subtask, parent=parent)

        elif min_score == unctl_score:
            _, task = self.unctl_task_que.get()
            subtask = task.subtasks.popleft()
            self.env.current_location = task.location
            self.in_progress_que.append(task)
            child_node = Node(subtask, parent=parent)

        else:
            task = self.in_progress_que[in_progress_idx]
            subtask = task.subtasks.popleft()
            self.env.current_location = task.location
            child_node = Node(subtask, parent=parent)

            if not task.subtasks:
                self.in_progress_que.remove(task)

        self.construct_tree(child_node)


# Example usage:
# env = Env()  # Assume Env is properly defined
# tasks = [...]  # Assume this is a list of Task objects
# profiler = TaskProfiler(env)
# task_ques = profiler.priority_classify(tasks)
# scheduler = TaskScheduler(env, task_ques)
# root = scheduler.init_tree()
