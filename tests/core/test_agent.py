import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, mock_open, patch

import numpy as np
import pytest

# Assuming Agent and related classes/constants are importable
from src.core.agent import (
    AGENT_KNOWLEDGE_PATH,
    ESTIMATE_FILE_NAME,
    FACTOR_ALPHA,
    GROUND_TRUTH_FILE_NAME,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
    MIN_VARIANCE,
    Agent,
)
from src.core.dataclass import CompletedEntry, SchedulerState  # Assuming these exist
from src.core.task import Duration, Execution, Subtask
from src.utils.config import constants as config_constants  # For default durations etc.

# Mock necessary external dependencies if Agent uses them directly
# We will mostly patch methods within Agent or its dependencies


class TestAgent(unittest.TestCase):

    def setUp(self):
        """Set up common mock objects and Agent instance."""
        # Mock dependencies needed for Agent initialization and methods
        self.mock_constraint_handler = MagicMock()
        # Patch external functions/classes used by Agent
        self.patcher_load_file = patch("src.utils.io_utils.load_file", autospec=True)
        self.patcher_json_dump = patch("json.dump", autospec=True)
        self.patcher_open = patch("builtins.open", mock_open())
        self.patcher_ssm_instance = patch(
            "src.utils.nlp.SentenceSimilarityModel.get_instance", autospec=True
        )
        self.patcher_extract_target = patch(
            "src.utils.common.extract_monitoring_target_name", autospec=True
        )
        self.patcher_get_crit_start = patch(
            "src.utils.task.constraints_util.get_critical_start_info", autospec=True
        )
        self.patcher_np_random_normal = patch("numpy.random.normal", autospec=True)

        self.mock_load_file = self.patcher_load_file.start()
        self.mock_json_dump = self.patcher_json_dump.start()
        self.mock_open = self.patcher_open.start()
        self.mock_ssm_instance = self.patcher_ssm_instance.start()
        self.mock_extract_target = self.patcher_extract_target.start()
        self.mock_get_crit_start = self.patcher_get_crit_start.start()
        self.mock_np_random_normal = self.patcher_np_random_normal.start()

        # Configure default mock behaviors
        mock_ssm = self.mock_ssm_instance.return_value
        mock_ssm.get_similar_ref.return_value = "task_a"
        self.mock_np_random_normal.return_value = 10.0

        # Default knowledge for tests
        self.mock_prior = {"Task_A": {"expected_duration": 10.0, "variance": 2.0}}
        self.mock_ground_truth = {"Task_A": 12.0, "Task_B": 20.0}

        # Configure load_file mocks
        def load_side_effect(filepath, mode="json"):
            filename = Path(filepath).name
            if filename == ESTIMATE_FILE_NAME:
                return copy.deepcopy(self.mock_prior)
            elif filename == GROUND_TRUTH_FILE_NAME:
                return copy.deepcopy(self.mock_ground_truth)
            else:
                raise FileNotFoundError(f"File not found: {filepath}")

        self.mock_load_file.side_effect = load_side_effect

        # Initialize Agent instance for tests
        self.agent = Agent(constraint_handler=self.mock_constraint_handler)

    def tearDown(self):
        """Stop all patchers."""
        self.patcher_load_file.stop()
        self.patcher_json_dump.stop()
        self.patcher_open.stop()
        self.patcher_ssm_instance.stop()
        self.patcher_extract_target.stop()
        self.patcher_get_crit_start.stop()
        self.patcher_np_random_normal.stop()

    def test_init_loads_knowledge_lowercase(self):
        """Test Agent initialization loads knowledge and converts keys to lowercase."""
        self.assertEqual(self.mock_load_file.call_count, 2)
        self.mock_load_file.assert_any_call(
            AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME, "json"
        )
        self.mock_load_file.assert_any_call(
            AGENT_KNOWLEDGE_PATH / GROUND_TRUTH_FILE_NAME, "json"
        )

        self.assertIn("task_a", self.agent.estimate_knowledge)
        self.assertIn("task_a", self.agent.ground_truth_knowledge)
        self.assertIn("task_b", self.agent.ground_truth_knowledge)
        self.assertNotIn("Task_A", self.agent.estimate_knowledge)
        self.assertNotIn("Task_A", self.agent.ground_truth_knowledge)
        self.assertNotIn("Task_B", self.agent.ground_truth_knowledge)

    def test_init_handles_file_not_found(self):
        """Test Agent initialization handles missing knowledge files."""
        self.mock_load_file.side_effect = FileNotFoundError
        self.patcher_load_file.stop()
        patcher_temp = patch(
            "src.utils.io_utils.load_file", side_effect=FileNotFoundError
        )
        mock_load_temp = patcher_temp.start()

        agent_no_files = Agent(constraint_handler=self.mock_constraint_handler)

        self.assertEqual(agent_no_files.estimate_knowledge, {})
        self.assertEqual(agent_no_files.ground_truth_knowledge, {})

        patcher_temp.stop()
        self.patcher_load_file.start()

    def test_get_prior_estimate_existing(self):
        """Test retrieving prior estimate for an existing task."""
        mean, variance = self.agent._get_prior_estimate("task_a")
        self.assertEqual(mean, 10.0)
        self.assertEqual(variance, 2.0)

        mean_upper, variance_upper = self.agent._get_prior_estimate("Task_A")
        self.assertEqual(mean_upper, 10.0)
        self.assertEqual(variance_upper, 2.0)

    def test_get_prior_estimate_new_task(self):
        """Test initializing and retrieving prior estimate for a new task."""
        self.assertNotIn("new_task", self.agent.estimate_knowledge)
        mean, variance = self.agent._get_prior_estimate("new_task")
        self.assertEqual(mean, INIT_PRIOR_MEAN)
        expected_variance = max(INIT_PRIOR_VARIANCE, MIN_VARIANCE)
        self.assertAlmostEqual(variance, expected_variance)
        self.assertIn("new_task", self.agent.estimate_knowledge)
        self.assertEqual(
            self.agent.estimate_knowledge["new_task"]["expected_duration"],
            INIT_PRIOR_MEAN,
        )

    def test_get_prior_estimate_min_variance(self):
        """Test prior variance is clamped at MIN_VARIANCE."""
        self.agent.estimate_knowledge["low_var_task"] = {
            "expected_duration": 5.0,
            "variance": 1e-10,
        }
        mean, variance = self.agent._get_prior_estimate("low_var_task")
        self.assertAlmostEqual(variance, MIN_VARIANCE)

    def test_bayesian_estimate_success_flow(self):
        """Test the high-level flow of bayesian_estimate."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_A", subtask_type="Monitor"
        )
        mock_state = MagicMock(spec=SchedulerState)
        mock_state.subtask = mock_subtask
        mock_state.current_time = 15.0
        completed_start_task = self._create_mock_subtask("StartTask")
        mock_state.completed_entries = [
            CompletedEntry(
                subtask=completed_start_task, sim_start_time=0.0, sim_end_time=5.0
            )
        ]
        mock_state.constraints = MagicMock()

        self.mock_extract_target.return_value = "Task_A"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_a"
        self.mock_get_crit_start.return_value = (
            "StartTask",
            5.0,
        )

        expected_post_mean = 10.0
        expected_post_var = 1.0

        updated_state, result_info = self.agent.bayesian_estimate(mock_state)

        self.mock_extract_target.assert_called_once_with("Monitor Task_A")
        self.agent.sentence_sim_model.get_similar_ref.assert_called_once_with(
            query_str="task_a", ref_strs=list(self.agent.estimate_knowledge.keys())
        )
        self.mock_get_crit_start.assert_called_once_with(
            subtask_name="task_a",
            completed=mock_state.completed_entries,
            constraints=mock_state.constraints,
            constraint_handler=self.mock_constraint_handler,
        )
        self.assertAlmostEqual(
            self.agent.estimate_knowledge["task_a"]["expected_duration"],
            expected_post_mean,
        )
        self.assertAlmostEqual(
            self.agent.estimate_knowledge["task_a"]["variance"], expected_post_var
        )

        self.assertIsNotNone(result_info)
        self.assertEqual(result_info["updated_subtask_name"], "StartTask")
        self.assertAlmostEqual(result_info["original_expected_time"], 10.0)
        self.assertAlmostEqual(result_info["updated_expected_time"], expected_post_mean)
        self.assertAlmostEqual(result_info["ground_truth_time"], 12.0)
        self.assertAlmostEqual(result_info["posterior_variance"], expected_post_var)

        self.assertEqual(updated_state, mock_state)

    def test_bayesian_estimate_missing_ground_truth(self):
        """Test bayesian_estimate handles missing ground truth gracefully."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_C", subtask_type="Monitor"
        )
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=10.0,
            completed_entries=[],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_C"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_c"

        updated_state, result_info = self.agent.bayesian_estimate(mock_state)

        self.assertIn("task_c", self.agent.estimate_knowledge)
        self.assertIsNotNone(result_info)
        self.assertIsNone(result_info.get("ground_truth_time"))

    def test_bayesian_estimate_crit_start_exception(self):
        """Test bayesian_estimate handles exception from get_critical_start_info."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_A", subtask_type="Monitor"
        )
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=15.0,
            completed_entries=[],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_A"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_a"
        self.mock_get_crit_start.side_effect = Exception("Failed to get critical info")

        updated_state, result_info = self.agent.bayesian_estimate(mock_state)

        self.assertIs(updated_state, mock_state)
        self.assertEqual(result_info, {})

    def test_bayesian_estimate_negative_elapsed_time(self):
        """Test bayesian_estimate handles negative elapsed time by clamping to 0."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_A", subtask_type="Monitor"
        )
        completed_start_task = self._create_mock_subtask("StartTask")
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=3.0,
            completed_entries=[
                CompletedEntry(
                    subtask=completed_start_task, sim_start_time=0.0, sim_end_time=5.0
                )
            ],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_A"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_a"
        self.mock_get_crit_start.return_value = ("StartTask", 5.0)

        self.mock_np_random_normal.reset_mock()
        self.mock_np_random_normal.return_value = 0.0

        self.agent.bayesian_estimate(mock_state)

        self.mock_np_random_normal.assert_called_once()
        call_args, call_kwargs = self.mock_np_random_normal.call_args
        passed_loc = call_kwargs.get("loc", call_args[0])
        self.assertEqual(passed_loc, 0)

    def test_save_knowledge_to_file_success(self):
        """Test saving knowledge calls json.dump correctly."""
        self.agent.estimate_knowledge = {
            "task_c": {"expected_duration": 1.0, "variance": 0.1}
        }
        self.agent.bayesian_estimate(MagicMock(spec=SchedulerState))
        self.mock_json_dump.assert_called_once_with(
            self.agent.estimate_knowledge, ANY, indent=4, ensure_ascii=False
        )

    def test_save_knowledge_to_file_empty(self):
        """Test saving knowledge when the knowledge base is empty."""
        self.agent.estimate_knowledge = {}
        mock_monitor_subtask = self._create_mock_subtask(
            "Monitor Task_X", subtask_type="Monitor"
        )
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_monitor_subtask,
            current_time=1.0,
            completed_entries=[],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_X"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_x"
        self.mock_get_crit_start.return_value = ("StartTaskX", 0.0)
        self.mock_np_random_normal.return_value = INIT_PRIOR_MEAN

        self.mock_open.reset_mock()
        self.mock_json_dump.reset_mock()

        self.agent.bayesian_estimate(mock_state)

        self.mock_open.assert_called_once_with(
            AGENT_KNOWLEDGE_PATH / ESTIMATE_FILE_NAME, "w"
        )
        file_handle = self.mock_open.return_value.__enter__.return_value
        self.mock_json_dump.assert_called_once_with(
            self.agent.estimate_knowledge, file_handle, indent=4, ensure_ascii=False
        )
        self.assertIn("task_x", self.agent.estimate_knowledge)

    def test_save_knowledge_to_file_exception(self):
        """Test exception handling during knowledge saving."""
        self.mock_json_dump.side_effect = IOError("Disk full")

        mock_monitor_subtask = self._create_mock_subtask(
            "Monitor Task_A", subtask_type="Monitor"
        )
        mock_start_subtask = self._create_mock_subtask("StartTask")
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_monitor_subtask,
            current_time=15.0,
            completed_entries=[
                CompletedEntry(
                    subtask=mock_start_subtask, sim_start_time=0.0, sim_end_time=5.0
                )
            ],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_A"
        self.agent.sentence_sim_model.get_similar_ref.return_value = "task_a"
        self.mock_get_crit_start.return_value = ("StartTask", 5.0)

        try:
            self.agent.bayesian_estimate(mock_state)
        except IOError:
            self.fail("IOError from json.dump was not handled by Agent.")

        self.mock_json_dump.assert_called_once()

    # Helper to create mock Subtasks correctly
    def _create_mock_subtask(self, name, subtask_type="Action", execution_status=True):
        mock_subtask = MagicMock(spec=Subtask)
        mock_subtask.name = name
        mock_subtask.subtask_type = subtask_type
        mock_subtask.execution = Execution(
            objects={}, primitive_actions=[f"ACTION {name}"]
        )
        mock_subtask.duration = Duration(type="Fixed", interval=1.0)
        mock_subtask.temporal_constraints = []
        mock_subtask.repetition = 1
        mock_subtask.execution_status = execution_status
        return mock_subtask
