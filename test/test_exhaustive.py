import unittest
from collections import deque
from itertools import permutations
from unittest.mock import MagicMock, patch

import pandas as pd
from anytree import Node, RenderTree

from concept.env import Env
from concept.task import Subtask, Task
from task_management.legacy.exhaustive_search import ExhaustiveSearch


class TestExhaustiveSearch(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.env.gen_dummpy()

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

    @patch("scheduler.task_scheduler.permutations")
    @patch("concept.env.Env.get_cost")
    def test_exhaustive_search(self, mock_get_cost, mock_permutations):
        mock_get_cost.return_value = 1
        mock_permutations.return_value = permutations(self.tasks)

        scheduler = ExhaustiveSearch(self.env, self.tasks)
        best_schedule = scheduler.exhaustive_search()

        self.assertIsNotNone(best_schedule)
        self.assertEqual(
            len(best_schedule), sum(len(task.subtasks) for task in self.tasks)
        )

    @patch("scheduler.exhaustive_search.ExhaustiveSearch")
    def test_init_tree(self, mock_exhaustive_search):
        mock_exhaustive_search.return_value = [
            Subtask("Kitchen", "Toast Start", 2, "Controllable"),
            Subtask("Kitchen", "Toast End", 1, "Controllable"),
            Subtask("Restroom", "Clean Restroom", 20, "Controllable"),
        ]

        scheduler = ExhaustiveSearch(self.env, self.tasks)
        self.assertIsNotNone(scheduler.root_node)
        self.assertEqual(scheduler.root_node.name, "Start")
        self.assertEqual(len(scheduler.root_node.children), 1)

    def test_generate_schedule(self):
        scheduler = ExhaustiveSearch(self.env, self.tasks)
        scheduler.root_node = Node("Start")
        parent = scheduler.root_node
        for subtask in [
            Subtask("Kitchen", "Toast Start", 2, "Controllable"),
            Subtask("Kitchen", "Toast End", 1, "Controllable"),
            Subtask("Restroom", "Clean Restroom", 20, "Controllable"),
        ]:
            if self.env.current_location != subtask.location:
                move_node = Node(self.env.move(subtask.location), parent=parent)
                parent = Node(subtask, parent=move_node)
            else:
                parent = Node(subtask, parent=parent)
            self.env.current_location = subtask.location

        df = scheduler.generate_schedule()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 3)


if __name__ == "__main__":
    unittest.main()
