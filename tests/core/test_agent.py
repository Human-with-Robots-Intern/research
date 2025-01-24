import unittest
from unittest.mock import MagicMock, patch

from core.agent import Agent


class TestBayesianAgent(unittest.TestCase):
    @patch("core.agent.BayesianAgent.get_task_duration")
    def test_load_(self, mock_get_task_duration):
        # Mock the return value of get_task_duration
        mock_get_task_duration.return_value = 5.0

        # Create a mock subtask with a duration attribute
        mock_subtask = MagicMock()
        mock_subtask.name = "mock_subtask"
        mock_subtask.duration.interval = None

        # Create a mock task with a list of subtasks
        mock_task = MagicMock()
        mock_task.subtasks = [mock_subtask]

        # Create a list of tasks
        tasks = [mock_task]

        # Initialize the BayesianAgent
        agent = Agent(robot=None, use_knowledge=False)

        # Call the load_ method
        result = agent.load_(tasks)

        # Check if get_task_duration was called with the correct subtask
        mock_get_task_duration.assert_called_with(mock_subtask)

        # Check if the subtask duration interval was updated
        self.assertEqual(mock_subtask.duration.interval, 5.0)

        # Check if the result is the same as the input tasks
        self.assertEqual(result, tasks)


if __name__ == "__main__":
    unittest.main()
