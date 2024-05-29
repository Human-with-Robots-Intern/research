import unittest

from scheduling_problem import SchedulingProblem
from task import Task


class TestSchedulingProblem(unittest.TestCase):
    def setUp(self):
        self.tasks = {
            "Test_Task": Task(
                "Test_Task",
                [
                    ("Start", 5, "Controllable"),
                    ("Continue", 10, "Uncontrollable"),
                    ("End", 5, "Controllable"),
                ],
            )
        }
        self.scheduler = SchedulingProblem(self.tasks)
        self.scheduler.define_variables()
        self.scheduler.set_objective()
        self.scheduler.add_constraints()

    def test_define_variables(self):
        self.assertTrue(len(self.scheduler.start_times) > 0)
        self.assertTrue(len(self.scheduler.completion_times) > 0)
        self.assertTrue(len(self.scheduler.task_vars) > 0)

    def test_solve(self):
        status = self.scheduler.solve()
        self.assertEqual(status, "Optimal")

    def test_extract_schedule(self):
        self.scheduler.solve()
        schedule = self.scheduler.extract_schedule()
        self.assertTrue(len(schedule) > 0)
        for subtask, start, end in schedule:
            self.assertTrue(start >= 0)
            self.assertTrue(end > start)


if __name__ == "__main__":
    unittest.main()
