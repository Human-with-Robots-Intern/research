"""Tests for monitoring backend policies and updaters."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

import networkx as nx
import numpy as np
import pytest
from scipy.stats import norm

from src.core.agent import Agent
from src.core.monitoring import (
    BayesianBeliefUpdater,
    BayesianMonitoringPolicy,
    BeliefStore,
    BeliefUpdateContext,
    GaussianSyntheticObservationModel,
    GroundTruthConfig,
    GroundTruthStore,
    MonitoringTriggerContext,
    ObservationResult,
    OpenAIVLMProgressObservationModel,
    ParticleFilterBeliefUpdater,
    ParticleFilterMonitoringPolicy,
    create_monitoring_backend,
    create_observation_model,
)
from src.core.scheduler import MonitoringObligation, Scheduler
from src.models.dataclass import (
    ActionSimulationLog,
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
    TaskExecutionStatus,
)
from src.models.task import Duration, Execution, Subtask
from src.scheduler.action_handler import ActionHandler
from src.scheduler.constraint_handler import ConstraintHandler
from src.scheduler.heuristic_manager import HeuristicManager
from src.utils.common import extract_monitoring_target_name
from src.utils.config import constants as runtime_constants
from src.utils.config.constants import (
    BAYESIAN_THRESHOLD_PROBABILITY,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    RISK_GRACE_SECONDS,
)
from src.utils.io_utils.result_saver import (
    calculate_timing_success_rate,
    serialize_completed_entries,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


class _DummyActionHandler:
    """Provide the minimal scheduler dependency surface for focused tests."""

    def get_actions_info(self, current_node: SimulationNode, actions: list[str]) -> Any:
        """Fail fast when an unexpected action simulation is attempted."""

        raise AssertionError(
            "_DummyActionHandler.get_actions_info should not be called in this test."
        )


class _DummyHeuristicManager:
    """Provide the minimal heuristic dependency surface for focused tests."""

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        all_candidates: list[Candidate],
    ) -> tuple[int, float]:
        """Return a neutral heuristic for dependency injection only."""

        return 0, 0.0


class _MonitoringOnlyActionHandler:
    """Simulate monitoring, wait, and staged wait actions for scheduler tests."""

    def __init__(self, *, nav_duration: float = 0.0) -> None:
        self.nav_duration = float(nav_duration)

    def get_actions_info(self, current_node: SimulationNode, actions: list[str]) -> Any:
        """Return deterministic action results for monitoring and staged waits."""

        if not actions:
            raise AssertionError("_MonitoringOnlyActionHandler requires at least one action.")

        cumulative_time = 0.0
        first_nav_duration = 0.0
        scene_positions = dict(current_node.state.scene_positions)
        held_object = current_node.state.held_object
        last_action = actions[-1]
        last_action_type = last_action.split()[0].upper()

        for index, action in enumerate(actions):
            parts = action.split()
            action_type = parts[0].upper()
            if action_type == "MONITORING":
                action_duration = MONITORING_DURATION
            elif action_type == "WAIT":
                action_duration = float(parts[1])
            elif action_type == "NAVIGATE_TO":
                action_duration = self.nav_duration
                if index == 0:
                    first_nav_duration = action_duration
                scene_positions["agent"] = (1.0, 0.9, 0.0)
            else:
                raise AssertionError(
                    "_MonitoringOnlyActionHandler only supports NAVIGATE_TO, WAIT, and MONITORING actions."
                )
            cumulative_time += action_duration

        return ActionResult(
            action_full_name=last_action,
            action_type=last_action_type,
            cumulative_time=cumulative_time,
            action_duration=(
                MONITORING_DURATION
                if last_action_type == "MONITORING"
                else float(last_action.split()[1])
                if last_action_type == "WAIT"
                else self.nav_duration
            ),
            scene_positions=scene_positions,
            held_object=held_object,
            success=True,
            first_nav_duration=first_nav_duration,
        )


class _FixedObservationModel:
    """Return a deterministic observation payload for updater tests."""

    def __init__(self, observation: float, variance: float) -> None:
        self._observation = observation
        self._variance = variance

    def observe(self, context: BeliefUpdateContext) -> ObservationResult:
        """Return a fixed observation irrespective of the input context."""

        _ = context
        return ObservationResult(
            observation=self._observation,
            variance=self._variance,
            metadata={"source": "fixed"},
        )


class _FakeResponsesApi:
    """Minimal fake OpenAI responses client for observation-model tests."""

    def __init__(self, output_text: str) -> None:
        self._output_text = output_text
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        """Capture request payloads and return a fake structured response."""

        self.last_kwargs = kwargs
        return type("FakeResponse", (), {"output_text": self._output_text})()


class _FakeOpenAIClient:
    """Expose the `.responses.create(...)` shape used in monitoring code."""

    def __init__(self, output_text: str) -> None:
        self.responses = _FakeResponsesApi(output_text)


def _make_subtask(
    name: str,
    *,
    primitive_actions: list[str],
    subtask_type: str = "Action",
    objects: Any = None,
    decomposed: bool = False,
) -> Subtask:
    """Build a compact subtask fixture for monitoring tests.

    Args:
        name: Subtask name.
        primitive_actions: Primitive action sequence.
        subtask_type: Logical subtask type.
        objects: Execution objects payload.
        decomposed: Whether the subtask is already decomposed.

    Returns:
        Subtask: Configured subtask fixture.
    """

    return Subtask(
        task_name="TestTask",
        name=name,
        repetition=1,
        subtask_type=subtask_type,
        execution=Execution(objects=objects or {}, primitive_actions=primitive_actions),
        duration=Duration(type="Controllable", interval=1, total_time=1.0),
        temporal_constraints=[],
        decomposed=decomposed,
    )


def _build_monitoring_update_state() -> tuple[SchedulerState, Subtask, Subtask, Subtask]:
    """Build a reusable monitoring-update state fixture.

    Returns:
        tuple[SchedulerState, Subtask, Subtask, Subtask]: State, critical start,
        monitoring subtask, and critical end subtask.
    """

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    monitor_subtask = _make_subtask(
        "Monitoring for Turn Off Microwave after Heating Potato_fixed",
        primitive_actions=["MONITORING Microwave|01"],
        subtask_type="Monitor",
        objects=["Microwave|01"],
        decomposed=True,
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )

    constraints = nx.DiGraph()
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 900.0},
    )
    constraints.add_edge(
        start_subtask.name,
        monitor_subtask.name,
        info={"Interval": 60.0, "IsCritical": True, "Variance": 900.0},
    )
    constraints.add_edge(
        monitor_subtask.name,
        end_subtask.name,
        info={"Interval": 40.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=monitor_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=0.0,
                schedule_end_time=28.01,
                sim_start_time=0.0,
                sim_end_time=28.01,
            ),
            CompletedEntry(
                subtask=monitor_subtask,
                schedule_start_time=85.80,
                schedule_end_time=91.70,
                sim_start_time=85.80,
                sim_end_time=91.70,
            ),
        ],
        remaining_subtasks=[end_subtask],
        constraints=constraints,
        current_time=91.70,
        scene_positions={},
        held_object=None,
    )
    return state, start_subtask, monitor_subtask, end_subtask


def _build_zero_wait_wait_monitoring_fixture(
    *,
    previous_same_target_monitor: bool = False,
    current_time: float = 90.0,
    target_start_time: float = 128.01,
    estimated_first_nav_duration: float = 0.0,
) -> tuple[Scheduler, SimulationNode, Candidate]:
    """Create a wait-with-monitoring case whose computed wait duration is zero."""

    action_handler = _MonitoringOnlyActionHandler(
        nav_duration=estimated_first_nav_duration
    )
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=_DummyHeuristicManager(),
    )

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
        subtask_type="Interaction",
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
        subtask_type="Interaction",
    )
    critical_interval_duration = target_start_time - 28.01

    if previous_same_target_monitor:
        current_subtask = _make_subtask(
            "Monitoring for Turn Off Microwave after Heating Potato_prev",
            primitive_actions=["MONITORING Microwave|01"],
            subtask_type="Monitor",
            objects=["Microwave|01"],
            decomposed=True,
        )
    else:
        current_subtask = _make_subtask(
            "Wash Fork and place on counterTop",
            primitive_actions=["CLEAN Fork|01"],
            subtask_type="Interaction",
        )

    constraints = nx.DiGraph()
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={
            "Interval": critical_interval_duration,
            "IsCritical": True,
            "Variance": 900.0,
        },
    )

    completed_entries = [
        CompletedEntry(
            subtask=start_subtask,
            schedule_start_time=0.0,
            schedule_end_time=28.01,
            sim_start_time=0.0,
            sim_end_time=28.01,
            execution_status=TaskExecutionStatus.SUCCESS,
        ),
        CompletedEntry(
            subtask=current_subtask,
            schedule_start_time=84.10,
            schedule_end_time=current_time,
            sim_start_time=84.10,
            sim_end_time=current_time,
            execution_status=TaskExecutionStatus.SUCCESS,
        ),
    ]

    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=completed_entries,
        remaining_subtasks=[end_subtask],
        constraints=constraints,
        current_time=current_time,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=end_subtask,
        is_critical=True,
        actual_interaction_start_time=target_start_time,
        logical_interaction_start_time=target_start_time,
        estimated_first_nav_duration=estimated_first_nav_duration,
    )
    return scheduler, node, candidate


def _monitor_target_name(subtask: Subtask) -> str:
    """Return the encoded monitoring target name for regression-style assertions."""

    try:
        return extract_monitoring_target_name(subtask.name)
    except ValueError:
        return subtask.name


def _assert_no_zero_duration_waits(completed_entries: list[CompletedEntry]) -> None:
    """Guard against synthetic WAIT 0 artifacts in scheduled plans."""

    for entry in completed_entries:
        if entry.subtask.subtask_type != "WAIT":
            continue
        duration = entry.schedule_end_time - entry.schedule_start_time
        assert not math.isclose(duration, 0.0, abs_tol=1e-9)


def _assert_no_immediate_same_target_remonitoring(
    completed_entries: list[CompletedEntry],
) -> None:
    """Guard against immediate same-target monitor duplication."""

    for previous_entry, current_entry in zip(completed_entries, completed_entries[1:]):
        if previous_entry.subtask.subtask_type != "Monitor":
            continue
        if current_entry.subtask.subtask_type != "Monitor":
            continue
        assert _monitor_target_name(previous_entry.subtask) != _monitor_target_name(
            current_entry.subtask
        )


def test_bayesian_monitoring_policy_matches_gaussian_quantile() -> None:
    """Bayesian trigger policy should match the closed-form Gaussian quantile."""

    belief_store = BeliefStore({"Mug": {"expected_duration": 20.0, "variance": 9.0}})
    policy = BayesianMonitoringPolicy(
        belief_store,
        threshold_probability=0.1,
    )

    trigger_time = policy.compute_trigger_time(
        MonitoringTriggerContext(
            object_name="Mug",
            critical_start_end_time=100.0,
            mean_duration=20.0,
            variance=9.0,
        )
    )

    expected_trigger_time = 100.0 + 20.0 + (math.sqrt(9.0) * norm.ppf(0.1))
    assert trigger_time == expected_trigger_time


def test_particle_filter_monitoring_policy_uses_weighted_quantile() -> None:
    """Particle-filter trigger policy should use the empirical particle quantile."""

    belief_store = BeliefStore(
        {
            "Mug": {
                "expected_duration": 20.0,
                "variance": 25.0,
                "method": "particle_filter",
                "particles": [10.0, 20.0, 30.0],
                "weights": [0.2, 0.3, 0.5],
            }
        }
    )
    policy = ParticleFilterMonitoringPolicy(
        belief_store,
        threshold_probability=0.5,
    )

    trigger_time = policy.compute_trigger_time(
        MonitoringTriggerContext(
            object_name="Mug",
            critical_start_end_time=100.0,
            mean_duration=20.0,
            variance=25.0,
        )
    )

    assert trigger_time == 120.0


def test_bayesian_belief_updater_persists_summary() -> None:
    """Bayesian updater should write a posterior summary back to the store."""

    belief_store = BeliefStore(
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        rng=np.random.default_rng(0),
    )
    updater = BayesianBeliefUpdater(
        belief_store,
        rng=np.random.default_rng(0),
    )

    result = updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    summary = belief_store.get_summary("Mug")
    assert result.method == "bayesian"
    assert summary.method == "bayesian"
    assert summary.expected_duration == result.posterior_mean
    assert summary.variance == result.posterior_variance
    assert "observation" in result.diagnostics


def test_gaussian_synthetic_observation_model_returns_variance_metadata() -> None:
    """Synthetic observation model should emit an observation and diagnostics."""

    observation_model = GaussianSyntheticObservationModel(
        rng=np.random.default_rng(0)
    )

    result = observation_model.observe(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    assert result.variance > 0.0
    assert "observation_mean" in result.metadata
    assert "elapsed_interval" in result.metadata


def test_create_observation_model_builds_synthetic_backend() -> None:
    """Observation factory should build the synthetic backend by name."""

    observation_model = create_observation_model("synthetic_gaussian")

    assert isinstance(observation_model, GaussianSyntheticObservationModel)


def test_openai_vlm_observation_model_converts_progress_to_duration() -> None:
    """OpenAI VLM observation model should turn progress into a duration estimate."""

    fake_client = _FakeOpenAIClient(
        json.dumps(
            {
                "progress": 0.5,
                "confidence": 0.8,
                "rationale": "The object appears about halfway done.",
            }
        )
    )
    observation_model = OpenAIVLMProgressObservationModel(
        image_provider=lambda: b"fake-image-bytes",
        client=fake_client,
        sigma_floor_sq=100.0,
        alpha=0.08,
    )

    result = observation_model.observe(
        BeliefUpdateContext(
            object_name="Microwave",
            gt_interval=100.0,
            prior_mean=100.0,
            prior_variance=900.0,
            elapsed_interval=40.0,
        )
    )

    assert result.observation == 80.0
    assert result.variance > 100.0
    assert result.metadata["observation_model"] == "openai_vlm"
    assert result.metadata["progress"] == 0.5
    assert result.metadata["confidence"] == 0.8
    assert fake_client.responses.last_kwargs is not None
    assert fake_client.responses.last_kwargs["model"] == "gpt-4.1-mini"


def test_create_observation_model_requires_image_provider_for_openai_vlm() -> None:
    """OpenAI VLM observation backend should require an image source."""

    with pytest.raises(ValueError):
        create_observation_model("openai_vlm")


def test_ground_truth_store_samples_once_per_object() -> None:
    """GroundTruthStore should reuse a sampled value within the same run."""

    ground_truth_store = GroundTruthStore(
        {"Microwave": 100.0},
        config=GroundTruthConfig(distribution="lognormal", random_seed=7),
    )

    first_sample = ground_truth_store.get_interval("Microwave")
    second_sample = ground_truth_store.get_interval("Microwave")

    assert first_sample is not None
    assert second_sample is not None
    assert first_sample == second_sample
    assert ground_truth_store.as_dict()["Microwave"] == first_sample


def test_ground_truth_store_can_presample_requested_objects() -> None:
    """GroundTruthStore should materialize latent GTs for a whole run upfront."""

    ground_truth_store = GroundTruthStore(
        {
            "Microwave": 100.0,
            "CoffeeMachine": 100.0,
            "CounterTop": 100.0,
        },
        config=GroundTruthConfig(distribution="lognormal", random_seed=11),
    )

    sampled_intervals = ground_truth_store.ensure_intervals(
        {"Microwave": {}, "CoffeeMachine": {}}
    )

    assert set(sampled_intervals.keys()) == {"Microwave", "CoffeeMachine"}
    assert "CounterTop" not in sampled_intervals
    assert ground_truth_store.as_dict() == sampled_intervals
    assert sampled_intervals["Microwave"] != sampled_intervals["CoffeeMachine"]


def test_ground_truth_store_gaussian_matches_wide_gt_design() -> None:
    """Gaussian GT sampling should match the intended wide 100s-centered design."""

    object_names = {f"Obj{i}": 100.0 for i in range(4000)}
    ground_truth_store = GroundTruthStore(
        object_names,
        config=GroundTruthConfig(distribution="gaussian", random_seed=3),
    )

    samples = np.asarray(
        list(ground_truth_store.ensure_intervals().values()),
        dtype=float,
    )

    assert samples.mean() == pytest.approx(100.0, abs=2.0)
    assert samples.std(ddof=0) == pytest.approx(40.0, abs=3.0)


def test_ground_truth_store_lognormal_is_heavy_tailed() -> None:
    """Log-normal GT sampling should be much broader than the mild legacy sampler."""

    object_names = {f"Obj{i}": 100.0 for i in range(4000)}
    ground_truth_store = GroundTruthStore(
        object_names,
        config=GroundTruthConfig(distribution="lognormal", random_seed=5),
    )

    samples = np.asarray(
        list(ground_truth_store.ensure_intervals().values()),
        dtype=float,
    )

    assert samples.mean() == pytest.approx(100.0, abs=5.0)
    assert np.quantile(samples, 0.95) > 250.0
    assert np.quantile(samples, 0.50) < 80.0


def test_ground_truth_store_mixture_has_two_separated_modes() -> None:
    """Mixture GT sampling should place mass near both low and high modes."""

    object_names = {f"Obj{i}": 100.0 for i in range(4000)}
    ground_truth_store = GroundTruthStore(
        object_names,
        config=GroundTruthConfig(distribution="mixture", random_seed=7),
    )

    samples = np.asarray(
        list(ground_truth_store.ensure_intervals().values()),
        dtype=float,
    )

    low_cluster_ratio = float(np.mean((samples >= 5.0) & (samples <= 65.0)))
    high_cluster_ratio = float(np.mean((samples >= 135.0) & (samples <= 195.0)))

    assert samples.mean() == pytest.approx(100.0, abs=5.0)
    assert low_cluster_ratio > 0.35
    assert high_cluster_ratio > 0.35


def test_scheduler_compute_monitoring_trigger_time_uses_bayesian_policy() -> None:
    """Scheduler should delegate trigger timing to the Bayesian policy."""

    belief_store = BeliefStore(
        {"Microwave": {"expected_duration": 100.0, "variance": 900.0}}
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(belief_store),
    )

    trigger_time = scheduler._compute_monitoring_trigger_time(
        raw_object_name="Microwave|01",
        critical_start_sub_end_time=28.01,
        mean_duration=100.0,
        variance=900.0,
    )

    expected_trigger_time = (
        28.01 + 100.0 + (math.sqrt(900.0) * norm.ppf(BAYESIAN_THRESHOLD_PROBABILITY))
    )
    assert trigger_time == expected_trigger_time


def test_scheduler_executes_feasible_candidate_atomically_without_staging(
    monkeypatch: MonkeyPatch,
) -> None:
    """Feasible candidates should keep atomic nav+interaction execution."""

    action_handler = ActionHandler(nav_graph={})
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
    )
    subtask = _make_subtask(
        "Heat Mug",
        primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
    )
    state = SchedulerState(
        subtask=_make_subtask("Init", primitive_actions=["WAIT 0"], subtask_type="Init"),
        completed_entries=[],
        remaining_subtasks=[subtask],
        constraints=nx.DiGraph(),
        current_time=10.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=subtask,
        is_critical=False,
        actual_interaction_start_time=15.0,
        logical_interaction_start_time=15.0,
        estimated_first_nav_duration=2.0,
    )

    monkeypatch.setattr(
        action_handler,
        "get_actions_info",
        lambda _node, actions: ActionResult(
            action_full_name=" -> ".join(actions),
            action_type="TOGGLE_ON",
            cumulative_time=5.0,
            action_duration=3.0,
            scene_positions={"agent": (1.0, 0.9, 0.0)},
            held_object=None,
            success=True,
            first_nav_duration=2.0,
        ),
    )
    monkeypatch.setattr(
        scheduler.cost_calculator,
        "calc_heuristic",
        lambda *_args, **_kwargs: (0, 0.0),
    )

    result_node = scheduler._expand_subtask_wo_monitoring(node, candidate, [], [])

    assert result_node is not None
    assert result_node.state.subtask.name == "Heat Mug"
    assert result_node.state.current_time == 15.0
    assert result_node.state.remaining_subtasks == []


def test_scheduler_keeps_monitoring_path_before_staged_wait(
    monkeypatch: MonkeyPatch,
) -> None:
    """Monitoring-required candidates should keep the existing monitoring split path."""

    action_handler = ActionHandler(nav_graph={})
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
    )
    subtask = _make_subtask(
        "Heat Mug",
        primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=subtask,
            completed_entries=[],
            remaining_subtasks=[subtask],
            constraints=nx.DiGraph(),
            current_time=0.0,
            scene_positions={"agent": (0.0, 0.9, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )
    candidate = Candidate(
        subtask=subtask,
        is_critical=True,
        actual_interaction_start_time=10.0,
        logical_interaction_start_time=10.0,
        estimated_first_nav_duration=2.0,
    )
    sentinel = SimulationNode(
        heuristic_cost=1.0,
        depth=1,
        tie_breaker=1,
        parent_node=node,
        state=node.state,
        risk_level=0,
    )

    monkeypatch.setattr(
        scheduler,
        "_should_split_with_monitoring",
        lambda *_args, **_kwargs: (
            True,
            SchedulingDue(due_date=10.0, due_related_sub_name=subtask.name),
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_expand_subtask_with_monitoring",
        lambda *_args, **_kwargs: sentinel,
    )
    monkeypatch.setattr(
        scheduler,
        "_expand_subtask_wo_monitoring",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Non-monitoring expansion should not run.")
        ),
    )

    result = scheduler._expand_single_subtask(node, candidate, [], [])

    assert result is sentinel


def test_scheduler_expands_blocked_candidate_frontier_as_staged_wait_only(
    monkeypatch: MonkeyPatch,
) -> None:
    """Blocked frontier candidates should emit one staged WAIT branch."""

    action_handler = ActionHandler(nav_graph={})
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
    )
    subtask = _make_subtask(
        "Heat Mug",
        primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=_make_subtask("Init", primitive_actions=["WAIT 0"], subtask_type="Init"),
            completed_entries=[],
            remaining_subtasks=[subtask],
            constraints=nx.DiGraph(),
            current_time=10.0,
            scene_positions={"agent": (0.0, 0.9, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )
    blocked_candidate = Candidate(
        subtask=subtask,
        is_critical=False,
        actual_interaction_start_time=20.0,
        logical_interaction_start_time=20.0,
        estimated_first_nav_duration=2.0,
    )

    monkeypatch.setattr(
        scheduler,
        "_should_split_with_monitoring",
        lambda *_args, **_kwargs: (False, None),
    )
    monkeypatch.setattr(
        action_handler,
        "get_actions_info",
        lambda _node, actions: ActionResult(
            action_full_name=" -> ".join(actions),
            action_type=actions[-1].split()[0].upper(),
            cumulative_time=10.0,
            action_duration=8.0 if actions[-1].startswith("WAIT ") else 2.0,
            scene_positions={"agent": (1.0, 0.9, 0.0)},
            held_object=None,
            success=True,
            first_nav_duration=2.0,
        ),
    )
    monkeypatch.setattr(
        scheduler.cost_calculator,
        "calc_heuristic",
        lambda *_args, **_kwargs: (0, 0.0),
    )

    expansions = scheduler._expand_candidates(node, [], [blocked_candidate])

    assert len(expansions) == 1
    assert expansions[0].state.subtask.subtask_type == "WAIT"
    assert expansions[0].state.current_time == pytest.approx(20.0)
    assert expansions[0].state.subtask.execution.primitive_actions == [
        "NAVIGATE_TO Mug|1",
        "WAIT 8.0",
    ]


def test_expand_wait_wo_monitoring_fuses_navigation_and_idle_wait() -> None:
    """Blocked waits should surface navigation and idle in one WAIT node."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=30.0,
        target_start_time=40.0,
        estimated_first_nav_duration=2.0,
    )

    result_node = scheduler._expand_wait_wo_monitoring(
        curr_node,
        candidate,
        [],
        nav_duration=2.0,
    )

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    assert result_node.state.current_time == pytest.approx(40.0)
    assert result_node.state.completed_entries[-1].schedule_nav_time == pytest.approx(2.0)
    assert result_node.state.subtask.execution.primitive_actions == [
        "NAVIGATE_TO Microwave|01",
        "WAIT 8.0",
    ]


def test_action_handler_reuses_search_scoped_action_cache(
    monkeypatch: MonkeyPatch,
) -> None:
    """ActionHandler should avoid re-simulating identical action requests."""

    action_handler = ActionHandler(nav_graph={})
    current_subtask = _make_subtask(
        "Inspect Mug",
        primitive_actions=["NAVIGATE_TO Mug|01"],
    )
    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[],
        remaining_subtasks=[current_subtask],
        constraints=nx.DiGraph(),
        current_time=5.0,
        scene_positions={"agent": (0.0, 0.0, 0.0), "Mug|01": (1.0, 0.0, 0.0)},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    simulate_call_count = {"count": 0}

    def _fake_simulate_actions(
        initial_node: SimulationNode, primitive_actions: list[str]
    ) -> ActionSimulationLog:
        """Return a deterministic action log and track invocation count."""

        _ = initial_node
        simulate_call_count["count"] += 1
        action_log = ActionSimulationLog()
        action_log.add_result(
            action_full_name=primitive_actions[0],
            action_type="NAVIGATE_TO",
            cumulative_time=1.5,
            action_duration=1.5,
            scene_positions={"agent": (1.0, 0.0, 0.0), "Mug|01": (1.0, 0.0, 0.0)},
            held_object=None,
            success=True,
        )
        return action_log

    monkeypatch.setattr(action_handler, "_simulate_actions", _fake_simulate_actions)

    action_handler.begin_search_session({})
    first_result = action_handler.get_actions_info(curr_node, ["NAVIGATE_TO Mug|01"])
    second_result = action_handler.get_actions_info(curr_node, ["NAVIGATE_TO Mug|01"])
    cache_hits, cache_misses = action_handler.end_search_session()

    assert first_result is not None
    assert second_result is not None
    assert first_result is second_result
    assert simulate_call_count["count"] == 1
    assert cache_hits == 1
    assert cache_misses == 1


def test_action_handler_cache_reuses_same_state_across_time_changes(
    monkeypatch: MonkeyPatch,
) -> None:
    """ActionHandler cache should ignore absolute time when physical state is unchanged."""

    action_handler = ActionHandler(nav_graph={})
    current_subtask = _make_subtask(
        "Inspect Mug",
        primitive_actions=["NAVIGATE_TO Mug|01"],
    )
    base_scene_positions = {"agent": (0.0, 0.0, 0.0), "Mug|01": (1.0, 0.0, 0.0)}
    first_state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[],
        remaining_subtasks=[current_subtask],
        constraints=nx.DiGraph(),
        current_time=5.0,
        scene_positions=base_scene_positions,
        held_object=None,
    )
    second_state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[],
        remaining_subtasks=[current_subtask],
        constraints=nx.DiGraph(),
        current_time=25.0,
        scene_positions=base_scene_positions,
        held_object=None,
    )
    first_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=first_state,
        risk_level=0,
    )
    second_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=1,
        parent_node=None,
        state=second_state,
        risk_level=0,
    )
    simulate_call_count = {"count": 0}

    def _fake_simulate_actions(
        initial_node: SimulationNode, primitive_actions: list[str]
    ) -> ActionSimulationLog:
        """Return a deterministic action log and track invocation count."""

        _ = initial_node
        simulate_call_count["count"] += 1
        action_log = ActionSimulationLog()
        action_log.add_result(
            action_full_name=primitive_actions[0],
            action_type="NAVIGATE_TO",
            cumulative_time=1.5,
            action_duration=1.5,
            scene_positions={"agent": (1.0, 0.0, 0.0), "Mug|01": (1.0, 0.0, 0.0)},
            held_object=None,
            success=True,
        )
        return action_log

    monkeypatch.setattr(action_handler, "_simulate_actions", _fake_simulate_actions)

    action_handler.begin_search_session({})
    first_result = action_handler.get_actions_info(first_node, ["NAVIGATE_TO Mug|01"])
    second_result = action_handler.get_actions_info(second_node, ["NAVIGATE_TO Mug|01"])
    cache_hits, cache_misses = action_handler.end_search_session()

    assert first_result is not None
    assert second_result is not None
    assert first_result is second_result
    assert simulate_call_count["count"] == 1
    assert cache_hits == 1
    assert cache_misses == 1


def test_action_handler_missing_navigation_target_fails_cleanly() -> None:
    """ActionHandler should fail navigation when the target object is unknown."""

    action_handler = ActionHandler(nav_graph={(0.0, 0.0, 0.0): []})
    current_subtask = _make_subtask(
        "Inspect Missing Mug",
        primitive_actions=["NAVIGATE_TO Mug|404"],
    )
    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[],
        remaining_subtasks=[current_subtask],
        constraints=nx.DiGraph(),
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.0, 0.0)},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )

    result = action_handler.get_actions_info(curr_node, ["NAVIGATE_TO Mug|404"])

    assert result is not None
    assert result.success is False
    assert result.action_duration == 0.0
    assert result.scene_positions["agent"] == (0.0, 0.0, 0.0)


def test_action_handler_partial_navigation_advances_by_one_step() -> None:
    """Partial navigation should move to the first traversed waypoint."""

    start_pos = (0.0, 0.0, 0.0)
    mid_pos = (1.0, 0.0, 0.0)
    end_pos = (2.0, 0.0, 0.0)
    nav_graph = {
        start_pos: [mid_pos],
        mid_pos: [end_pos],
        end_pos: [],
    }
    action_handler = ActionHandler(nav_graph=nav_graph)
    current_subtask = _make_subtask(
        "Partially Move To Mug",
        primitive_actions=[f"NAVIGATE_TO Mug|01 {NAV_STEP_DURATION}"],
    )
    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[],
        remaining_subtasks=[current_subtask],
        constraints=nx.DiGraph(),
        current_time=0.0,
        scene_positions={"agent": start_pos, "Mug|01": end_pos},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )

    result = action_handler.get_actions_info(
        curr_node,
        [f"NAVIGATE_TO Mug|01 {NAV_STEP_DURATION}"],
    )

    assert result is not None
    assert result.success is True
    assert result.scene_positions["agent"] == mid_pos


def test_action_handler_shortest_path_prefers_fewer_steps() -> None:
    """Shortest-path search should minimize step count instead of turn count."""

    start_pos = (0.0, 0.0, 0.0)
    shortcut_pos = (100.0, 0.0, 0.0)
    end_pos = (100.0, 0.0, 1.0)
    nav_graph: dict[tuple[float, float, float], list[tuple[float, float, float]]] = {
        start_pos: [(1.0, 0.0, 0.0), shortcut_pos],
        shortcut_pos: [end_pos],
        end_pos: [],
    }
    for x_coord in range(1, 100):
        current_pos = (float(x_coord), 0.0, 0.0)
        next_pos = (float(x_coord + 1), 0.0, 0.0)
        nav_graph.setdefault(current_pos, []).append(next_pos)
    action_handler = ActionHandler(nav_graph=nav_graph)

    shortest_path = action_handler._find_shortest_path(start_pos, end_pos)

    assert shortest_path == [start_pos, shortcut_pos, end_pos]


def test_heuristic_navigation_time_matches_action_handler_step_model() -> None:
    """Heuristic navigation estimate should count traversed steps only."""

    start_pos = (0.0, 0.0, 0.0)
    mid_pos = (1.0, 0.0, 0.0)
    end_pos = (2.0, 0.0, 0.0)
    nav_graph = {
        start_pos: [mid_pos],
        mid_pos: [end_pos],
        end_pos: [],
    }
    heuristic_manager = HeuristicManager(ActionHandler(nav_graph=nav_graph))

    estimated_nav_time = heuristic_manager._estimate_navigation_time_between_positions(
        start_pos,
        end_pos,
    )

    assert estimated_nav_time == 2 * NAV_STEP_DURATION


def test_heuristic_uses_monitor_subtask_duration_consistently() -> None:
    """Heuristic should treat Monitor subtasks via their configured duration."""

    heuristic_manager = HeuristicManager(ActionHandler(nav_graph={}))
    monitor_subtask = _make_subtask(
        "Monitoring Microwave",
        primitive_actions=["MONITORING Microwave|01"],
        subtask_type="Monitor",
    )
    wait_subtask = _make_subtask(
        "Wait Briefly",
        primitive_actions=["WAIT 3.0"],
        subtask_type="WAIT",
    )
    monitor_subtask.duration.interval = 5.0
    wait_subtask.duration.interval = 3.0

    monitor_duration = heuristic_manager._get_estimated_pure_interaction_time(
        monitor_subtask
    )
    wait_duration = heuristic_manager._get_estimated_pure_interaction_time(wait_subtask)

    assert monitor_duration == 5.0
    assert wait_duration == 0.0

def test_constraint_handler_handles_missing_navigation_estimate(
    monkeypatch: MonkeyPatch,
) -> None:
    """ConstraintHandler should not crash when navigation simulation returns None."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    subtask = _make_subtask(
        "Inspect Mug",
        primitive_actions=["NAVIGATE_TO Mug|01", "GRASP Mug|01"],
    )
    state = SchedulerState(
        subtask=subtask,
        completed_entries=[],
        remaining_subtasks=[subtask],
        constraints=nx.DiGraph(),
        current_time=0.0,
        scene_positions={"agent": (0.0, 0.0, 0.0), "Mug|01": (1.0, 0.0, 0.0)},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )

    monkeypatch.setattr(action_handler, "get_actions_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        constraint_handler,
        "get_logical_interaction_start_time",
        lambda *_args, **_kwargs: (0.0, False, "READY", {}),
    )
    monkeypatch.setattr(
        constraint_handler,
        "_assign_scheduling_due",
        lambda *_args, **_kwargs: None,
    )

    feasible_candidates, not_yet_candidates = constraint_handler.get_feasible_candidates(
        curr_node
    )

    assert not not_yet_candidates
    assert len(feasible_candidates) == 1
    assert feasible_candidates[0].estimated_first_nav_duration == 0.0


def test_assign_scheduling_due_preserves_self_deadline_for_feasible_critical_candidate() -> None:
    """Feasible critical candidates should keep their own due for heuristic self-target checks."""

    constraint_handler = ConstraintHandler(_DummyActionHandler())
    critical_now = Candidate(
        subtask=_make_subtask(
            "Turn Off Microwave",
            primitive_actions=["TOGGLE_OFF Microwave|01"],
        ),
        is_critical=True,
        logical_interaction_start_time=12.0,
    )
    filler_task = Candidate(
        subtask=_make_subtask(
            "Prepare Plate",
            primitive_actions=["PUT Plate|01 Table|01"],
        ),
        is_critical=False,
        logical_interaction_start_time=6.0,
    )
    next_critical = Candidate(
        subtask=_make_subtask(
            "Take Out Potato",
            primitive_actions=["PICKUP Potato|01"],
        ),
        is_critical=True,
        logical_interaction_start_time=8.0,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=critical_now.subtask,
            completed_entries=[],
            remaining_subtasks=[
                critical_now.subtask,
                filler_task.subtask,
                next_critical.subtask,
            ],
            constraints=nx.DiGraph(),
            current_time=5.0,
            scene_positions={"agent": (0.0, 0.0, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )

    constraint_handler._assign_scheduling_due(
        [critical_now, filler_task],
        [next_critical],
        curr_node,
    )

    assert critical_now.scheduling_due == SchedulingDue(
        due_date=12.0,
        due_related_sub_name="Turn Off Microwave",
    )
    assert filler_task.scheduling_due == SchedulingDue(
        due_date=8.0,
        due_related_sub_name="Take Out Potato",
    )


def test_urgent_horizon_marks_within_grace_candidate_urgent() -> None:
    """Critical tasks inside the monitoring horizon and dispatch grace should become urgent."""

    assert RISK_GRACE_SECONDS >= 1.0
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
    )
    candidate = Candidate(
        subtask=_make_subtask(
            "Turn Off Microwave",
            primitive_actions=["TOGGLE_OFF Microwave|01"],
        ),
        is_critical=True,
        logical_interaction_start_time=6.0,
        estimated_first_nav_duration=5.0,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=_make_subtask("Init", primitive_actions=["WAIT 0"], subtask_type="Init"),
            completed_entries=[],
            remaining_subtasks=[candidate.subtask],
            constraints=nx.DiGraph(),
            current_time=0.0,
            scene_positions={"agent": (0.0, 0.0, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )

    urgent_candidates = scheduler._get_urgent_critical_candidates(
        curr_node, [candidate], []
    )

    assert candidate in urgent_candidates
    assert candidate.actual_interaction_start_time == 5.0


def test_urgent_horizon_leaves_outside_grace_candidate_blocked() -> None:
    """Critical tasks inside the horizon but outside grace should wait for blocked expansion."""

    slack_outside_grace = RISK_GRACE_SECONDS + 0.5
    assert slack_outside_grace < MONITORING_DURATION
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
    )
    candidate = Candidate(
        subtask=_make_subtask(
            "Turn Off Microwave",
            primitive_actions=["TOGGLE_OFF Microwave|01"],
        ),
        is_critical=True,
        logical_interaction_start_time=5.0 + slack_outside_grace,
        estimated_first_nav_duration=5.0,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=_make_subtask("Init", primitive_actions=["WAIT 0"], subtask_type="Init"),
            completed_entries=[],
            remaining_subtasks=[candidate.subtask],
            constraints=nx.DiGraph(),
            current_time=0.0,
            scene_positions={"agent": (0.0, 0.0, 0.0)},
            held_object=None,
        ),
        risk_level=0,
    )

    urgent_candidates = scheduler._get_urgent_critical_candidates(
        curr_node, [candidate], []
    )

    assert urgent_candidates == []
    assert candidate.actual_interaction_start_time is None


def test_heuristic_remaining_work_keeps_uncommitted_zero_interval_successor(
    monkeypatch: MonkeyPatch,
) -> None:
    """Remaining-work scoring should keep uncommitted successors in the residual set."""

    action_handler = ActionHandler(nav_graph={})
    heuristic_manager = HeuristicManager(action_handler)
    candidate_subtask = _make_subtask(
        "Start Microwave",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    zero_interval_successor = _make_subtask(
        "Stop Microwave",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    unrelated_subtask = _make_subtask(
        "Prepare Coffee",
        primitive_actions=["TOGGLE_ON CoffeeMachine|01"],
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        candidate_subtask.name,
        zero_interval_successor.name,
        info={"Interval": 0.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=candidate_subtask,
        completed_entries=[],
        remaining_subtasks=[
            candidate_subtask,
            zero_interval_successor,
            unrelated_subtask,
        ],
        constraints=constraints,
        current_time=0.0,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "Microwave|01": (1.0, 0.0, 0.0),
            "CoffeeMachine|01": (2.0, 0.0, 0.0),
        },
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=candidate_subtask,
        is_critical=True,
    )
    captured_tasks: dict[str, list[str]] = {}

    monkeypatch.setattr(
        action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: None,
    )

    def _fake_mst(
        current_agent_pos: Any,
        remaining_tasks: Any,
        scene_positions: Any,
    ) -> float:
        """Capture the task set passed to MST and return a neutral cost."""

        _ = current_agent_pos, scene_positions
        captured_tasks["names"] = [task.name for task in remaining_tasks]
        return 0.0

    monkeypatch.setattr(
        heuristic_manager,
        "_calculate_mst_navigation_time",
        _fake_mst,
    )

    heuristic_manager._calculate_remaining_work_cost(curr_node, candidate)

    assert captured_tasks["names"] == [
        zero_interval_successor.name,
        unrelated_subtask.name,
    ]


def test_heuristic_remaining_work_preserves_debt_until_timer_start_executes(
    monkeypatch: MonkeyPatch,
) -> None:
    """Scoring should not erase a future timer debt before its start task is committed."""

    action_handler = ActionHandler(nav_graph={})
    heuristic_manager = HeuristicManager(action_handler)
    prep_subtask = _make_subtask(
        "Place Bread in Microwave",
        primitive_actions=["OPEN Microwave|01", "PLACE_INSIDE Bread|01 Microwave|01"],
    )
    start_subtask = _make_subtask(
        "Start Microwave for Heating Bread",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Bread",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        prep_subtask.name,
        start_subtask.name,
        info={"Interval": 0.0, "IsCritical": True},
    )
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=prep_subtask,
        completed_entries=[],
        remaining_subtasks=[prep_subtask, start_subtask, end_subtask],
        constraints=constraints,
        current_time=0.0,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "Microwave|01": (1.0, 0.0, 0.0),
        },
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(subtask=prep_subtask, is_critical=False)

    monkeypatch.setattr(
        action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_calculate_mst_navigation_time",
        lambda *_args, **_kwargs: 0.0,
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_estimated_pure_interaction_time",
        lambda *_args, **_kwargs: 0.0,
    )

    remaining_work_cost = heuristic_manager._calculate_remaining_work_cost(
        curr_node, candidate
    )

    assert remaining_work_cost == pytest.approx(100.0)


def test_constraint_handler_marks_failed_predecessor_as_unavailable() -> None:
    """ConstraintHandler should stop successors after an explicit predecessor failure."""

    failed_subtask = _make_subtask(
        "Start Microwave",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    dependent_subtask = _make_subtask(
        "Stop Microwave",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        failed_subtask.name,
        dependent_subtask.name,
        info={"Interval": 10.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=dependent_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=failed_subtask,
                schedule_start_time=0.0,
                schedule_end_time=5.0,
                execution_status=TaskExecutionStatus.FAILURE,
            )
        ],
        remaining_subtasks=[dependent_subtask],
        constraints=constraints,
        current_time=5.0,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    constraint_handler = ConstraintHandler(_DummyActionHandler())

    logical_start_time, is_critical, status, critical_info = (
        constraint_handler.get_logical_interaction_start_time(
            curr_node, dependent_subtask
        )
    )

    assert logical_start_time is None
    assert is_critical is False
    assert status == "FAILED_PREDECESSOR"
    assert critical_info == {}


def test_scheduler_detects_active_bayesian_monitoring_interval(
    monkeypatch: MonkeyPatch,
) -> None:
    """Scheduler should request monitoring when an active critical interval exists."""

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    current_subtask = _make_subtask(
        "Prepare Coffee Machine with Mug",
        primitive_actions=["NAVIGATE_TO Mug|01", "GRASP Mug|01"],
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    graph = nx.DiGraph()
    graph.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=0.0,
                schedule_end_time=28.01,
            )
        ],
        remaining_subtasks=[current_subtask, end_subtask],
        constraints=graph,
        current_time=63.39,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )
    candidate = Candidate(
        subtask=_make_subtask(
            "Wash Fork",
            primitive_actions=["NAVIGATE_TO Fork|01", "GRASP Fork|01"],
        ),
        is_critical=False,
    )

    monkeypatch.setattr(
        scheduler.action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: ActionResult(
            action_full_name="GRASP Fork|01",
            action_type="GRASP",
            cumulative_time=40.0,
            action_duration=40.0,
            scene_positions={},
            success=True,
        ),
    )

    need_monitor, due_info = scheduler._should_split_with_monitoring(
        curr_node, candidate
    )

    assert need_monitor is True
    assert due_info is not None
    assert due_info.due_related_sub_name == end_subtask.name
    assert due_info.due_date == 128.01


def test_scheduler_reuses_monitoring_caches_within_search_session(
    monkeypatch: MonkeyPatch,
) -> None:
    """Scheduler should memoize active intervals and trigger times per search."""

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    current_subtask = _make_subtask(
        "Prepare Coffee Machine with Mug",
        primitive_actions=["NAVIGATE_TO Mug|01", "GRASP Mug|01"],
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    graph = nx.DiGraph()
    graph.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=0.0,
                schedule_end_time=28.01,
            )
        ],
        remaining_subtasks=[current_subtask, end_subtask],
        constraints=graph,
        current_time=63.39,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )
    candidate = Candidate(
        subtask=_make_subtask(
            "Wash Fork",
            primitive_actions=["NAVIGATE_TO Fork|01", "GRASP Fork|01"],
        ),
        is_critical=False,
    )

    monkeypatch.setattr(
        scheduler.action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: ActionResult(
            action_full_name="GRASP Fork|01",
            action_type="GRASP",
            cumulative_time=40.0,
            action_duration=40.0,
            scene_positions={},
            success=True,
        ),
    )

    scheduler._begin_search_session()
    try:
        first_need_monitor, first_due = scheduler._should_split_with_monitoring(
            curr_node, candidate
        )
        second_need_monitor, second_due = scheduler._should_split_with_monitoring(
            curr_node, candidate
        )
        first_trigger = scheduler._compute_monitoring_trigger_time(
            raw_object_name="Microwave|01",
            critical_start_sub_end_time=28.01,
            mean_duration=100.0,
            variance=900.0,
        )
        second_trigger = scheduler._compute_monitoring_trigger_time(
            raw_object_name="Microwave|01",
            critical_start_sub_end_time=28.01,
            mean_duration=100.0,
            variance=900.0,
        )

        assert first_need_monitor is True
        assert second_need_monitor is True
        assert first_due == second_due
        assert first_trigger == second_trigger
        assert scheduler._search_cache is not None
        assert scheduler._search_cache.active_interval_cache_misses == 1
        assert scheduler._search_cache.active_interval_cache_hits == 1
        assert scheduler._search_cache.trigger_cache_misses == 1
        assert scheduler._search_cache.trigger_cache_hits == 3
    finally:
        scheduler._end_search_session()


def test_monitoring_target_selection_is_not_hijacked_by_candidate_due(
    monkeypatch: MonkeyPatch,
) -> None:
    """Monitoring target selection should stay on the active Bayesian winner."""

    early_start = _make_subtask(
        "Start Faucet",
        primitive_actions=["TOGGLE_ON Faucet|01"],
    )
    early_end = _make_subtask(
        "Turn Off Faucet",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
    )
    late_start = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    late_end = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    filler_subtask = _make_subtask(
        "Wash Fork",
        primitive_actions=["NAVIGATE_TO Fork|01", "GRASP Fork|01"],
    )

    graph = nx.DiGraph()
    graph.add_edge(
        early_start.name,
        early_end.name,
        info={"Interval": 20.0, "IsCritical": True, "Variance": 100.0},
    )
    graph.add_edge(
        late_start.name,
        late_end.name,
        info={"Interval": 40.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=filler_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=early_start,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            ),
            CompletedEntry(
                subtask=late_start,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            ),
        ],
        remaining_subtasks=[filler_subtask, early_end, late_end],
        constraints=graph,
        current_time=12.0,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )
    candidate = Candidate(
        subtask=filler_subtask,
        is_critical=False,
        scheduling_due=SchedulingDue(
            due_date=30.0,
            due_related_sub_name=early_end.name,
        ),
    )

    monkeypatch.setattr(
        scheduler.action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: ActionResult(
            action_full_name="GRASP Fork|01",
            action_type="GRASP",
            cumulative_time=15.0,
            action_duration=15.0,
            scene_positions={},
            success=True,
        ),
    )

    need_monitor, due_info = scheduler._should_split_with_monitoring(
        curr_node, candidate
    )

    assert need_monitor is True
    assert due_info is not None
    assert due_info.due_related_sub_name == late_end.name
    assert due_info.due_date == 50.0


def test_monitoring_target_selection_ignores_future_trigger_outside_candidate_window(
    monkeypatch: MonkeyPatch,
) -> None:
    """Future active intervals should not force monitoring before their trigger reaches this candidate."""

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    filler_subtask = _make_subtask(
        "Wash Fork",
        primitive_actions=["NAVIGATE_TO Fork|01", "GRASP Fork|01"],
    )
    graph = nx.DiGraph()
    graph.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=filler_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            )
        ],
        remaining_subtasks=[filler_subtask, end_subtask],
        constraints=graph,
        current_time=12.0,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )
    candidate = Candidate(subtask=filler_subtask, is_critical=False)

    monkeypatch.setattr(
        scheduler.action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: ActionResult(
            action_full_name="GRASP Fork|01",
            action_type="GRASP",
            cumulative_time=5.0,
            action_duration=5.0,
            scene_positions={},
            success=True,
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: 30.0,
    )

    need_monitor, due_info = scheduler._should_split_with_monitoring(
        curr_node, candidate
    )

    assert need_monitor is False
    assert due_info is None


def test_monitoring_target_selection_uses_earliest_overlapping_trigger_only(
    monkeypatch: MonkeyPatch,
) -> None:
    """Only triggers that land in the current candidate window should compete."""

    early_start = _make_subtask(
        "Start Faucet",
        primitive_actions=["TOGGLE_ON Faucet|01"],
    )
    early_end = _make_subtask(
        "Turn Off Faucet",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
    )
    late_start = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    late_end = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    filler_subtask = _make_subtask(
        "Wash Fork",
        primitive_actions=["NAVIGATE_TO Fork|01", "GRASP Fork|01"],
    )

    graph = nx.DiGraph()
    graph.add_edge(
        early_start.name,
        early_end.name,
        info={"Interval": 20.0, "IsCritical": True, "Variance": 100.0},
    )
    graph.add_edge(
        late_start.name,
        late_end.name,
        info={"Interval": 40.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=filler_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=early_start,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            ),
            CompletedEntry(
                subtask=late_start,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            ),
        ],
        remaining_subtasks=[filler_subtask, early_end, late_end],
        constraints=graph,
        current_time=12.0,
        scene_positions={},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )
    candidate = Candidate(subtask=filler_subtask, is_critical=False)

    monkeypatch.setattr(
        scheduler.action_handler,
        "get_actions_info",
        lambda *_args, **_kwargs: ActionResult(
            action_full_name="GRASP Fork|01",
            action_type="GRASP",
            cumulative_time=10.0,
            action_duration=10.0,
            scene_positions={},
            success=True,
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **kwargs: (
            18.0
            if kwargs["raw_object_name"] == "Faucet|01"
            else 30.0
        ),
    )

    need_monitor, due_info = scheduler._should_split_with_monitoring(
        curr_node, candidate
    )

    assert need_monitor is True
    assert due_info is not None
    assert due_info.due_related_sub_name == early_end.name
    assert due_info.due_date == 30.0


def test_scheduler_compute_monitoring_trigger_time_uses_particle_filter_policy() -> None:
    """Scheduler should delegate trigger timing to the particle-filter policy."""

    belief_store = BeliefStore(
        {
            "Microwave": {
                "expected_duration": 100.0,
                "variance": 900.0,
                "method": "particle_filter",
                "particles": [80.0, 100.0, 120.0],
                "weights": [0.2, 0.3, 0.5],
            }
        }
    )
    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=ParticleFilterMonitoringPolicy(
            belief_store,
            threshold_probability=0.5,
        ),
    )

    trigger_time = scheduler._compute_monitoring_trigger_time(
        raw_object_name="Microwave|01",
        critical_start_sub_end_time=28.01,
        mean_duration=100.0,
        variance=900.0,
    )

    assert trigger_time == 128.01


def test_expand_subtask_with_monitoring_skips_late_pre_monitor_fallback(
    monkeypatch: MonkeyPatch,
) -> None:
    """Split-failure fallback should skip monitoring once it already misses the critical deadline."""

    action_handler = _DummyActionHandler()
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=_DummyHeuristicManager(),
        monitoring_policy=BayesianMonitoringPolicy(BeliefStore()),
    )

    start_subtask = _make_subtask(
        "Cook Egg in Pan",
        primitive_actions=["COOK Egg|01"],
        subtask_type="Interaction",
    )
    current_subtask = _make_subtask(
        "Wash Plate and place on counterTop",
        primitive_actions=["CLEAN Plate|01"],
        subtask_type="Interaction",
    )
    end_subtask = _make_subtask(
        "Turn Off Stove After Cooking Egg",
        primitive_actions=["TOGGLE_OFF Stove|01"],
        subtask_type="Interaction",
    )

    constraints = nx.DiGraph()
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 20.0, "IsCritical": True, "Variance": 900.0},
    )

    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=0.0,
                schedule_end_time=10.0,
            ),
            CompletedEntry(
                subtask=current_subtask,
                schedule_start_time=20.0,
                schedule_end_time=31.0,
            ),
        ],
        remaining_subtasks=[end_subtask],
        constraints=constraints,
        current_time=31.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=end_subtask,
        is_critical=True,
        scheduling_due=SchedulingDue(
            due_date=30.0,
            due_related_sub_name=end_subtask.name,
        ),
        logical_interaction_start_time=30.0,
        actual_interaction_start_time=31.0,
        estimated_first_nav_duration=0.0,
    )

    def _get_actions_info(current_node: SimulationNode, actions: list[str]) -> ActionResult:
        _ = current_node
        action_name = actions[-1]
        return ActionResult(
            action_full_name=action_name,
            action_type=action_name.split()[0].upper(),
            cumulative_time=2.0,
            action_duration=2.0,
            scene_positions=dict(state.scene_positions),
            held_object=state.held_object,
            success=True,
            first_nav_duration=0.0,
        )

    monkeypatch.setattr(action_handler, "get_actions_info", _get_actions_info)
    monkeypatch.setattr(
        action_handler,
        "split_subtask_by_cutoff_time",
        lambda *_args, **_kwargs: (None, None, False, False),
        raising=False,
    )
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: 29.0,
    )

    result_node = scheduler._expand_subtask_with_monitoring(curr_node, candidate, [])

    assert result_node is not None
    assert result_node.state.subtask.name == end_subtask.name
    assert result_node.state.subtask.subtask_type == "Interaction"
    assert result_node.state.current_time == pytest.approx(33.0)
    new_entries = result_node.state.completed_entries[len(state.completed_entries) :]
    assert len(new_entries) == 1
    assert new_entries[0].subtask.name == end_subtask.name
    assert new_entries[0].subtask.subtask_type == "Interaction"


def test_particle_filter_belief_updater_returns_particle_state() -> None:
    """Particle-filter updater should keep particle state and expose ESS."""

    belief_store = BeliefStore(
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        rng=np.random.default_rng(0),
    )
    belief_store.ensure_method("Mug", "particle_filter")
    updater = ParticleFilterBeliefUpdater(
        belief_store,
        rng=np.random.default_rng(0),
    )

    result = updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    stored_state = belief_store.get_state("Mug")
    assert result.method == "particle_filter"
    assert stored_state["method"] == "particle_filter"
    assert len(stored_state["particles"]) == len(stored_state["weights"])
    assert stored_state["ess"] > 0.0
    assert "ess_before_resample" in result.diagnostics
    assert "ess_ratio_after_resample" in result.diagnostics
    assert "particle_quantile_p10" in result.diagnostics
    assert "particle_quantile_p50" in result.diagnostics
    assert "particle_quantile_p90" in result.diagnostics
    assert "particle_tail_spread" in result.diagnostics
    assert "particle_weighted_skewness" in result.diagnostics


def test_particle_filter_belief_updater_records_likelihood_family() -> None:
    """PF updater should surface an explicit non-Gaussian likelihood family."""

    belief_store = BeliefStore(
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        rng=np.random.default_rng(0),
    )
    belief_store.ensure_method("Mug", "particle_filter")
    updater = ParticleFilterBeliefUpdater(
        belief_store,
        likelihood_family="gamma",
        rng=np.random.default_rng(0),
    )

    result = updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    stored_state = belief_store.get_state("Mug")

    assert stored_state["particle_likelihood_family"] == "gamma"
    assert result.diagnostics["particle_likelihood_family"] == "gamma"


def test_belief_updaters_accept_shared_observation_model() -> None:
    """Bayesian and PF updaters should consume the same observation payload API."""

    fixed_observation_model = _FixedObservationModel(observation=18.0, variance=4.0)
    bayesian_store = BeliefStore(
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
    )
    bayesian_updater = BayesianBeliefUpdater(
        bayesian_store,
        observation_model=fixed_observation_model,
    )
    bayesian_result = bayesian_updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    particle_store = BeliefStore(
        {
            "Mug": {
                "expected_duration": 20.0,
                "variance": 16.0,
                "method": "particle_filter",
                "particles": [12.0, 18.0, 24.0],
                "weights": [1 / 3, 1 / 3, 1 / 3],
            }
        },
    )
    particle_updater = ParticleFilterBeliefUpdater(
        particle_store,
        observation_model=fixed_observation_model,
        rng=np.random.default_rng(0),
    )
    particle_result = particle_updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    assert bayesian_result.diagnostics["observation"] == 18.0
    assert bayesian_result.diagnostics["likelihood_variance"] == 4.0
    assert bayesian_result.diagnostics["source"] == "fixed"
    assert particle_result.diagnostics["observation"] == 18.0
    assert particle_result.diagnostics["likelihood_variance"] == 4.0
    assert particle_result.diagnostics["source"] == "fixed"


def test_belief_store_constant_particle_initialization_is_degenerate() -> None:
    """Constant PF initialization should produce identical particles."""

    belief_store = BeliefStore(
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        particle_count=8,
        particle_distribution="constant",
        rng=np.random.default_rng(0),
    )

    particle_state = belief_store.ensure_method("Mug", "particle_filter")

    assert particle_state["particle_distribution"] == "constant"
    assert len(set(particle_state["particles"])) == 1
    assert particle_state["particles"][0] == 20.0


def test_create_monitoring_backend_initializes_particles_with_selected_distribution() -> None:
    """PF backend should persist the selected particle initialization family."""

    belief_store, monitoring_policy, belief_updater = create_monitoring_backend(
        "particle_filter",
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        particle_distribution="lognormal",
    )

    particle_state = belief_store.get_state("Mug")

    assert monitoring_policy.method == "particle_filter"
    assert belief_updater.method == "particle_filter"
    assert particle_state["particle_distribution"] == "lognormal"
    assert min(particle_state["particles"]) > 0.0
    assert len(set(particle_state["particles"])) > 1


def test_create_monitoring_backend_uses_runtime_eta_override_for_policy() -> None:
    """Backend factory should honor runtime eta overrides when building policies."""

    previous_eta = runtime_constants.BAYESIAN_THRESHOLD_PROBABILITY
    runtime_constants.set_bayesian_threshold_probability(0.9)
    try:
        _belief_store, monitoring_policy, _belief_updater = create_monitoring_backend(
            "bayesian",
            {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        )
    finally:
        runtime_constants.set_bayesian_threshold_probability(previous_eta)

    trigger_time = monitoring_policy.compute_trigger_time(
        MonitoringTriggerContext(
            object_name="Mug",
            critical_start_end_time=10.0,
            mean_duration=20.0,
            variance=16.0,
        )
    )

    expected = 10.0 + 20.0 + (4.0 * float(norm.ppf(0.9)))
    assert trigger_time == pytest.approx(expected)


def test_agent_update_monitoring_belief_updates_constraints_and_metadata(
    monkeypatch: MonkeyPatch,
) -> None:
    """Agent should update Bayesian posterior summaries and graph intervals."""

    state, start_subtask, monitor_subtask, end_subtask = _build_monitoring_update_state()

    belief_store = BeliefStore(
        {"Microwave": {"expected_duration": 100.0, "variance": 900.0}},
        rng=np.random.default_rng(0),
    )
    updater = BayesianBeliefUpdater(
        belief_store,
        rng=np.random.default_rng(0),
    )
    agent = Agent(
        ConstraintHandler(_DummyActionHandler()),
        {"Microwave": {"expected_duration": 100.0, "variance": 900.0}},
        belief_updater=updater,
        belief_store=belief_store,
        ground_truth_store=GroundTruthStore(
            {"Microwave": 100.0},
            config=GroundTruthConfig(distribution="constant", random_seed=0),
        ),
    )

    monkeypatch.setattr(agent.belief_store, "persist", lambda output_path=None: None)

    updated_state, monitored_subtask = agent.update_monitoring_belief(state)

    assert updated_state is state
    assert monitored_subtask is not None
    assert monitored_subtask["update_method"] == "bayesian"
    assert monitored_subtask["updated_subtask_name"] == start_subtask.name
    assert monitored_subtask["updated_expected_time"] > 0.0
    assert monitored_subtask["ground_truth_time"] == 100.0
    assert monitored_subtask["ground_truth_distribution"] == "constant"
    assert "observation" in monitored_subtask
    assert (
        state.constraints.edges[start_subtask.name, end_subtask.name]["info"][
            "Interval"
        ]
        == monitored_subtask["updated_expected_time"]
    )
    assert (
        state.constraints.edges[start_subtask.name, end_subtask.name]["info"][
            "Variance"
        ]
        == belief_store.get_summary("Microwave").variance
    )
    expected_remaining_interval = (
        28.01 + monitored_subtask["updated_expected_time"] - state.current_time
    )
    assert (
        state.constraints.edges[monitor_subtask.name, end_subtask.name]["info"][
            "Interval"
        ]
        == expected_remaining_interval
    )


def test_scheduler_monitoring_budget_counts_completed_monitors_per_interval() -> None:
    """Per-critical monitoring budgets should count executed monitor steps locally."""

    state, start_subtask, _monitor_subtask, end_subtask = _build_monitoring_update_state()
    action_handler = ActionHandler(nav_graph={})
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
        max_monitoring_per_critical_interval=1,
    )

    assert scheduler._count_monitoring_events_for_interval(
        state,
        critical_start_sub_end_time=28.01,
        critical_end_sub_name=end_subtask.name,
    ) == 1
    assert scheduler._monitoring_budget_reached(
        state,
        critical_start_sub_end_time=28.01,
        critical_end_sub_name=end_subtask.name,
    )

    scheduler_two = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
        max_monitoring_per_critical_interval=2,
    )
    assert not scheduler_two._monitoring_budget_reached(
        state,
        critical_start_sub_end_time=28.01,
        critical_end_sub_name=end_subtask.name,
    )


def test_expand_wait_with_monitoring_zero_wait_inserts_monitor_without_wait_node(
    monkeypatch: MonkeyPatch,
) -> None:
    """Zero computed wait should skip synthetic WAIT creation and insert monitoring directly."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture()
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: curr_node.state.current_time,
    )

    result_node = scheduler._expand_wait_with_monitoring(curr_node, candidate, [])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "Monitor"
    new_entries = result_node.state.completed_entries[
        len(curr_node.state.completed_entries) :
    ]
    assert len(new_entries) == 1
    assert new_entries[0].subtask.subtask_type == "Monitor"
    assert result_node.state.current_time == pytest.approx(
        curr_node.state.current_time + MONITORING_DURATION
    )
    _assert_no_zero_duration_waits(result_node.state.completed_entries)
    _assert_no_immediate_same_target_remonitoring(result_node.state.completed_entries)

def test_expand_wait_with_monitoring_zero_wait_suppresses_same_target_remonitor(
    monkeypatch: MonkeyPatch,
) -> None:
    """Immediate same-target re-monitoring should fall back instead of stacking monitors."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        previous_same_target_monitor=True
    )
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: curr_node.state.current_time,
    )

    result_node = scheduler._expand_wait_with_monitoring(curr_node, candidate, [])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    new_entries = result_node.state.completed_entries[
        len(curr_node.state.completed_entries) :
    ]
    assert len(new_entries) == 1
    assert new_entries[0].subtask.subtask_type == "WAIT"
    assert new_entries[0].schedule_end_time > new_entries[0].schedule_start_time
    _assert_no_zero_duration_waits(result_node.state.completed_entries)
    _assert_no_immediate_same_target_remonitoring(result_node.state.completed_entries)

def test_expand_wait_wo_monitoring_scores_against_post_wait_state(
    monkeypatch: MonkeyPatch,
) -> None:
    """Wait-without-monitoring should evaluate heuristic inputs on the post-wait child state."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=90.0,
        target_start_time=128.01,
    )
    captured: dict[str, Any] = {}

    def _record_calc_heuristic(
        current_node: SimulationNode,
        heuristic_candidate: Candidate,
        all_candidates: list[Candidate],
    ) -> tuple[int, float]:
        captured["node"] = current_node
        captured["candidate"] = heuristic_candidate
        captured["all_candidates"] = all_candidates
        return 0, 0.0

    monkeypatch.setattr(scheduler.cost_calculator, "calc_heuristic", _record_calc_heuristic)

    result_node = scheduler._expand_wait_wo_monitoring(curr_node, candidate, [])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    scored_node = captured["node"]
    assert scored_node.state.current_time == pytest.approx(result_node.state.current_time)
    assert scored_node.state.subtask.subtask_type == "WAIT"
    assert scored_node.state.completed_entries == result_node.state.completed_entries
    assert scored_node.state.completed_entries[-1].subtask.subtask_type == "WAIT"


def test_heuristic_manager_treats_negative_slack_within_grace_as_safe(
    monkeypatch: MonkeyPatch,
) -> None:
    """Scheduler risk grace should keep mildly late candidates out of risk 2."""

    heuristic_manager = HeuristicManager(_DummyActionHandler())
    subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    state = SchedulerState(
        subtask=subtask,
        completed_entries=[],
        remaining_subtasks=[subtask],
        constraints=nx.DiGraph(),
        current_time=10.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=subtask,
        is_critical=True,
        scheduling_due=SchedulingDue(
            due_date=25.0,
            due_related_sub_name=subtask.name,
        ),
    )

    monkeypatch.setattr(
        heuristic_manager,
        "check_future_conflict",
        lambda _current_node, _candidate: (0.0, None),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_estimate_total_time_needed_for_deadline_violation_check",
        lambda _current_node, _candidate: 15.0 + (RISK_GRACE_SECONDS / 2.0),
    )

    risk_level, urgency_cost = heuristic_manager._calculate_candidate_risk_and_urgency(
        node, candidate
    )

    assert risk_level == 0
    assert urgency_cost == pytest.approx(0.0)


def test_heuristic_manager_marks_negative_slack_outside_grace_as_risky(
    monkeypatch: MonkeyPatch,
) -> None:
    """Candidates later than planner grace should still become high risk."""

    heuristic_manager = HeuristicManager(_DummyActionHandler())
    subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    state = SchedulerState(
        subtask=subtask,
        completed_entries=[],
        remaining_subtasks=[subtask],
        constraints=nx.DiGraph(),
        current_time=10.0,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=subtask,
        is_critical=True,
        scheduling_due=SchedulingDue(
            due_date=25.0,
            due_related_sub_name=subtask.name,
        ),
    )

    monkeypatch.setattr(
        heuristic_manager,
        "check_future_conflict",
        lambda _current_node, _candidate: (0.0, None),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_estimate_total_time_needed_for_deadline_violation_check",
        lambda _current_node, _candidate: 15.0 + RISK_GRACE_SECONDS + 0.5,
    )

    risk_level, urgency_cost = heuristic_manager._calculate_candidate_risk_and_urgency(
        node, candidate
    )

    assert risk_level == 2
    assert urgency_cost > 10000.0


def test_expand_wait_with_monitoring_clamps_to_latest_safe_monitor_start(
    monkeypatch: MonkeyPatch,
) -> None:
    """Wait-with-monitoring should stop at the latest safe monitor point, not fall back to a longer plain wait."""

    current_time = 169.75
    target_start_time = 196.86585658205928
    nav_duration = 1.60
    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=current_time,
        target_start_time=target_start_time,
        estimated_first_nav_duration=nav_duration,
    )
    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: 194.44,
    )

    result_node = scheduler._expand_wait_with_monitoring(
        curr_node,
        candidate,
        [],
        nav_duration=nav_duration,
    )

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"

    expected_monitor_start = target_start_time - MONITORING_DURATION
    assert result_node.state.current_time == pytest.approx(expected_monitor_start)
    assert result_node.state.completed_entries[-1].schedule_nav_time == pytest.approx(
        nav_duration
    )
    assert result_node.state.subtask.execution.primitive_actions[0] == (
        "NAVIGATE_TO Microwave|01"
    )
    assert result_node.state.subtask.execution.primitive_actions[1].startswith("WAIT ")
    assert float(
        result_node.state.subtask.execution.primitive_actions[1].split()[1]
    ) == pytest.approx(expected_monitor_start - current_time - nav_duration)

    monitoring_subtasks = [
        subtask
        for subtask in result_node.state.remaining_subtasks
        if subtask.subtask_type == "Monitor"
    ]
    assert len(monitoring_subtasks) == 1
    monitor_subtask = monitoring_subtasks[0]
    monitor_to_end = result_node.state.constraints.edges[
        monitor_subtask.name,
        candidate.subtask.name,
    ]["info"]["Interval"]
    assert monitor_to_end == pytest.approx(0.0, abs=1e-9)


def test_expand_single_wait_prefers_earlier_other_target_monitoring_event(
    monkeypatch: MonkeyPatch,
) -> None:
    """Event-driven wait should advance to an earlier other-target monitoring event."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=34.15,
        target_start_time=128.01,
        estimated_first_nav_duration=1.60,
    )

    other_start_subtask = _make_subtask(
        "Cook Egg in Pan",
        primitive_actions=["COOK Egg|01"],
        subtask_type="Interaction",
    )
    other_end_subtask = _make_subtask(
        "Turn Off Stove After Cooking Egg",
        primitive_actions=["TOGGLE_OFF StoveKnob|01"],
        subtask_type="Interaction",
    )
    curr_node.state.constraints.add_edge(
        other_start_subtask.name,
        other_end_subtask.name,
        info={
            "Interval": 100.0,
            "IsCritical": True,
            "Variance": 900.0,
        },
    )
    curr_node.state.completed_entries.append(
        CompletedEntry(
            subtask=other_start_subtask,
            schedule_start_time=0.0,
            schedule_end_time=20.0,
            sim_start_time=0.0,
            sim_end_time=20.0,
            execution_status=TaskExecutionStatus.SUCCESS,
        )
    )
    curr_node.state.remaining_subtasks.append(other_end_subtask)
    other_candidate = Candidate(
        subtask=other_end_subtask,
        is_critical=True,
        actual_interaction_start_time=120.0,
        logical_interaction_start_time=120.0,
        estimated_first_nav_duration=0.0,
    )

    def _trigger_for_target(**kwargs: Any) -> float:
        raw_object_name = kwargs["raw_object_name"]
        if raw_object_name == "Microwave|01":
            return 120.0
        if raw_object_name == "StoveKnob|01":
            return 60.0
        raise AssertionError(f"Unexpected monitoring target: {raw_object_name}")

    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        _trigger_for_target,
    )

    result_node = scheduler._expand_single_wait(
        curr_node,
        candidate,
        [candidate, other_candidate],
    )

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    assert result_node.state.subtask.name == f"Wait for {other_end_subtask.name}"
    assert result_node.state.current_time == pytest.approx(60.0)
    assert result_node.state.completed_entries[-1].schedule_nav_time == pytest.approx(0.0)
    monitoring_subtasks = [
        subtask
        for subtask in result_node.state.remaining_subtasks
        if subtask.subtask_type == "Monitor"
    ]
    assert len(monitoring_subtasks) == 1
    assert _monitor_target_name(monitoring_subtasks[0]) == other_end_subtask.name
    _assert_no_zero_duration_waits(result_node.state.completed_entries)


def test_expand_single_wait_immediately_rescues_overdue_other_target_monitoring(
    monkeypatch: MonkeyPatch,
) -> None:
    """An overdue other-target trigger should insert monitoring now instead of a second wait."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=60.0,
        target_start_time=128.01,
    )
    other_start_subtask = _make_subtask(
        "Cook Egg in Pan",
        primitive_actions=["COOK Egg|01"],
        subtask_type="Interaction",
    )
    other_end_subtask = _make_subtask(
        "Turn Off Stove After Cooking Egg",
        primitive_actions=["TOGGLE_OFF StoveKnob|01"],
        subtask_type="Interaction",
    )
    curr_node.state.constraints.add_edge(
        other_start_subtask.name,
        other_end_subtask.name,
        info={
            "Interval": 100.0,
            "IsCritical": True,
            "Variance": 900.0,
        },
    )
    curr_node.state.completed_entries.append(
        CompletedEntry(
            subtask=other_start_subtask,
            schedule_start_time=0.0,
            schedule_end_time=20.0,
            sim_start_time=0.0,
            sim_end_time=20.0,
            execution_status=TaskExecutionStatus.SUCCESS,
        )
    )
    curr_node.state.remaining_subtasks.append(other_end_subtask)
    other_candidate = Candidate(
        subtask=other_end_subtask,
        is_critical=True,
        actual_interaction_start_time=120.0,
        logical_interaction_start_time=120.0,
        estimated_first_nav_duration=0.0,
    )

    def _trigger_for_target(**kwargs: Any) -> float:
        raw_object_name = kwargs["raw_object_name"]
        if raw_object_name == "Microwave|01":
            return 120.0
        if raw_object_name == "StoveKnob|01":
            return 50.0
        raise AssertionError(f"Unexpected monitoring target: {raw_object_name}")

    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        _trigger_for_target,
    )

    result_node = scheduler._expand_single_wait(
        curr_node,
        candidate,
        [candidate, other_candidate],
    )

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "Monitor"
    new_entries = result_node.state.completed_entries[
        len(curr_node.state.completed_entries) :
    ]
    assert len(new_entries) == 1
    assert new_entries[0].subtask.subtask_type == "Monitor"
    assert _monitor_target_name(new_entries[0].subtask) == other_end_subtask.name
    _assert_no_zero_duration_waits(result_node.state.completed_entries)
    _assert_no_immediate_same_target_remonitoring(result_node.state.completed_entries)


def test_expand_single_wait_ignores_missing_rescue_target_and_falls_back_to_local_wait(
    monkeypatch: MonkeyPatch,
) -> None:
    """A rescue obligation without an exact candidate should not block the local wait event."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=34.15,
        target_start_time=128.01,
        estimated_first_nav_duration=1.60,
    )
    missing_obligation = MonitoringObligation(
        trigger_time=60.0,
        variance=900.0,
        due=SchedulingDue(
            due_date=120.0,
            due_related_sub_name="Missing Target",
        ),
    )

    def _stub_obligations(
        _curr_node: SimulationNode,
        _candidate: Candidate,
        *,
        expansion_kind: str,
        restrict_wait_target: bool = True,
    ) -> list[MonitoringObligation]:
        if expansion_kind != "wait":
            return []
        if restrict_wait_target:
            return []
        return [missing_obligation]

    monkeypatch.setattr(
        scheduler,
        "_get_relevant_monitoring_obligations",
        _stub_obligations,
    )

    result_node = scheduler._expand_single_wait(curr_node, candidate, [candidate])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    assert result_node.state.subtask.name == f"Wait for {candidate.subtask.name}"
    assert result_node.state.current_time == pytest.approx(candidate.actual_interaction_start_time)
    assert result_node.state.completed_entries[-1].schedule_nav_time == pytest.approx(
        1.60
    )


def test_expand_single_wait_skips_late_local_monitor_and_falls_back_to_local_execute(
    monkeypatch: MonkeyPatch,
) -> None:
    """A late local monitor should not survive just because the drifted target start is later."""

    action_handler = _MonitoringOnlyActionHandler(nav_duration=1.44)
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=_DummyHeuristicManager(),
    )
    start_subtask = _make_subtask(
        "Cook Egg in Pan",
        primitive_actions=["COOK Egg|01"],
        subtask_type="Interaction",
    )
    current_subtask = _make_subtask(
        "REMAIN_Wash Cup and place on counterTop",
        primitive_actions=["CLEAN Cup|01"],
        subtask_type="Interaction",
        decomposed=True,
    )
    end_subtask = _make_subtask(
        "Turn Off Stove After Cooking Egg",
        primitive_actions=["TOGGLE_OFF StoveKnob|01"],
        subtask_type="Interaction",
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 1600.0},
    )
    state = SchedulerState(
        subtask=current_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=start_subtask,
                schedule_start_time=44.40,
                schedule_end_time=64.23,
                sim_start_time=44.40,
                sim_end_time=64.23,
                execution_status=TaskExecutionStatus.SUCCESS,
            ),
            CompletedEntry(
                subtask=current_subtask,
                schedule_start_time=151.43,
                schedule_end_time=169.54,
                sim_start_time=151.43,
                sim_end_time=169.54,
                execution_status=TaskExecutionStatus.SUCCESS,
            ),
        ],
        remaining_subtasks=[end_subtask],
        constraints=constraints,
        current_time=169.54,
        scene_positions={"agent": (0.0, 0.9, 0.0)},
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=end_subtask,
        is_critical=True,
        actual_interaction_start_time=170.98,
        logical_interaction_start_time=170.98,
        estimated_first_nav_duration=1.44,
    )

    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: 152.967937378216,
    )

    result_node = scheduler._expand_single_wait(curr_node, candidate, [candidate])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    assert result_node.state.subtask.name == f"Wait for {candidate.subtask.name}"
    assert result_node.state.current_time == pytest.approx(170.98)
    assert all(
        subtask.subtask_type != "Monitor" for subtask in result_node.state.remaining_subtasks
    )
    _assert_no_zero_duration_waits(result_node.state.completed_entries)


def test_expand_single_wait_rejects_immediate_zero_interval_successor() -> None:
    """A zero-interval critical successor should not materialize as a scheduler WAIT branch."""

    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
    )
    predecessor_subtask = _make_subtask(
        "Turn Off Faucet after Pot is Filled",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
        subtask_type="Interaction",
    )
    candidate_subtask = _make_subtask(
        "Place Pot on Stove and Start Boiling",
        primitive_actions=["PLACE Pot|01 StoveBurner|01"],
        subtask_type="Interaction",
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        predecessor_subtask.name,
        candidate_subtask.name,
        info={"Interval": 0.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=predecessor_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=predecessor_subtask,
                schedule_start_time=117.40,
                schedule_end_time=123.73,
                sim_start_time=117.40,
                sim_end_time=123.73,
                execution_status=TaskExecutionStatus.SUCCESS,
            )
        ],
        remaining_subtasks=[candidate_subtask],
        constraints=constraints,
        current_time=123.73,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "StoveBurner|01": (1.0, 0.0, 0.0),
        },
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=candidate_subtask,
        is_critical=True,
        logical_interaction_start_time=127.65,
        actual_interaction_start_time=127.65,
        estimated_first_nav_duration=0.0,
    )

    result_node = scheduler._expand_single_wait(curr_node, candidate, [candidate])

    assert result_node is None


def test_expand_candidates_skips_conflict_wait_for_immediate_zero_interval_successor(
    monkeypatch: MonkeyPatch,
) -> None:
    """Conflict-avoidance should not create WAIT for an immediate zero-interval successor."""

    scheduler = Scheduler(
        action_handler=_DummyActionHandler(),
        constraint_handler=ConstraintHandler(_DummyActionHandler()),
        heuristic_manager=_DummyHeuristicManager(),
    )
    predecessor_subtask = _make_subtask(
        "Turn Off Faucet after Pot is Filled",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
        subtask_type="Interaction",
    )
    candidate_subtask = _make_subtask(
        "Place Pot on Stove and Start Boiling",
        primitive_actions=["PLACE Pot|01 StoveBurner|01"],
        subtask_type="Interaction",
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        predecessor_subtask.name,
        candidate_subtask.name,
        info={"Interval": 0.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=predecessor_subtask,
        completed_entries=[
            CompletedEntry(
                subtask=predecessor_subtask,
                schedule_start_time=117.40,
                schedule_end_time=123.73,
                sim_start_time=117.40,
                sim_end_time=123.73,
                execution_status=TaskExecutionStatus.SUCCESS,
            )
        ],
        remaining_subtasks=[candidate_subtask],
        constraints=constraints,
        current_time=123.73,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "StoveBurner|01": (1.0, 0.0, 0.0),
        },
        held_object=None,
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=state,
        risk_level=0,
    )
    candidate = Candidate(
        subtask=candidate_subtask,
        is_critical=True,
        logical_interaction_start_time=123.73,
        actual_interaction_start_time=123.73,
        estimated_first_nav_duration=0.0,
    )

    monkeypatch.setattr(
        scheduler.cost_calculator,
        "check_future_conflict",
        lambda *_args, **_kwargs: (4.0, "Victim Task"),
        raising=False,
    )

    def _stub_expand_single_subtask(
        current_node: SimulationNode,
        expanded_candidate: Candidate,
        _not_yet_candidates: list[Candidate],
        _feasible_candidates: list[Candidate] | None = None,
    ) -> SimulationNode:
        next_state = current_node.state._replace(subtask=expanded_candidate.subtask)
        return SimulationNode(
            heuristic_cost=0.0,
            depth=current_node.depth + 1,
            tie_breaker=1,
            parent_node=current_node,
            state=next_state,
            risk_level=current_node.risk_level,
        )

    monkeypatch.setattr(scheduler, "_expand_single_subtask", _stub_expand_single_subtask)

    expansions = scheduler._expand_candidates(curr_node, [candidate], [])

    assert len(expansions) == 1
    assert expansions[0].state.subtask.name == candidate_subtask.name
    assert all(node.state.subtask.subtask_type != "WAIT" for node in expansions)


def test_expand_wait_with_monitoring_scores_against_post_wait_state(
    monkeypatch: MonkeyPatch,
) -> None:
    """Wait-with-monitoring should evaluate heuristic inputs on the returned child state."""

    scheduler, curr_node, candidate = _build_zero_wait_wait_monitoring_fixture(
        current_time=90.0,
        target_start_time=128.01,
    )
    captured: dict[str, Any] = {}

    def _record_calc_heuristic(
        current_node: SimulationNode,
        heuristic_candidate: Candidate,
        all_candidates: list[Candidate],
    ) -> tuple[int, float]:
        captured["node"] = current_node
        captured["candidate"] = heuristic_candidate
        captured["all_candidates"] = all_candidates
        return 0, 0.0

    monkeypatch.setattr(
        scheduler,
        "_compute_monitoring_trigger_time",
        lambda **_kwargs: 100.0,
    )
    monkeypatch.setattr(scheduler.cost_calculator, "calc_heuristic", _record_calc_heuristic)

    result_node = scheduler._expand_wait_with_monitoring(curr_node, candidate, [])

    assert result_node is not None
    assert result_node.state.subtask.subtask_type == "WAIT"
    scored_node = captured["node"]
    assert scored_node.state.current_time == pytest.approx(result_node.state.current_time)
    assert scored_node.state.subtask.subtask_type == "WAIT"
    assert scored_node.state.completed_entries == result_node.state.completed_entries
    monitoring_subtasks = [
        subtask
        for subtask in scored_node.state.remaining_subtasks
        if subtask.subtask_type == "Monitor"
    ]
    assert len(monitoring_subtasks) == 1
    monitor_subtask = monitoring_subtasks[0]
    assert result_node.state.constraints is scored_node.state.constraints
    assert scored_node.state.constraints.has_edge(
        scored_node.state.subtask.name, monitor_subtask.name
    )
    assert scored_node.state.constraints.has_edge(
        monitor_subtask.name, candidate.subtask.name
    )


def test_agent_update_monitoring_belief_with_particle_filter_updates_constraints(
    monkeypatch: MonkeyPatch,
) -> None:
    """Agent should apply particle-filter posterior summaries to constraints."""

    state, start_subtask, monitor_subtask, end_subtask = _build_monitoring_update_state()

    belief_store = BeliefStore(
        {
            "Microwave": {
                "expected_duration": 100.0,
                "variance": 900.0,
                "method": "particle_filter",
                "particles": [80.0, 100.0, 120.0, 140.0],
                "weights": [0.25, 0.25, 0.25, 0.25],
            }
        },
        rng=np.random.default_rng(0),
    )
    updater = ParticleFilterBeliefUpdater(
        belief_store,
        rng=np.random.default_rng(0),
    )
    agent = Agent(
        ConstraintHandler(_DummyActionHandler()),
        {"Microwave": {"expected_duration": 100.0, "variance": 900.0}},
        belief_updater=updater,
        belief_store=belief_store,
        ground_truth_store=GroundTruthStore(
            {"Microwave": 100.0},
            config=GroundTruthConfig(distribution="constant", random_seed=0),
        ),
    )

    monkeypatch.setattr(agent.belief_store, "persist", lambda output_path=None: None)

    updated_state, monitored_subtask = agent.update_monitoring_belief(state)

    assert updated_state is state
    assert monitored_subtask is not None
    assert monitored_subtask["update_method"] == "particle_filter"
    assert monitored_subtask["updated_subtask_name"] == start_subtask.name
    assert monitored_subtask["updated_expected_time"] > 0.0
    assert monitored_subtask["ground_truth_time"] == 100.0
    assert monitored_subtask["ground_truth_distribution"] == "constant"
    assert "ess_before_resample" in monitored_subtask
    assert "resample_count" in monitored_subtask
    assert "particle_quantile_p10" in monitored_subtask
    assert "particle_quantile_p50" in monitored_subtask
    assert "particle_quantile_p90" in monitored_subtask
    assert "particle_tail_spread" in monitored_subtask
    assert "particle_weighted_skewness" in monitored_subtask
    assert (
        state.constraints.edges[start_subtask.name, end_subtask.name]["info"][
            "Interval"
        ]
        == monitored_subtask["updated_expected_time"]
    )
    assert (
        state.constraints.edges[start_subtask.name, end_subtask.name]["info"][
            "Variance"
        ]
        == belief_store.get_summary("Microwave").variance
    )
    expected_remaining_interval = (
        28.01 + monitored_subtask["updated_expected_time"] - state.current_time
    )
    assert (
        state.constraints.edges[monitor_subtask.name, end_subtask.name]["info"][
            "Interval"
        ]
        == expected_remaining_interval
    )


def test_create_monitoring_backend_wires_shared_components() -> None:
    """Factory should return a shared store with matching policy and updater."""

    belief_store, monitoring_policy, belief_updater = create_monitoring_backend(
        "particle_filter",
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
    )

    assert monitoring_policy.method == "particle_filter"
    assert belief_updater.method == "particle_filter"
    assert belief_store.get_summary("Mug").method == "particle_filter"


def test_serialize_completed_entries_preserves_monitored_subtask_payload() -> None:
    """Result serialization should keep monitoring diagnostics in each entry."""

    monitored_entry = CompletedEntry(
        subtask=_make_subtask(
            "Monitoring for Mug",
            primitive_actions=["MONITORING Mug|01"],
            subtask_type="Monitor",
            objects=["Mug|01"],
        ),
        schedule_start_time=10.0,
        schedule_end_time=12.0,
        sim_start_time=10.0,
        sim_end_time=12.0,
    )
    monitored_entry.execution_status = True
    monitored_entry.monitored_subtask = {
        "updated_subtask_name": "Prepare Mug",
        "ground_truth_time": 111.0,
        "ground_truth_distribution": "gamma",
    }

    serialized_entries = serialize_completed_entries([monitored_entry])

    assert serialized_entries[0]["monitored_subtask"]["updated_subtask_name"] == "Prepare Mug"
    assert serialized_entries[0]["monitored_subtask"]["ground_truth_time"] == 111.0
    assert (
        serialized_entries[0]["monitored_subtask"]["ground_truth_distribution"]
        == "gamma"
    )


def test_calculate_timing_success_rate_uses_sampled_ground_truth_override() -> None:
    """Critical-edge evaluation should use sampled GT overrides when provided."""

    start_subtask = _make_subtask(
        "Start Microwave for Heating Potato",
        primitive_actions=["TOGGLE_ON Microwave|01"],
        objects={"Microwave|01": 1},
    )
    end_subtask = _make_subtask(
        "Turn Off Microwave after Heating Potato",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
        objects={"Microwave|01": 1},
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        start_subtask.name,
        end_subtask.name,
        info={"Interval": 100.0, "IsCritical": True, "Variance": 900.0},
    )
    result_schedule = [
        CompletedEntry(
            subtask=start_subtask,
            schedule_start_time=0.0,
            schedule_end_time=10.0,
            sim_start_time=0.0,
            sim_end_time=10.0,
        ),
        CompletedEntry(
            subtask=end_subtask,
            schedule_start_time=126.0,
            schedule_end_time=131.0,
            sim_start_time=126.0,
            sim_end_time=131.0,
        ),
    ]

    default_sim_rate, default_sched_rate, _ = calculate_timing_success_rate(
        constraints,
        result_schedule,
    )
    override_sim_rate, override_sched_rate, detail_log = calculate_timing_success_rate(
        constraints,
        result_schedule,
        ground_truth_overrides={"Microwave": 120.0},
    )

    assert default_sim_rate == 0.0
    assert default_sched_rate == 0.0
    assert override_sim_rate == 1.0
    assert override_sched_rate == 1.0
    assert (
        detail_log[f"{start_subtask.name} -> {end_subtask.name}"][
            "Original Timing Constraint"
        ]
        == "(120.0, True)"
    )
