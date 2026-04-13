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
    evaluate_duration_observation_likelihood,
    resolve_duration_sampling_variance,
)
from src.core.scheduler import Scheduler
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
from src.utils.config.constants import (
    BAYESIAN_THRESHOLD_PROBABILITY,
    NAV_STEP_DURATION,
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


def test_bayesian_monitoring_policy_default_follows_runtime_eta_constant() -> None:
    """Omitted ``threshold_probability`` must read the live global ``eta``/threshold.

    Regression guard: a default parameter evaluated only at import time caused
    ``constants.set_bayesian_threshold_probability`` (offline harness / CLI) to
    be ignored when constructing ``BayesianMonitoringPolicy(belief_store)``.
    """

    import src.utils.config.constants as runtime_constants

    belief_store = BeliefStore({"Mug": {"expected_duration": 20.0, "variance": 9.0}})
    previous = float(runtime_constants.BAYESIAN_THRESHOLD_PROBABILITY)
    try:
        runtime_constants.set_bayesian_threshold_probability(0.25)
        policy_a = BayesianMonitoringPolicy(belief_store)
        assert policy_a._threshold_probability == pytest.approx(0.25)

        runtime_constants.set_bayesian_threshold_probability(0.75)
        policy_b = BayesianMonitoringPolicy(belief_store)
        assert policy_b._threshold_probability == pytest.approx(0.75)
    finally:
        runtime_constants.set_bayesian_threshold_probability(previous)


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
    assert sampled_intervals["Microwave"] != sampled_intervals["CoffeeMachine"]
    assert "CounterTop" not in sampled_intervals
    assert ground_truth_store.as_dict() == sampled_intervals


def test_default_gt_sampling_variance_uses_harder_non_gaussian_presets() -> None:
    """Default GT sampling variance should widen non-Gaussian stress cases."""

    mean = 100.0

    assert resolve_duration_sampling_variance(
        distribution="gaussian",
        mean=mean,
    ) == pytest.approx(900.0)
    assert resolve_duration_sampling_variance(
        distribution="lognormal",
        mean=mean,
    ) == pytest.approx(2500.0)
    assert resolve_duration_sampling_variance(
        distribution="gamma",
        mean=mean,
    ) == pytest.approx(2500.0)
    assert resolve_duration_sampling_variance(
        distribution="mixture",
        mean=mean,
    ) == pytest.approx(3600.0)


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


def test_scheduler_executes_feasible_candidate_atomically_without_prenavigation(
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


def test_scheduler_keeps_monitoring_path_before_prenavigation(
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


def test_scheduler_expands_blocked_candidate_prenavigation_frontier(
    monkeypatch: MonkeyPatch,
) -> None:
    """Blocked frontier candidates should emit both WAIT and PRENAV branches."""

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
            action_full_name=actions[0],
            action_type="NAVIGATE_TO",
            cumulative_time=2.0,
            action_duration=2.0,
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

    assert len(expansions) == 2
    assert {child.state.subtask.subtask_type for child in expansions} == {
        "WAIT",
        "NAVIGATE",
    }


def test_scheduler_skips_blocked_prenavigation_for_monitoring_candidates(
    monkeypatch: MonkeyPatch,
) -> None:
    """Blocked pre-navigation should stay conservative when monitoring is needed."""

    action_handler = ActionHandler(nav_graph={})
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=ConstraintHandler(action_handler),
        heuristic_manager=HeuristicManager(action_handler),
    )
    candidate = Candidate(
        subtask=_make_subtask(
            "Heat Mug",
            primitive_actions=["NAVIGATE_TO Mug|1", "TOGGLE_ON Mug|1"],
        ),
        is_critical=True,
        actual_interaction_start_time=20.0,
        logical_interaction_start_time=20.0,
        estimated_first_nav_duration=2.0,
    )

    monkeypatch.setattr(
        scheduler,
        "_should_split_with_monitoring",
        lambda *_args, **_kwargs: (True, SchedulingDue(20.0, candidate.subtask.name)),
    )
    monkeypatch.setattr(
        action_handler,
        "get_actions_info",
        lambda _node, actions: ActionResult(
            action_full_name=actions[0],
            action_type="NAVIGATE_TO",
            cumulative_time=2.0,
            action_duration=2.0,
            scene_positions={"agent": (1.0, 0.9, 0.0)},
            held_object=None,
            success=True,
            first_nav_duration=2.0,
        ),
    )

    blocked_prenav = scheduler._expand_blocked_prenavigation(
        SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
            state=SchedulerState(
                subtask=candidate.subtask,
                completed_entries=[],
                remaining_subtasks=[candidate.subtask],
                constraints=nx.DiGraph(),
                current_time=10.0,
                scene_positions={"agent": (0.0, 0.9, 0.0)},
                held_object=None,
            ),
            risk_level=0,
        ),
        candidate,
        [candidate],
        [],
    )

    assert blocked_prenav is None


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


def test_future_conflict_positive_delay_is_penalized(
    monkeypatch: MonkeyPatch,
) -> None:
    """Any positive future-conflict delay should be penalized under strict semantics."""

    action_handler = ActionHandler(nav_graph={})
    heuristic_manager = HeuristicManager(action_handler)
    candidate_subtask = _make_subtask(
        "Start Bread Heating",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    target_subtask = _make_subtask(
        "Turn Off Microwave",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    reserved_last_subtask = _make_subtask(
        "Turn Off Faucet",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        candidate_subtask.name,
        target_subtask.name,
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=candidate_subtask,
        completed_entries=[],
        remaining_subtasks=[candidate_subtask, target_subtask, reserved_last_subtask],
        constraints=constraints,
        current_time=0.0,
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
    candidate = Candidate(
        subtask=candidate_subtask,
        is_critical=False,
        estimated_first_nav_duration=0.0,
    )

    monkeypatch.setattr(
        heuristic_manager,
        "_get_estimated_pure_interaction_time",
        lambda subtask: 4.5 if subtask.name == candidate_subtask.name else 0.0,
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_reserved_windows",
        lambda _node: [(100.0, 110.0, "reserved-owner", reserved_last_subtask.name)],
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_chain_info",
        lambda _node, subtask: (5.0, {subtask.name}, subtask.name),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_task_interaction_location",
        lambda _subtask, _scene_positions: (0.0, 0.0, 0.0),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_estimate_navigation_time_between_positions",
        lambda _a, _b: 2.5,
    )

    conflict_delay, victim = heuristic_manager.check_future_conflict(
        curr_node, candidate
    )

    assert conflict_delay == pytest.approx(8.0)
    assert victim == target_subtask.name


def test_future_conflict_zero_wait_is_ignored(
    monkeypatch: MonkeyPatch,
) -> None:
    """Zero effective wait should not be treated as a future conflict."""

    action_handler = ActionHandler(nav_graph={})
    heuristic_manager = HeuristicManager(action_handler)
    candidate_subtask = _make_subtask(
        "Start Bread Heating",
        primitive_actions=["TOGGLE_ON Microwave|01"],
    )
    target_subtask = _make_subtask(
        "Turn Off Microwave",
        primitive_actions=["TOGGLE_OFF Microwave|01"],
    )
    reserved_last_subtask = _make_subtask(
        "Turn Off Faucet",
        primitive_actions=["TOGGLE_OFF Faucet|01"],
    )
    constraints = nx.DiGraph()
    constraints.add_edge(
        candidate_subtask.name,
        target_subtask.name,
        info={"Interval": 100.0, "IsCritical": True},
    )
    state = SchedulerState(
        subtask=candidate_subtask,
        completed_entries=[],
        remaining_subtasks=[candidate_subtask, target_subtask, reserved_last_subtask],
        constraints=constraints,
        current_time=0.0,
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
    candidate = Candidate(
        subtask=candidate_subtask,
        is_critical=False,
        estimated_first_nav_duration=0.0,
    )

    monkeypatch.setattr(
        heuristic_manager,
        "_get_estimated_pure_interaction_time",
        lambda subtask: 4.5 if subtask.name == candidate_subtask.name else 0.0,
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_reserved_windows",
        lambda _node: [(100.0, 105.0, "reserved-owner", reserved_last_subtask.name)],
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_chain_info",
        lambda _node, subtask: (5.0, {subtask.name}, subtask.name),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_get_task_interaction_location",
        lambda _subtask, _scene_positions: (0.0, 0.0, 0.0),
    )
    monkeypatch.setattr(
        heuristic_manager,
        "_estimate_navigation_time_between_positions",
        lambda _a, _b: 0.0,
    )

    conflict_delay, victim = heuristic_manager.check_future_conflict(
        curr_node, candidate
    )

    assert conflict_delay == pytest.approx(0.0)
    assert victim is None

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


def test_heuristic_remaining_work_mst_uses_residual_tasks_only(
    monkeypatch: MonkeyPatch,
) -> None:
    """Remaining-work MST should exclude the candidate chain already being executed."""

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

    assert captured_tasks["names"] == [unrelated_subtask.name]


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


def test_constraint_handler_assigns_due_from_not_ready_critical_inferred_due() -> None:
    """Feasible candidates should inherit due from blocked critical candidates."""

    action_handler = ActionHandler(nav_graph={})
    constraint_handler = ConstraintHandler(action_handler)
    feasible_candidate = Candidate(
        subtask=_make_subtask(
            "Wash Spoon",
            primitive_actions=["PLACE Spoon|01 CounterTop|01"],
        ),
        is_critical=False,
    )
    blocked_critical = Candidate(
        subtask=_make_subtask(
            "Turn Off Microwave",
            primitive_actions=["TOGGLE_OFF Microwave|01"],
        ),
        is_critical=True,
        logical_interaction_start_time=None,
        scheduling_due=SchedulingDue(
            due_date=165.0,
            due_related_sub_name="Turn Off Microwave",
        ),
    )
    curr_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=SchedulerState(
            subtask=feasible_candidate.subtask,
            completed_entries=[],
            remaining_subtasks=[feasible_candidate.subtask, blocked_critical.subtask],
            constraints=nx.DiGraph(),
            current_time=150.0,
            scene_positions={},
            held_object=None,
        ),
        risk_level=0,
    )

    constraint_handler._assign_scheduling_due(
        [feasible_candidate],
        [blocked_critical],
        curr_node,
    )

    assert feasible_candidate.scheduling_due == SchedulingDue(
        due_date=165.0,
        due_related_sub_name="Turn Off Microwave",
    )


def test_scheduler_detects_active_bayesian_monitoring_interval() -> None:
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

    need_monitor, due_info = scheduler._should_split_with_monitoring(
        curr_node, candidate
    )

    assert need_monitor is True
    assert due_info is not None
    assert due_info.due_related_sub_name == end_subtask.name
    assert due_info.due_date == 128.01


def test_scheduler_reuses_monitoring_caches_within_search_session() -> None:
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
        assert scheduler._search_cache.trigger_cache_hits == 1
    finally:
        scheduler._end_search_session()


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


def test_particle_filter_belief_updater_uses_configured_likelihood_family(
    monkeypatch: MonkeyPatch,
) -> None:
    """PF updater should evaluate weights with the configured likelihood family."""

    captured: dict[str, Any] = {}

    def _fake_likelihood(
        *,
        observation: float,
        hypotheses: np.ndarray,
        variance: float,
        family: str,
    ) -> np.ndarray:
        captured["observation"] = observation
        captured["variance"] = variance
        captured["family"] = family
        return np.ones_like(hypotheses, dtype=float)

    monkeypatch.setattr(
        "src.core.monitoring.evaluate_duration_observation_likelihood",
        _fake_likelihood,
    )

    belief_store = BeliefStore(
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
    updater = ParticleFilterBeliefUpdater(
        belief_store,
        likelihood_family="mixture",
        observation_model=_FixedObservationModel(observation=18.0, variance=4.0),
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

    assert captured["family"] == "mixture"
    assert result.diagnostics["particle_likelihood_family"] == "mixture"


def test_create_monitoring_backend_passes_particle_likelihood_family() -> None:
    """PF backend should preserve the configured likelihood family during updates."""

    belief_store, _monitoring_policy, belief_updater = create_monitoring_backend(
        "particle_filter",
        {"Mug": {"expected_duration": 20.0, "variance": 16.0}},
        particle_distribution="gaussian",
        particle_likelihood_family="lognormal",
        observation_model=_FixedObservationModel(observation=18.0, variance=4.0),
        random_seed=0,
    )

    result = belief_updater.update(
        BeliefUpdateContext(
            object_name="Mug",
            gt_interval=15.0,
            prior_mean=20.0,
            prior_variance=16.0,
            elapsed_interval=12.0,
        )
    )

    assert belief_store.get_state("Mug")["particle_distribution"] == "gaussian"
    assert result.diagnostics["particle_likelihood_family"] == "lognormal"


def test_evaluate_duration_observation_likelihood_supports_non_gaussian_families() -> None:
    """Shared likelihood evaluator should support the configured non-Gaussian families."""

    hypotheses = np.array([80.0, 100.0, 120.0], dtype=float)

    for family in ("gaussian", "lognormal", "gamma", "mixture"):
        weights = evaluate_duration_observation_likelihood(
            observation=105.0,
            hypotheses=hypotheses,
            variance=25.0,
            family=family,
        )
        assert weights.shape == hypotheses.shape
        assert np.all(np.isfinite(weights))
        assert np.all(weights >= 0.0)


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
