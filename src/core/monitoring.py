from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Protocol

import numpy as np
from scipy.stats import norm

from src.utils.common import create_module_logger
from src.utils.config.constants import (
    AGENT_KNOWLEDGE_PATH,
    BAYESIAN_THRESHOLD_PROBABILITY,
    FACTOR_ALPHA,
    INIT_PRIOR_MEAN,
    INIT_PRIOR_VARIANCE,
    MIN_VARIANCE,
)

BeliefMethod = Literal["bayesian", "particle_filter"]
GroundTruthDistribution = Literal[
    "constant",
    "gaussian",
    "lognormal",
    "gamma",
    "mixture",
]


@dataclass(frozen=True)
class GroundTruthConfig:
    """Describe how runtime ground-truth durations are sampled.

    Args:
        distribution: Distribution family used to sample the latent duration.
        random_seed: Seed for reproducible sampling across runs.
    """

    distribution: GroundTruthDistribution = "constant"
    random_seed: int = 42


class GroundTruthStore:
    """Sample and cache runtime ground-truth durations per monitored object.

    The store samples each object's latent duration at most once per run and
    reuses the sampled value for all subsequent monitoring updates.

    Args:
        base_truths: Base interval table keyed by object type.
        config: Sampling configuration.
        rng: Optional random generator for tests.
    """

    def __init__(
        self,
        base_truths: Optional[Mapping[str, float]] = None,
        *,
        config: Optional[GroundTruthConfig] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        self._base_truths = {
            object_name: float(interval)
            for object_name, interval in (base_truths or {}).items()
        }
        self._config = config or GroundTruthConfig()
        self._rng = rng or np.random.default_rng(self._config.random_seed)
        self._samples: dict[str, float] = {}

    @property
    def distribution(self) -> GroundTruthDistribution:
        """Return the configured ground-truth distribution family."""

        return self._config.distribution

    @property
    def random_seed(self) -> int:
        """Return the configured random seed."""

        return self._config.random_seed

    def get_interval(self, object_name: str) -> Optional[float]:
        """Return the sampled runtime duration for an object.

        Args:
            object_name: Monitored object type.

        Returns:
            Sampled duration when the object is known, otherwise ``None``.
        """

        if object_name not in self._base_truths:
            return None
        if object_name not in self._samples:
            self._samples[object_name] = self._sample_interval(
                self._base_truths[object_name]
            )
        return self._samples[object_name]

    def as_dict(self) -> dict[str, float]:
        """Return sampled ground-truth durations as a serializable mapping."""

        return dict(self._samples)

    def _sample_interval(self, base_interval: float) -> float:
        """Sample a positive latent duration from the configured family.

        Args:
            base_interval: Baseline interval for the object type.

        Returns:
            Positive sampled duration.
        """

        sampled = _sample_positive_duration(
            distribution=self._config.distribution,
            mean=max(MIN_VARIANCE, float(base_interval)),
            variance=max(MIN_VARIANCE, float(base_interval) * 0.1),
            sample_count=1,
            rng=self._rng,
        )[0]
        return max(MIN_VARIANCE, float(sampled))

log = create_module_logger(module_name=__name__, module_log=True)


@dataclass(frozen=True)
class BeliefSummary:
    """Summarize a belief distribution for scheduling decisions.

    Args:
        expected_duration: Mean estimate of the interval duration.
        variance: Variance of the interval duration estimate.
        method: Active inference backend for this belief.
    """

    expected_duration: float
    variance: float
    method: BeliefMethod


@dataclass(frozen=True)
class MonitoringTriggerContext:
    """Hold the inputs needed to compute a monitoring trigger time.

    Args:
        object_name: Object type associated with the monitored interval.
        critical_start_end_time: Absolute end time of the critical start subtask.
        mean_duration: Current expected interval duration.
        variance: Current interval variance.
    """

    object_name: Optional[str]
    critical_start_end_time: float
    mean_duration: float
    variance: float


@dataclass(frozen=True)
class BeliefUpdateContext:
    """Hold the inputs needed for a posterior update.

    Args:
        object_name: Object type whose belief is updated.
        gt_interval: Ground-truth interval used by the simulator.
        prior_mean: Prior expected duration.
        prior_variance: Prior variance.
        elapsed_interval: Elapsed time since the critical start completed.
    """

    object_name: str
    gt_interval: float
    prior_mean: float
    prior_variance: float
    elapsed_interval: float


@dataclass
class BeliefUpdateResult:
    """Store posterior summary and backend-specific diagnostics.

    Args:
        posterior_mean: Updated posterior mean.
        posterior_variance: Updated posterior variance.
        method: Backend that produced the update.
        belief_state: Serializable belief state to persist in the store.
        diagnostics: Extra debug values from the update process.
    """

    posterior_mean: float
    posterior_variance: float
    method: BeliefMethod
    belief_state: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)


class MonitoringPolicy(Protocol):
    """Protocol for computing backend-specific monitoring trigger times."""

    method: BeliefMethod

    def compute_trigger_time(self, context: MonitoringTriggerContext) -> float:
        """Return the absolute time to insert monitoring."""


class BeliefUpdater(Protocol):
    """Protocol for backend-specific posterior updates."""

    method: BeliefMethod

    def update(self, context: BeliefUpdateContext) -> BeliefUpdateResult:
        """Update belief state after a monitoring action."""


class BeliefStore:
    """Manage serializable belief states for all monitored objects."""

    def __init__(
        self,
        initial_beliefs: Optional[Mapping[str, Mapping[str, Any]]] = None,
        *,
        particle_count: int = 128,
        particle_distribution: GroundTruthDistribution = "gaussian",
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        """Initialize the store from a legacy belief dictionary.

        Args:
            initial_beliefs: Existing belief mapping keyed by object type.
            particle_count: Default particle count for particle-filter mode.
            particle_distribution: Distribution family used to initialize PF particles.
            rng: Optional random generator for deterministic tests.
        """

        self._particle_count = particle_count
        self._particle_distribution = particle_distribution
        self._rng = rng or np.random.default_rng()
        self._beliefs: dict[str, dict[str, Any]] = {}

        for object_name, raw_state in (initial_beliefs or {}).items():
            self._beliefs[object_name] = self._normalize_state(raw_state)

    def get_state(self, object_name: str) -> dict[str, Any]:
        """Return a mutable copy of the stored belief state.

        Args:
            object_name: Object type key.

        Returns:
            Serializable belief state for the object.
        """

        state = self._beliefs.get(object_name)
        if state is None:
            state = self._default_state()
            self._beliefs[object_name] = state
        return self._copy_state(state)

    def get_summary(self, object_name: str) -> BeliefSummary:
        """Return the summary statistics needed by the scheduler.

        Args:
            object_name: Object type key.

        Returns:
            Summary with mean, variance, and active backend.
        """

        state = self.get_state(object_name)
        return BeliefSummary(
            expected_duration=float(state["expected_duration"]),
            variance=max(MIN_VARIANCE, float(state["variance"])),
            method=state["method"],
        )

    def set_state(self, object_name: str, state: Mapping[str, Any]) -> None:
        """Persist a belief state for an object.

        Args:
            object_name: Object type key.
            state: New belief payload.
        """

        self._beliefs[object_name] = self._normalize_state(state)

    def ensure_method(self, object_name: str, method: BeliefMethod) -> dict[str, Any]:
        """Ensure that an object has the required backend-specific state.

        Args:
            object_name: Object type key.
            method: Requested backend.

        Returns:
            The updated and stored belief state.
        """

        state = self.get_state(object_name)
        state["method"] = method

        if method == "particle_filter" and "particles" not in state:
            particle_state = self._build_particle_state(
                mean=float(state["expected_duration"]),
                variance=float(state["variance"]),
                resample_count=int(state.get("resample_count", 0)),
            )
            state.update(particle_state)

        self.set_state(object_name, state)
        return self.get_state(object_name)

    def ensure_method_for_all(self, method: BeliefMethod) -> None:
        """Prepare every known object for a selected backend.

        Args:
            method: Requested backend.
        """

        for object_name in list(self._beliefs.keys()):
            self.ensure_method(object_name, method)

    def persist(self, output_path: Optional[Path] = None) -> None:
        """Write the current belief store to disk.

        Args:
            output_path: Optional override path for the persisted JSON file.
        """

        path = output_path or (AGENT_KNOWLEDGE_PATH / "bayesian_estimate.json")
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(self.as_dict(), file_obj, indent=4)

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Return a deep-serializable copy of the store."""

        return {
            object_name: self._copy_state(state)
            for object_name, state in self._beliefs.items()
        }

    def _default_state(self) -> dict[str, Any]:
        """Create the default Gaussian summary."""

        return {
            "expected_duration": float(INIT_PRIOR_MEAN),
            "variance": float(INIT_PRIOR_VARIANCE),
            "method": "bayesian",
        }

    def _normalize_state(self, raw_state: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize an external belief payload.

        Args:
            raw_state: Arbitrary mapping to normalize.

        Returns:
            Serializable belief state with stable defaults.
        """

        expected_duration = max(
            0.0,
            float(raw_state.get("expected_duration", INIT_PRIOR_MEAN)),
        )
        variance = max(MIN_VARIANCE, float(raw_state.get("variance", INIT_PRIOR_VARIANCE)))
        method: BeliefMethod = raw_state.get("method", "bayesian")
        normalized: dict[str, Any] = {
            "expected_duration": expected_duration,
            "variance": variance,
            "method": method,
        }

        if "particles" in raw_state:
            particles = np.asarray(raw_state["particles"], dtype=float)
            if particles.size:
                weights = np.asarray(
                    raw_state.get("weights", np.ones_like(particles)),
                    dtype=float,
                )
                weights = self._normalize_weights(weights)
                normalized.update(
                    {
                        "particles": particles.tolist(),
                        "weights": weights.tolist(),
                        "ess": float(raw_state.get("ess", self._compute_ess(weights))),
                        "resample_count": int(raw_state.get("resample_count", 0)),
                        "particle_distribution": raw_state.get(
                            "particle_distribution",
                            self._particle_distribution,
                        ),
                    }
                )

        return normalized

    def _build_particle_state(
        self,
        *,
        mean: float,
        variance: float,
        resample_count: int = 0,
    ) -> dict[str, Any]:
        """Create a particle approximation from Gaussian summary statistics.

        Args:
            mean: Prior expected duration.
            variance: Prior variance.
            resample_count: Existing resample counter.

        Returns:
            Particle-filter state that matches the summary.
        """

        particles = _sample_positive_duration(
            distribution=self._particle_distribution,
            mean=max(MIN_VARIANCE, mean),
            variance=max(MIN_VARIANCE, variance),
            sample_count=self._particle_count,
            rng=self._rng,
        )
        weights = np.ones(self._particle_count, dtype=float) / float(self._particle_count)
        return {
            "particles": particles.tolist(),
            "weights": weights.tolist(),
            "ess": float(self._compute_ess(weights)),
            "resample_count": resample_count,
            "particle_distribution": self._particle_distribution,
        }

    @staticmethod
    def _copy_state(state: Mapping[str, Any]) -> dict[str, Any]:
        """Return a JSON-safe deep-ish copy of a belief state.

        Args:
            state: Stored belief state.

        Returns:
            Copied belief state.
        """

        copied: dict[str, Any] = {}
        for key, value in state.items():
            if isinstance(value, list):
                copied[key] = list(value)
            else:
                copied[key] = value
        return copied

    @staticmethod
    def _normalize_weights(weights: np.ndarray) -> np.ndarray:
        """Normalize a particle weight vector safely.

        Args:
            weights: Raw weight vector.

        Returns:
            Normalized weights.
        """

        total_weight = float(np.sum(weights))
        if total_weight <= 0.0:
            return np.ones_like(weights, dtype=float) / float(len(weights))
        return weights / total_weight

    @staticmethod
    def _compute_ess(weights: np.ndarray) -> float:
        """Compute effective sample size.

        Args:
            weights: Normalized particle weights.

        Returns:
            Effective sample size.
        """

        return 1.0 / float(np.sum(np.square(weights)))


class BayesianMonitoringPolicy:
    """Compute trigger times from a Gaussian quantile."""

    def __init__(
        self,
        belief_store: BeliefStore,
        *,
        threshold_probability: float = BAYESIAN_THRESHOLD_PROBABILITY,
    ) -> None:
        """Initialize the Bayesian trigger policy.

        Args:
            belief_store: Shared belief store for summary access.
            threshold_probability: Quantile threshold for trigger timing.
        """

        self.method: BeliefMethod = "bayesian"
        self._belief_store = belief_store
        self._threshold_probability = threshold_probability

    def compute_trigger_time(self, context: MonitoringTriggerContext) -> float:
        """Compute the trigger from Gaussian mean and variance.

        Args:
            context: Trigger inputs.

        Returns:
            Absolute trigger time.
        """

        z_score = float(norm.ppf(self._threshold_probability))
        sigma = math.sqrt(max(MIN_VARIANCE, context.variance))
        return context.critical_start_end_time + context.mean_duration + (sigma * z_score)


class ParticleFilterMonitoringPolicy:
    """Compute trigger times from an empirical particle quantile."""

    def __init__(
        self,
        belief_store: BeliefStore,
        *,
        threshold_probability: float = BAYESIAN_THRESHOLD_PROBABILITY,
    ) -> None:
        """Initialize the particle-filter trigger policy.

        Args:
            belief_store: Shared belief store for particle access.
            threshold_probability: Quantile threshold for trigger timing.
        """

        self.method: BeliefMethod = "particle_filter"
        self._belief_store = belief_store
        self._threshold_probability = threshold_probability

    def compute_trigger_time(self, context: MonitoringTriggerContext) -> float:
        """Compute the trigger from a weighted particle quantile.

        Args:
            context: Trigger inputs.

        Returns:
            Absolute trigger time.
        """

        if context.object_name is None:
            return BayesianMonitoringPolicy(
                self._belief_store,
                threshold_probability=self._threshold_probability,
            ).compute_trigger_time(context)

        state = self._belief_store.ensure_method(context.object_name, self.method)
        particles = np.asarray(state["particles"], dtype=float)
        weights = np.asarray(state["weights"], dtype=float)
        duration_quantile = _weighted_quantile(
            particles,
            weights,
            self._threshold_probability,
        )
        log.debug(
            "[ParticleFilterMonitoringPolicy] object=%s quantile=%.3f "
            "selected_duration=%.2f min_particle=%.2f max_particle=%.2f "
            "ess=%.2f resample_count=%s",
            context.object_name,
            self._threshold_probability,
            duration_quantile,
            float(np.min(particles)) if particles.size else 0.0,
            float(np.max(particles)) if particles.size else 0.0,
            float(state.get("ess", BeliefStore._compute_ess(weights))),
            state.get("resample_count", 0),
        )
        return context.critical_start_end_time + duration_quantile


class BayesianBeliefUpdater:
    """Update beliefs using a Gaussian conjugate approximation."""

    def __init__(
        self,
        belief_store: BeliefStore,
        *,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        """Initialize the Bayesian updater.

        Args:
            belief_store: Shared belief store.
            rng: Optional random generator for deterministic tests.
        """

        self.method: BeliefMethod = "bayesian"
        self._belief_store = belief_store
        self._rng = rng or np.random.default_rng()

    def update(self, context: BeliefUpdateContext) -> BeliefUpdateResult:
        """Update Gaussian summary statistics from a synthetic observation.

        Args:
            context: Posterior update inputs.

        Returns:
            Updated posterior result.
        """

        observation, likelihood_variance = _sample_observation(
            gt_interval=context.gt_interval,
            prior_mean=context.prior_mean,
            elapsed_interval=context.elapsed_interval,
            rng=self._rng,
        )
        posterior_mean = (
            (context.prior_variance * observation)
            + (likelihood_variance * context.prior_mean)
        ) / (likelihood_variance + context.prior_variance)
        posterior_variance = max(
            MIN_VARIANCE,
            (likelihood_variance * context.prior_variance)
            / (likelihood_variance + context.prior_variance),
        )

        belief_state = {
            "expected_duration": posterior_mean,
            "variance": posterior_variance,
            "method": self.method,
        }
        self._belief_store.set_state(context.object_name, belief_state)
        return BeliefUpdateResult(
            posterior_mean=posterior_mean,
            posterior_variance=posterior_variance,
            method=self.method,
            belief_state=belief_state,
            diagnostics={
                "observation": observation,
                "likelihood_variance": likelihood_variance,
            },
        )


class ParticleFilterBeliefUpdater:
    """Update beliefs with a simple bootstrap particle filter."""

    def __init__(
        self,
        belief_store: BeliefStore,
        *,
        resample_threshold: float = 0.5,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        """Initialize the particle-filter updater.

        Args:
            belief_store: Shared belief store.
            resample_threshold: ESS threshold ratio for resampling.
            rng: Optional random generator for deterministic tests.
        """

        self.method: BeliefMethod = "particle_filter"
        self._belief_store = belief_store
        self._resample_threshold = resample_threshold
        self._rng = rng or np.random.default_rng()

    def update(self, context: BeliefUpdateContext) -> BeliefUpdateResult:
        """Update particles using the current synthetic likelihood model.

        Args:
            context: Posterior update inputs.

        Returns:
            Updated posterior result.
        """

        state = self._belief_store.ensure_method(context.object_name, self.method)
        particles = np.asarray(state["particles"], dtype=float)
        weights = np.asarray(state["weights"], dtype=float)
        observation, likelihood_variance = _sample_observation(
            gt_interval=context.gt_interval,
            prior_mean=context.prior_mean,
            elapsed_interval=context.elapsed_interval,
            rng=self._rng,
        )

        likelihood = norm.pdf(
            observation,
            loc=particles,
            scale=math.sqrt(max(MIN_VARIANCE, likelihood_variance)),
        )
        updated_weights = BeliefStore._normalize_weights(weights * likelihood)
        ess_before_resample = BeliefStore._compute_ess(updated_weights)
        resample_count = int(state.get("resample_count", 0))
        resampled = False

        if ess_before_resample < self._resample_threshold * float(len(particles)):
            particles = _systematic_resample(
                particles=particles,
                weights=updated_weights,
                rng=self._rng,
            )
            updated_weights = np.ones_like(updated_weights) / float(len(updated_weights))
            resample_count += 1
            resampled = True

        posterior_mean = float(np.sum(updated_weights * particles))
        posterior_variance = float(
            np.sum(updated_weights * np.square(particles - posterior_mean))
        )
        posterior_variance = max(MIN_VARIANCE, posterior_variance)
        ess_after_resample = float(BeliefStore._compute_ess(updated_weights))

        log.debug(
            "[ParticleFilterBeliefUpdater] object=%s observation=%.2f "
            "prior_mean=%.2f prior_variance=%.2f posterior_mean=%.2f "
            "posterior_variance=%.2f ess_before=%.2f ess_after=%.2f "
            "resampled=%s resample_count=%d",
            context.object_name,
            observation,
            context.prior_mean,
            context.prior_variance,
            posterior_mean,
            posterior_variance,
            ess_before_resample,
            ess_after_resample,
            resampled,
            resample_count,
        )

        belief_state = {
            "expected_duration": posterior_mean,
            "variance": posterior_variance,
            "method": self.method,
            "particles": particles.tolist(),
            "weights": updated_weights.tolist(),
            "ess": ess_after_resample,
            "resample_count": resample_count,
        }
        self._belief_store.set_state(context.object_name, belief_state)
        return BeliefUpdateResult(
            posterior_mean=posterior_mean,
            posterior_variance=posterior_variance,
            method=self.method,
            belief_state=belief_state,
            diagnostics={
                "observation": observation,
                "likelihood_variance": likelihood_variance,
                "ess_before_resample": ess_before_resample,
                "ess_after_resample": ess_after_resample,
                "resampled": resampled,
                "resample_count": resample_count,
            },
        )


def create_monitoring_policy(
    method: BeliefMethod,
    belief_store: BeliefStore,
) -> MonitoringPolicy:
    """Create the scheduler-facing monitoring policy.

    Args:
        method: Requested backend.
        belief_store: Shared belief store.

    Returns:
        Configured monitoring policy.

    Raises:
        ValueError: If the backend is unsupported.
    """

    if method == "bayesian":
        return BayesianMonitoringPolicy(belief_store)
    if method == "particle_filter":
        return ParticleFilterMonitoringPolicy(belief_store)
    raise ValueError(f"Unsupported monitoring method: {method}")


def create_belief_updater(
    method: BeliefMethod,
    belief_store: BeliefStore,
) -> BeliefUpdater:
    """Create the runtime posterior updater.

    Args:
        method: Requested backend.
        belief_store: Shared belief store.

    Returns:
        Configured belief updater.

    Raises:
        ValueError: If the backend is unsupported.
    """

    if method == "bayesian":
        return BayesianBeliefUpdater(belief_store)
    if method == "particle_filter":
        return ParticleFilterBeliefUpdater(belief_store)
    raise ValueError(f"Unsupported belief update method: {method}")


def create_monitoring_backend(
    method: BeliefMethod,
    initial_beliefs: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    particle_distribution: GroundTruthDistribution = "gaussian",
) -> tuple[BeliefStore, MonitoringPolicy, BeliefUpdater]:
    """Build a complete monitoring backend bundle.

    Args:
        method: Requested backend.
        initial_beliefs: Existing belief mapping from task initialization.
        particle_distribution: Distribution family used for PF particle initialization.

    Returns:
        Tuple of shared belief store, scheduler policy, and runtime updater.
    """

    log.info("Creating monitoring backend: %s", method)
    belief_store = BeliefStore(
        initial_beliefs,
        particle_distribution=particle_distribution,
    )
    belief_store.ensure_method_for_all(method)
    monitoring_policy = create_monitoring_policy(method, belief_store)
    belief_updater = create_belief_updater(method, belief_store)
    return belief_store, monitoring_policy, belief_updater


def create_ground_truth_store(
    base_truths: Optional[Mapping[str, float]] = None,
    *,
    distribution: GroundTruthDistribution = "constant",
    random_seed: int = 42,
) -> GroundTruthStore:
    """Create a reusable ground-truth sampler for a run.

    Args:
        base_truths: Baseline object-to-interval mapping.
        distribution: Distribution family used to sample latent durations.
        random_seed: Seed for deterministic sampling.

    Returns:
        Configured ground-truth store.
    """

    return GroundTruthStore(
        base_truths,
        config=GroundTruthConfig(
            distribution=distribution,
            random_seed=random_seed,
        ),
    )


def _sample_positive_duration(
    *,
    distribution: GroundTruthDistribution,
    mean: float,
    variance: float,
    sample_count: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample positive duration values from a selected distribution family.

    Args:
        distribution: Target distribution family.
        mean: Target first moment.
        variance: Target second central moment proxy.
        sample_count: Number of samples to generate.
        rng: Random generator used for sampling.

    Returns:
        Positive duration samples.
    """

    clipped_mean = max(MIN_VARIANCE, float(mean))
    clipped_variance = max(MIN_VARIANCE, float(variance))
    sample_size = max(1, int(sample_count))

    if distribution == "constant":
        samples = np.full(sample_size, clipped_mean, dtype=float)
    elif distribution == "gaussian":
        samples = rng.normal(
            loc=clipped_mean,
            scale=math.sqrt(clipped_variance),
            size=sample_size,
        )
    elif distribution == "lognormal":
        sigma_sq = math.log(1.0 + (clipped_variance / max(MIN_VARIANCE, clipped_mean**2)))
        sigma = math.sqrt(max(MIN_VARIANCE, sigma_sq))
        mu = math.log(clipped_mean) - (0.5 * sigma_sq)
        samples = rng.lognormal(mean=mu, sigma=sigma, size=sample_size)
    elif distribution == "gamma":
        shape = max(MIN_VARIANCE, (clipped_mean**2) / clipped_variance)
        scale = max(MIN_VARIANCE, clipped_variance / clipped_mean)
        samples = rng.gamma(shape=shape, scale=scale, size=sample_size)
    else:
        std = math.sqrt(clipped_variance)
        component_offsets = np.array([-0.75 * std, 0.75 * std], dtype=float)
        component_scales = np.array(
            [max(1.0, 0.45 * std), max(1.0, 0.55 * std)],
            dtype=float,
        )
        component_choices = rng.choice([0, 1], size=sample_size, p=[0.5, 0.5])
        samples = rng.normal(
            loc=clipped_mean + component_offsets[component_choices],
            scale=component_scales[component_choices],
        )

    return np.clip(np.asarray(samples, dtype=float), a_min=MIN_VARIANCE, a_max=None)


def _sample_observation(
    *,
    gt_interval: float,
    prior_mean: float,
    elapsed_interval: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Sample a synthetic observation shared by all backends.

    Args:
        gt_interval: Ground-truth interval.
        prior_mean: Current prior mean.
        elapsed_interval: Time elapsed since the critical interval started.
        rng: Random generator used for sampling.

    Returns:
        Sampled observation and likelihood variance.
    """

    likelihood_variance = max(
        MIN_VARIANCE,
        FACTOR_ALPHA * (prior_mean - elapsed_interval) ** 2,
    )
    observation = float(
        rng.normal(loc=gt_interval, scale=math.sqrt(likelihood_variance))
    )
    return observation, likelihood_variance


def _weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    """Compute a weighted empirical quantile.

    Args:
        values: Sample values.
        weights: Corresponding normalized weights.
        quantile: Target quantile in the closed interval [0, 1].

    Returns:
        Weighted empirical quantile.
    """

    if values.size == 0:
        return 0.0

    clipped_quantile = min(max(quantile, 0.0), 1.0)
    sort_indices = np.argsort(values)
    sorted_values = values[sort_indices]
    sorted_weights = BeliefStore._normalize_weights(weights[sort_indices])
    cumulative_weights = np.cumsum(sorted_weights)
    index = int(np.searchsorted(cumulative_weights, clipped_quantile, side="left"))
    index = min(index, len(sorted_values) - 1)
    return float(sorted_values[index])


def _systematic_resample(
    *,
    particles: np.ndarray,
    weights: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Perform systematic resampling for a weighted particle set.

    Args:
        particles: Particle values.
        weights: Normalized particle weights.
        rng: Random generator used for resampling.

    Returns:
        Resampled particles with uniform implicit weights.
    """

    particle_count = len(particles)
    if particle_count == 0:
        return particles

    positions = (rng.random() + np.arange(particle_count)) / float(particle_count)
    cumulative_sum = np.cumsum(BeliefStore._normalize_weights(weights))
    indices = np.searchsorted(cumulative_sum, positions, side="left")
    return particles[indices]
