import unittest
from unittest.mock import MagicMock

import pulp

from concept.env import Env
from concept.task import Subtask, Task, get_all_controllable_subtasks
from scheduler import SchedulingProblem, TaskScheduler


class TestSchedulingProblem(unittest.TestCase):
    def setUp(self):
        self.env = Env()

        # Define some sample tasks
        subtasks1 = [
            Subtask("Kitchen", "Toast Start", 2, "Controllable"),
            Subtask("Kitchen", "Toast End", 1, "Controllable"),
        ]
        subtasks2 = [Subtask("Restroom", "Clean Restroom", 20, "Controllable")]
        subtasks3 = [
            Subtask("Restroom", "Start Laundry", 5, "Controllable"),
            Subtask("Restroom", "End Laundry", 10, "Controllable"),
        ]
        subtasks4 = [Subtask("Living Room", "Pour-milk", 10, "Controllable")]

        self.task1 = Task("Toast", "Kitchen", subtasks1)
        self.task2 = Task("Clean-restroom", "Restroom", subtasks2)
        self.task3 = Task("Laundry", "Restroom", subtasks3)
        self.task4 = Task("Pour-milk", "Living Room", subtasks4)

        self.tasks = [self.task1, self.task2, self.task3, self.task4]
        self.scheduler = SchedulingProblem(self.tasks)

    def test_define_variables(self):
        self.scheduler.define_variables()
        self.assertIn("Start_time_Toast Start", self.scheduler.start_times)
        self.assertIn("Completion_time_Toast End", self.scheduler.completion_times)
        self.assertIn("Task_Toast Start", self.scheduler.task_vars)

    def test_set_objective(self):
        self.scheduler.set_objective()
        objective = self.scheduler.prob.objective
        self.assertIsInstance(objective, pulp.LpAffineExpression)
        self.assertEqual(objective.name, "Total_Completion_Time")

    def test_add_constraints(self):
        self.scheduler.add_constraints()
        constraints = self.scheduler.prob.constraints
        self.assertGreater(len(constraints), 0)

    def test_solve(self):
        self.scheduler.solve()
        status = pulp.LpStatus[self.scheduler.prob.status]
        self.assertIn(status, ["Optimal", "Infeasible", "Unbounded"])

    def test_extract_schedule(self):
        self.scheduler.solve()
        schedule = self.scheduler.extract_schedule()
        self.assertIsInstance(schedule, list)
        self.assertGreater(len(schedule), 0)
        for subtask in schedule:
            self.assertEqual(len(subtask), 3)


if __name__ == "__main__":
    unittest.main()
