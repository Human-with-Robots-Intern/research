import json
import os
import unittest
from unittest.mock import MagicMock, patch

from concept.env import Env
from concept.task import parse_tasks
from scheduler.milp_solver import SchedulingProblem
from scheduler.task_scheduler import TaskProfiler, TaskScheduler
from util.visualizer import visualize, visualize2


class TestSchedulers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join("asset", "task_detach.json"), "r") as file:
            cls.tasks = parse_tasks(json.load(file))

    def setUp(self):
        self.env = Env()
        self.env.gen_dummpy(current_location="Living Room")

    @patch("scheduler.milp_solver.SchedulingProblem.solve")
    @patch("scheduler.milp_solver.SchedulingProblem.extract_schedule")
    def test_milp_scheduler(self, mock_extract_schedule, mock_solve):
        mock_solve.return_value = "Optimal"
        mock_extract_schedule.return_value = [("Task1", 0, 10), ("Task2", 10, 20)]

        scheduler = SchedulingProblem(self.tasks)
        scheduler.solve = mock_solve
        scheduler.extract_schedule = mock_extract_schedule

        with patch("scheduler_task_scheduler.visualize") as mock_visualize:
            from main import milp_scheduler

            milp_scheduler(self.tasks)

            mock_solve.assert_called_once()
            mock_extract_schedule.assert_called_once()
            mock_visualize.assert_called_once()

    @patch("scheduler.task_scheduler.TaskScheduler.generate_schedule")
    def test_priority_scheduler(self, mock_generate_schedule):
        mock_generate_schedule.return_value = [
            {"name": "Task1", "start": 0, "duration": 10},
            {"name": "Task2", "start": 10, "duration": 10},
        ]

        task_profiler = TaskProfiler(self.env)
        task_ques = task_profiler.priority_classify(self.tasks)
        task_scheduler = TaskScheduler(self.env, task_ques)
        task_scheduler.generate_schedule = mock_generate_schedule

        with patch("scheduler_task_scheduler.visualize2") as mock_visualize2:
            from main import priority_scheduler

            priority_scheduler(self.env, self.tasks)

            mock_generate_schedule.assert_called_once()
            mock_visualize2.assert_called_once()

    def test_exhaustive_scheduler(self):
        from main import exhaustive_scheduler

        with patch("main.exhaustive_scheduler") as mock_exhaustive_scheduler:
            mock_exhaustive_scheduler(self.env, self.tasks)
            mock_exhaustive_scheduler.assert_called_once()


if __name__ == "__main__":
    unittest.main()
