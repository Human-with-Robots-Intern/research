import unittest

from task import Task


class TestTask(unittest.TestCase):
    def setUp(self):
        self.task = Task(
            "Test_Task",
            [
                ("Start", 5, "Controllable"),
                ("Continue", 10, "Uncontrollable"),
                ("End", 5, "Controllable"),
            ],
        )

    def test_get_controllable_subtasks(self):
        expected_subtasks = ["Test_Task_Start", "Test_Task_End"]
        self.assertEqual(self.task.get_controllable_subtasks(), expected_subtasks)

    def test_get_duration(self):
        expected_duration = 20
        self.assertEqual(self.task.get_duration(), expected_duration)


if __name__ == "__main__":
    unittest.main()
