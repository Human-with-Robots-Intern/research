import json
import unittest

from concept.task import *


class TestTaskSubtask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load data from the given JSON path
        with open("/home/dongkyu/pdk_ws/research/asset/task_detach.json") as file:
            cls.data = json.load(file)

        cls.tasks = parse_tasks(cls.data)

    def test_subtask_initialization(self):
        subtask_data = self.data[0]["Subtasks"][0]
        subtask = Subtask(
            self.data[0]["Task"],
            self.data[0]["Location"],
            subtask_data["Subtask"],
            subtask_data["Type"],
            subtask_data["Duration"]["Interval"],
            subtask_data["Constraints"]["TemporalConstraint"],
        )
        self.assertEqual(subtask.name, subtask_data["Subtask"])
        self.assertEqual(subtask.type, subtask_data["Type"])
        self.assertEqual(subtask.duration, subtask_data["Duration"]["Interval"])
        self.assertEqual(
            subtask.constraints, subtask_data["Constraints"]["TemporalConstraint"]
        )

    def test_task_initialization(self):
        task_data = self.data[0]
        task = Task(
            task_data["Task"],
            task_data["Location"],
            [
                (
                    subtask["Subtask"],
                    subtask["Type"],
                    subtask["Duration"]["Interval"],
                    subtask["Constraints"]["TemporalConstraint"],
                )
                for subtask in task_data["Subtasks"]
            ],
        )
        self.assertEqual(task.name, task_data["Task"])
        self.assertEqual(task.location, task_data["Location"])
        self.assertEqual(len(task.subtasks), len(task_data["Subtasks"]))

    def test_get_total_seq_duration(self):
        task = self.tasks[0]
        expected_duration = sum(
            subtask["Duration"]["Interval"] for subtask in self.data[0]["Subtasks"]
        )
        self.assertEqual(task.get_total_seq_duration(), expected_duration)

    def test_get_all_subtasks(self):
        subtasks_by_name = get_all_subtasks(self.tasks, mode="name")
        for task in self.tasks:
            for subtask in task.subtasks:
                self.assertEqual(subtasks_by_name[subtask.name], task.name)

        subtasks_all = get_all_subtasks(self.tasks, mode="all")
        for task, subtasks in zip(self.tasks, subtasks_all):
            self.assertEqual(len(subtasks), len(task.subtasks))
            for subtask_obj, subtask_data in zip(subtasks, task.subtasks):
                self.assertEqual(subtask_obj.name, subtask_data.name)
                self.assertEqual(subtask_obj.duration, subtask_data.duration)


if __name__ == "__main__":
    unittest.main()
