import json
import unittest

from concept import (
    Subtask,
    Task,
    get_all_controllable_subtasks,
    get_subtask_dict,
    parse_tasks,
)


class TestTaskModule(unittest.TestCase):

    def setUp(self):
        with open("task.json", "r") as f:
            self.data = json.load(f)
        self.tasks = parse_tasks(self.data)

    def test_subtask_creation(self):
        subtask = Subtask("Kitchen", "Test Subtask", 10, "Controllable")
        self.assertEqual(subtask.name, "Test Subtask")
        self.assertEqual(subtask.duration, 10)
        self.assertEqual(subtask.type, "Controllable")
        self.assertEqual(subtask.constraints, None)

    def test_task_creation(self):
        task = Task(
            "Test Task", "Kitchen", [("Test Subtask", 10, "Controllable", None)]
        )
        self.assertEqual(task.name, "Test Task")
        self.assertEqual(task.location, "Kitchen")
        self.assertEqual(len(task.subtasks), 1)

    def test_parse_tasks(self):
        self.assertEqual(len(self.tasks), 4)

    def test_get_controllable_subtasks(self):
        task = self.tasks[0]
        controllable_subtasks = task.get_controllable_subtasks()
        self.assertEqual(controllable_subtasks, ["Toast Start", "Toast End"])

    def test_is_contain_uncontrollable(self):
        task = self.tasks[0]
        self.assertFalse(task.is_contain_uncontrollable())

    def test_check_containing(self):
        task = self.tasks[0]
        self.assertTrue(task.check_containing("Toast Start"))
        self.assertFalse(task.check_containing("Nonexistent Subtask"))

    def test_get_total_seq_duration(self):
        task = self.tasks[0]
        self.assertEqual(task.get_total_seq_duration(), 3)

    def test_get_subtask_dict(self):
        subtask_dict = get_subtask_dict(self.tasks)
        self.assertEqual(subtask_dict["Toast Start"], "Toast")
        self.assertEqual(subtask_dict["Clean Restroom"], "Clean-restroom")

    def test_get_all_controllable_subtasks(self):
        controllable_subtasks = get_all_controllable_subtasks(self.tasks)
        expected_subtasks = [
            "Toast Start",
            "Toast End",
            "Clean Restroom",
            "Start Laundry",
            "End Laundry",
            "Pour-milk",
        ]
        self.assertEqual(controllable_subtasks, expected_subtasks)


if __name__ == "__main__":
    unittest.main()
