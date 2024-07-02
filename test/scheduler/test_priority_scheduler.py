import unittest
from collections import deque
from queue import PriorityQueue
from unittest.mock import MagicMock

import pandas as pd

from concept.env import Env
from concept.task import Subtask, Task
from scheduler.task_scheduler import TaskProfiler, TaskScheduler


class TestTaskProfiler(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.profiler = TaskProfiler(self.env)

        self.task1 = Task("Task1", "Kitchen", [("Subtask1", 10, "Controllable", None)])
        self.task2 = Task(
            "Task2", "Living Room", [("Subtask2", 15, "Uncontrollable", "Temperature")]
        )

    def test_unctl_priority_scoring(self):
        self.env.get_cost = MagicMock(return_value=1)
        score = self.profiler.unctl_priority_scoring(self.task2)
        expected_score = -(15 * 2 + 1)
        self.assertEqual(score, expected_score)

    def test_ctl_priority_scoring(self):
        self.env.get_cost = MagicMock(return_value=1)
        score = self.profiler.ctl_priority_scoring(self.task1)
        expected_score = -(10 + 1)
        self.assertEqual(score, expected_score)

    def test_priority_classify(self):
        tasks = [self.task1, self.task2]
        self.env.get_cost = MagicMock(return_value=1)
        unctl_que, ctl_que = self.profiler.priority_classify(tasks)
        self.assertEqual(unctl_que.qsize(), 1)
        self.assertEqual(ctl_que.qsize(), 1)


class TestTaskScheduler(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.task1 = Task("Task1", "Kitchen", [("Subtask1", 10, "Controllable", None)])
        self.task2 = Task(
            "Task2", "Living Room", [("Subtask2", 15, "Uncontrollable", "Temperature")]
        )
        profiler = TaskProfiler(self.env)
        unctl_que, ctl_que = profiler.priority_classify([self.task1, self.task2])
        self.scheduler = TaskScheduler(self.env, (unctl_que, ctl_que))

    def test_init_tree(self):
        self.assertIsNotNone(self.scheduler.root_node)

    def test_queues_are_empty(self):
        self.assertFalse(self.scheduler.queues_are_empty())
        self.scheduler.in_progress_que = deque()
        self.scheduler.ctl_task_que = PriorityQueue()
        self.scheduler.unctl_task_que = PriorityQueue()
        self.assertTrue(self.scheduler.queues_are_empty())

    def test_generate_schedule(self):
        self.scheduler.construct_tree(self.scheduler.root_node)
        df = self.scheduler.generate_schedule()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)


if __name__ == "__main__":
    unittest.main()
