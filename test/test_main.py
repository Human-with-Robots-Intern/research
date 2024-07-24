import json
import os
import unittest
from unittest.mock import MagicMock, patch

from concept.env import Env
from concept.task import parse_tasks


class TestSchedulers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join("asset", "task_detach.json"), "r") as file:
            cls.tasks = parse_tasks(json.load(file))

    def setUp(self):
        self.env = Env()
        self.env.gen_dummpy(current_location="Living Room")

    def test_exhaustive_scheduler(self):
        from main import exhaustive_scheduler

        with patch("main.exhaustive_scheduler") as mock_exhaustive_scheduler:
            mock_exhaustive_scheduler(self.env, self.tasks)
            mock_exhaustive_scheduler.assert_called_once()


if __name__ == "__main__":
    unittest.main()
