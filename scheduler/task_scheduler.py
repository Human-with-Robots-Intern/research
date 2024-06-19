from queue import PriorityQueue

from concept.env import Env
from concept.task import Task


class TaskProfiler:
    def __init__(self, init_location="Kitchen") -> None:
        self.current_room = init_location

    def unctl_priority_scoring(self, env: Env, task: Task) -> int:
        """Task의 uncontrollable task가 갖는 총 작업 시간 * 위험도 점수"""
        print(task.name)
        print(env.get_cost(self.current_room, task.location))
        priority_score = 0
        for subtask in task.subtasks:
            if subtask.type == "Uncontrollable":

                if subtask.constraints == "Temperature":
                    risk_score = 2
                else:
                    risk_score = 1

                priority_score -= (
                    subtask.duration + env.get_cost(self.current_room, task.location)
                ) * risk_score

        return priority_score

    def ctl_priority_scoring(self, env: Env, task: Task) -> int:
        """Task의 controllable task가 갖는 총 작업 시간"""
        print(task.name)
        print(env.get_cost(self.current_room, task.location))
        priority_score = 0
        for subtask in task.subtasks:
            priority_score -= subtask.duration + env.get_cost(
                self.current_room, task.location
            )
        return priority_score

    def priority_classify(
        self, env: Env, tasks: list[Task]
    ) -> tuple[PriorityQueue, PriorityQueue]:
        """task 항목을 순회하면서, constraints가 존재하는 (uncontrollable) task를 priority queue에 올림

        Args:
            tasks (list[Task]): task 전체 목록

        Returns:
            PriorityQueue: 제약 조건 존재 task
            PriorityQueue: 제약 조건 미존재 task
        """

        priority_task_que = PriorityQueue()
        non_priority_task_que = PriorityQueue()

        for task in tasks:

            if task.is_contain_uncontrollable():
                priority_task_que.put(
                    (self.unctl_priority_scoring(env, task), task.name, task)
                )
            else:
                non_priority_task_que.put(
                    (self.ctl_priority_scoring(env, task), task.name, task)
                )

        return priority_task_que, non_priority_task_que


class TaskScheduler:
    def __init__(self) -> None:
        """두종류의 queue를 이용하여 Task Sequence를 만듦

        Args:
            priority_tasks (PriorityQueue): 긴급한 작업 큐
            non_priority_tasks (PriorityQueue): 긴급하지 않은 작업 큐
        """
        pass
