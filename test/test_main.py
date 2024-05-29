import unittest

from scheduling_problem import SchedulingProblem
from task import Task
from visualization import ScheduleVisualizer


class TestMainIntegration(unittest.TestCase):
    def setUp(self):
        self.tasks = {
            "Cook_Steak": Task(
                "Cook_Steak",
                [
                    ("Start", 5, "Controllable"),
                    ("Continue", 20, "Uncontrollable"),
                    ("End", 10, "Controllable"),
                ],
            ),
            "Wash_Dishes": Task(
                "Wash_Dishes",
                [
                    ("Start", 5, "Controllable"),
                    ("Continue", 5, "Controllable"),
                    ("End", 5, "Controllable"),
                ],
            ),
            "Clean_Living_Room": Task(
                "Clean_Living_Room",
                [
                    ("Start", 5, "Controllable"),
                    ("Continue", 5, "Controllable"),
                    ("End", 5, "Controllable"),
                ],
            ),
            "Laundry": Task(
                "Laundry",
                [
                    ("Start", 5, "Controllable"),
                    ("Continue", 45, "Uncontrollable"),
                    ("End", 5, "Controllable"),
                ],
            ),
        }

    def test_full_workflow(self):
        scheduler = SchedulingProblem(self.tasks)
        scheduler.define_variables()
        scheduler.set_objective()
        scheduler.add_constraints()

        status = scheduler.solve()
        self.assertEqual(status, "Optimal")

        schedule = scheduler.extract_schedule()
        self.assertTrue(len(schedule) > 0)
        for subtask, start, end in schedule:
            self.assertTrue(start >= 0)
            self.assertTrue(end > start)

        try:
            ScheduleVisualizer.visualize(schedule)
        except Exception as e:
            self.fail(f"ScheduleVisualizer.visualize() raised an exception: {e}")


if __name__ == "__main__":
    unittest.main()
