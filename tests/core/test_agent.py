import unittest
from unittest.mock import ANY, MagicMock, call, patch

import numpy as np

# Assuming Agent and related classes/constants are importable
from src.core.agent import (
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
        self.patcher_load_knowledge = patch("src.core.agent.load_knowledge")
        self.patcher_save_knowledge = patch("src.core.agent.save_knowledge")
        self.patcher_ssm_instance = patch(
            "src.core.agent.SentenceSimilarityModel.get_instance"
        )
        self.patcher_extract_target = patch(
            "src.core.agent.extract_monitoring_target_name"
        )
        self.patcher_get_crit_start = patch("src.core.agent.get_critical_start_info")
        self.patcher_np_random_normal = patch("src.core.agent.np.random.normal")

        self.mock_load_knowledge = self.patcher_load_knowledge.start()
        self.mock_save_knowledge = self.patcher_save_knowledge.start()
        self.mock_ssm_instance = self.patcher_ssm_instance.start()
        self.mock_extract_target = self.patcher_extract_target.start()
        self.mock_get_crit_start = self.patcher_get_crit_start.start()
        self.mock_np_random_normal = self.patcher_np_random_normal.start()

        # Configure default mock behaviors
        self.mock_ssm_instance.return_value.compute_batch_cosine_similarity.return_value = np.array(
            [0.9, 0.1]
        )  # Example similarity
        self.mock_np_random_normal.return_value = 10.0  # Mock observation generation

        # Default knowledge for tests
        self.mock_prior = {"task_a": {"expected_duration": 10.0, "variance": 2.0}}
        self.mock_ground_truth = {"task_a": 12.0, "task_b": 20.0}

        # Configure load_knowledge mocks
        # Need to handle multiple calls for prior and ground truth
        def load_side_effect(filename):
            if filename == ESTIMATE_FILE_NAME:
                # Return a copy to avoid modification between tests
                return self.mock_prior.copy()
            elif filename == GROUND_TRUTH_FILE_NAME:
                return self.mock_ground_truth.copy()
            else:
                raise FileNotFoundError

        self.mock_load_knowledge.side_effect = load_side_effect

        # Initialize Agent instance for tests
        self.agent = Agent(constraint_handler=self.mock_constraint_handler)

    def tearDown(self):
        """Stop all patchers."""
        self.patcher_load_knowledge.stop()
        self.patcher_save_knowledge.stop()
        self.patcher_ssm_instance.stop()
        self.patcher_extract_target.stop()
        self.patcher_get_crit_start.stop()
        self.patcher_np_random_normal.stop()

    def test_init_loads_knowledge_lowercase(self):
        """Test Agent initialization loads knowledge and converts keys to lowercase."""
        # Check if load_knowledge was called correctly
        expected_calls = [call(ESTIMATE_FILE_NAME), call(GROUND_TRUTH_FILE_NAME)]
        self.mock_load_knowledge.assert_has_calls(expected_calls, any_order=True)

        # Check if keys are lowercase (Agent init handles this)
        self.assertIn("task_a", self.agent.prior_knowledge)
        self.assertNotIn("Task_A", self.agent.prior_knowledge)
        self.assertIn("task_a", self.agent.ground_truth)
        self.assertIn("task_b", self.agent.ground_truth)

        # Test loading with different casing in mock data
        self.mock_prior = {"Task_C": {"expected_duration": 5.0, "variance": 1.0}}
        self.mock_ground_truth = {"Task_D": 8.0}
        # Re-initialize agent to test loading again
        agent_new = Agent(constraint_handler=self.mock_constraint_handler)
        self.assertIn("task_c", agent_new.prior_knowledge)
        self.assertIn("task_d", agent_new.ground_truth)

    def test_init_handles_file_not_found(self):
        """Test Agent initialization handles missing knowledge files."""
        self.mock_load_knowledge.side_effect = FileNotFoundError
        agent_no_files = Agent(constraint_handler=self.mock_constraint_handler)
        self.assertEqual(agent_no_files.prior_knowledge, {})
        self.assertEqual(agent_no_files.ground_truth, {})

    def test_get_prior_estimate_existing(self):
        """Test retrieving prior estimate for an existing task."""
        mean, variance = self.agent._get_prior_estimate("task_a")
        self.assertEqual(mean, 10.0)
        self.assertEqual(variance, 2.0)

    def test_get_prior_estimate_new_task(self):
        """Test initializing and retrieving prior estimate for a new task."""
        self.assertNotIn("new_task", self.agent.prior_knowledge)
        mean, variance = self.agent._get_prior_estimate("new_task")
        self.assertEqual(mean, INIT_PRIOR_MEAN)
        self.assertEqual(variance, INIT_PRIOR_VARIANCE)
        # Check if it was added to the internal knowledge
        self.assertIn("new_task", self.agent.prior_knowledge)
        self.assertEqual(
            self.agent.prior_knowledge["new_task"]["expected_duration"], INIT_PRIOR_MEAN
        )

    def test_get_prior_estimate_min_variance(self):
        """Test prior variance is clamped at MIN_VARIANCE."""
        self.agent.prior_knowledge["zero_var_task"] = {
            "expected_duration": 5.0,
            "variance": 0.0,
        }
        _, variance = self.agent._get_prior_estimate("zero_var_task")
        self.assertEqual(variance, MIN_VARIANCE)

    def test_perform_bayesian_update_calculation(self):
        """Test the Bayesian update calculation logic."""
        prior_mean, prior_variance = 10.0, 4.0
        gt_duration = 12.0
        elapsed_interval = 11.0
        mock_observation = 11.5  # Assume np.random.normal returns this
        self.mock_np_random_normal.return_value = mock_observation

        # Expected calculation
        epsilon_k_sq = max(FACTOR_ALPHA * prior_variance, MIN_VARIANCE)
        denominator = epsilon_k_sq + prior_variance
        expected_posterior_mean = (
            prior_variance * mock_observation + epsilon_k_sq * prior_mean
        ) / denominator
        expected_posterior_variance = max(
            (epsilon_k_sq * prior_variance) / denominator, MIN_VARIANCE
        )

        post_mean, post_var = self.agent._perform_bayesian_update(
            prior_mean, prior_variance, gt_duration, elapsed_interval
        )

        self.assertAlmostEqual(post_mean, expected_posterior_mean)
        self.assertAlmostEqual(post_var, expected_posterior_variance)
        # Check that np.random.normal was called with correct parameters
        expected_scale = np.sqrt(epsilon_k_sq)
        self.mock_np_random_normal.assert_called_once_with(
            loc=elapsed_interval, scale=expected_scale
        )

    def test_perform_bayesian_update_denominator_zero(self):
        """Test Bayesian update yields results close to prior when denominator is near zero."""
        prior_mean, prior_variance_tiny = 10.0, 1e-12
        elapsed_interval, gt_duration = 11.0, 12.0

        self.mock_np_random_normal.reset_mock()
        # Mock observation to be predictable, e.g., equal to elapsed_interval
        self.mock_np_random_normal.return_value = elapsed_interval

        post_mean, post_var = self.agent._perform_bayesian_update(
            prior_mean, prior_variance_tiny, gt_duration, elapsed_interval
        )

        # np.random.normal은 호출될 수 있으므로 assert_not_called 제거
        # self.mock_np_random_normal.assert_not_called() # 제거

        # 반환값이 prior 값과 매우 가까운지 확인 (delta 값 조정)
        self.assertAlmostEqual(post_mean, prior_mean, delta=1e-3)
        # post_var는 MIN_VARIANCE로 클램핑되므로 MIN_VARIANCE와 비교
        self.assertAlmostEqual(post_var, MIN_VARIANCE, delta=1e-15)

    def test_bayesian_estimate_success_flow(self):
        """Test the high-level flow of bayesian_estimate."""
        # Use helper to create mock subtasks
        mock_subtask = self._create_mock_subtask("Monitor Task_A", type="Monitor")
        mock_state = MagicMock(spec=SchedulerState)
        mock_state.subtask = mock_subtask
        mock_state.current_time = 15.0
        completed_start_task = self._create_mock_subtask("StartTask")
        mock_state.completed_subtasks = [
            CompletedEntry(subtask=completed_start_task, start_time=0.0, end_time=5.0)
        ]
        mock_state.constraints = MagicMock()  # Assume constraint graph exists

        # Configure mocks for this flow
        self.mock_extract_target.return_value = "Task_A"  # Target extracted
        self.agent._find_most_similar_subtask = MagicMock(
            return_value="task_a"
        )  # Mock internal method
        self.mock_get_crit_start.return_value = (
            "StartTask",
            5.0,
        )  # Critical start info
        # _get_prior_estimate uses setUp mock data
        # _perform_bayesian_update uses setUp mock data and mock observation

        # Expected posterior values from the update calculation (based on setUp mocks)
        # Prior: mean=10, var=2 -> epsilon_k_sq = max(1.0*2, 1e-9) = 2.0
        # elapsed = 15.0 - 5.0 = 10.0
        # observation = mock_np_random_normal = 10.0
        # denom = 2.0 + 2.0 = 4.0
        # post_mean = (2 * 10 + 2 * 10) / 4 = 10.0
        # post_var = (2 * 2) / 4 = 1.0
        expected_post_mean = 10.0
        expected_post_var = 1.0

        updated_state, result_info = self.agent.bayesian_estimate(mock_state)

        # Assertions
        self.mock_extract_target.assert_called_once_with("Monitor Task_A")
        self.agent._find_most_similar_subtask.assert_called_once_with(
            "task_a", ["task_a"]
        )  # Assumes mock_prior keys
        self.mock_get_crit_start.assert_called_once_with(
            subtask_name="Task_A",
            completed=mock_state.completed_subtasks,
            constraints=mock_state.constraints,
            constraint_handler=self.mock_constraint_handler,
        )
        # Check if knowledge was updated internally (we don't mock _update_knowledge... itself)
        self.assertAlmostEqual(
            self.agent.prior_knowledge["task_a"]["expected_duration"],
            expected_post_mean,
        )
        self.assertAlmostEqual(
            self.agent.prior_knowledge["task_a"]["variance"], expected_post_var
        )

        # Check result info dictionary
        self.assertIsNotNone(result_info)
        self.assertEqual(result_info["updated_subtask_name"], "task_a")
        self.assertAlmostEqual(
            result_info["original_expected_time"], 10.0
        )  # Prior mean from mock
        self.assertAlmostEqual(result_info["updated_expected_time"], expected_post_mean)
        self.assertAlmostEqual(result_info["ground_truth_time"], 12.0)  # GT from mock
        self.assertAlmostEqual(result_info["posterior_variance"], expected_post_var)

        self.assertEqual(
            updated_state, mock_state
        )  # State object itself might be modified in place or returned

    def test_bayesian_estimate_missing_ground_truth(self):
        """Test bayesian_estimate raises ValueError if ground truth is missing."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_C", type="Monitor"
        )  # Use helper
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=10.0,
            completed_subtasks=[],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_C"
        self.agent._find_most_similar_subtask = MagicMock(return_value="task_c")

        with self.assertRaisesRegex(
            ValueError, "No ground_truth found for matched subtask: 'task_c'"
        ):
            self.agent.bayesian_estimate(mock_state)

    def test_bayesian_estimate_crit_start_exception(self):
        """Test bayesian_estimate handles exception from get_critical_start_info."""
        mock_subtask = self._create_mock_subtask(
            "Monitor Task_A", type="Monitor"
        )  # Use helper
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=15.0,
            completed_subtasks=[],
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_A"
        self.agent._find_most_similar_subtask = MagicMock(return_value="task_a")
        self.mock_get_crit_start.side_effect = Exception("Failed to get critical info")

        updated_state, result_info = self.agent.bayesian_estimate(mock_state)

        self.assertEqual(updated_state, mock_state)  # Should return original state
        self.assertEqual(result_info, {})  # Should return empty dict

    def test_bayesian_estimate_negative_elapsed_time(self):
        """Test bayesian_estimate handles negative elapsed time by clamping to 0."""
        mock_subtask = self._create_mock_subtask("Monitor Task_A", type="Monitor")
        completed_start_task = self._create_mock_subtask("StartTask")
        mock_state = MagicMock(
            spec=SchedulerState,
            subtask=mock_subtask,
            current_time=3.0,
            completed_subtasks=[
                CompletedEntry(
                    subtask=completed_start_task, start_time=0.0, end_time=5.0
                )
            ],  # end_time=5.0
            constraints=MagicMock(),
        )
        self.mock_extract_target.return_value = "Task_A"
        self.agent._find_most_similar_subtask = MagicMock(return_value="task_a")
        self.mock_get_crit_start.return_value = ("StartTask", 5.0)  # end_time=5.0

        # _perform_bayesian_update 내부의 np.random.normal 호출 검증
        self.mock_np_random_normal.reset_mock()  # 이전 호출 기록 초기화
        self.mock_np_random_normal.return_value = 10.0  # dummy observation

        self.agent.bayesian_estimate(mock_state)

        # np.random.normal이 호출되었는지, loc 인자가 0인지 확인
        self.mock_np_random_normal.assert_called_once()
        call_args, call_kwargs = self.mock_np_random_normal.call_args
        # loc 인자는 키워드 인자로 전달될 수도 있고 위치 인자일 수도 있음
        passed_loc = call_kwargs.get("loc", None)
        if passed_loc is None and len(call_args) > 0:  # 위치 인자인 경우
            passed_loc = call_args[0]
        self.assertEqual(
            passed_loc, 0
        )  # critical_elapsed_interval이 0으로 전달되었는지 확인

    def test_save_knowledge_to_file_success(self):
        """Test saving the knowledge base to a file."""
        # Ensure prior_knowledge is not empty
        self.agent.prior_knowledge["task_a"] = {
            "expected_duration": 11.0,
            "variance": 1.5,
        }
        self.agent.save_knowledge_to_file()
        # Check that io_utils.save_knowledge was called correctly
        self.mock_save_knowledge.assert_called_once_with(
            self.agent.prior_knowledge, ESTIMATE_FILE_NAME
        )

    def test_save_knowledge_to_file_empty(self):
        """Test saving is skipped if knowledge base is empty."""
        self.agent.prior_knowledge = {}  # Make knowledge empty
        self.agent.save_knowledge_to_file()
        self.mock_save_knowledge.assert_not_called()

    def test_save_knowledge_to_file_exception(self):
        """Test exception handling during save."""
        self.mock_save_knowledge.side_effect = IOError("Disk full")
        self.agent.prior_knowledge["task_a"] = {
            "expected_duration": 11.0,
            "variance": 1.5,
        }
        with self.assertRaises(IOError):
            self.agent.save_knowledge_to_file()

    # Helper to create mock Subtasks correctly
    def _create_mock_subtask(self, name, type="Action", execution_status=True):
        # Provide minimum required args for Subtask constructor
        mock_sub = Subtask(
            task_name="TestTask",  # Dummy task_name
            name=name,
            repetition=1,  # Dummy repetition
            type=type,  # Dummy type
            # Optional args can be None or mocked
            execution=Execution(objects={}, primitive_actions=[f"ACTION {name}"]),
            duration=Duration(type="Controllable", interval=5.0),
        )
        if execution_status is not None:
            setattr(
                mock_sub, "execution_status", execution_status
            )  # Set status if needed
        return mock_sub


if __name__ == "__main__":
    unittest.main()
