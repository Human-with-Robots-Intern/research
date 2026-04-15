"""Scheduler-free Monte Carlo benchmark for belief-update robustness.

This module isolates the monitoring backend from the scheduler so we can compare
Bayesian and particle-filter trigger behavior under a **single** experimental
regime: the **shape-stress** ground-truth sampler (fixed mean,
amplified family-specific spread / mixture stress) over
``SHAPE_STRESS_GT_DISTRIBUTIONS``, with **sequential** monitoring observations
driven by ``BayesianMonitoringPolicy`` / ``ParticleFilterMonitoringPolicy`` in
``monitoring.py`` (no shared fixed-fraction replay, no generic GT profiles).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping

import numpy as np
from scipy.stats import norm

from src.core.monitoring import (
    BayesianMonitoringPolicy,
    BeliefMethod,
    BeliefStore,
    GroundTruthDistribution,
    MonitoringTriggerContext,
    ObservationResult,
    ParticleFilterMonitoringPolicy,
    _sample_positive_duration,
    _systematic_resample,
    _weighted_quantile,
    evaluate_duration_observation_likelihood,
)
from src.utils.config import constants

ObservationFamilySpec = str

SHAPE_STRESS_GT_DISTRIBUTIONS: tuple[GroundTruthDistribution, ...] = (
    "gaussian",
    "lognormal",
    "mixture",
)


@dataclass(frozen=True)
class BeliefBenchmarkConfig:
    """Describe a scheduler-free PF-vs-Bayesian Monte Carlo benchmark.

    Ground truth is always sampled with the shape-stress profile over
    ``SHAPE_STRESS_GT_DISTRIBUTIONS``. The prior mean stays fixed at
    ``base_duration`` (100 by default), while ``gt_mean_multipliers``
    move the ground-truth mean away from that anchor to create location
    misspecification on top of the GT shape mismatch. Observations use
    the sequential monitoring timeline (see module docstring).
    """

    methods: tuple[BeliefMethod, ...] = ("bayesian", "particle_filter")
    etas: tuple[float, ...] = (0.1,)
    max_sequential_observations: int = 20
    sequential_horizon_multiplier: float = 2.0
    episode_count: int = 200
    base_duration: float = 100.0
    gt_mean_multipliers: tuple[float, ...] = (1.0,)
    gt_variance: float | None = None
    prior_variance: float = constants.INIT_PRIOR_VARIANCE
    observation_alpha: float = constants.FACTOR_ALPHA
    observation_families: tuple[ObservationFamilySpec, ...] = (
        "gaussian",
        "same_as_gt",
    )
    particle_count: int = 1024
    particle_distributions: tuple[GroundTruthDistribution, ...] = ("gaussian",)
    object_name: str = "BenchmarkObject"
    random_seed: int = 42
    write_episode_rows: bool = True


BELIEF_BENCHMARK_SCRIPT_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "output_dir",
        "latex_export",
        "latex_dir",
        "observation_alphas",
    }
)

_BENCHMARK_LIST_LIKE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "methods",
        "etas",
        "gt_mean_multipliers",
        "observation_families",
        "particle_distributions",
    }
)


def belief_benchmark_config_and_script_options_from_flat_mapping(
    raw: Mapping[str, Any],
    *,
    base: BeliefBenchmarkConfig | None = None,
) -> tuple[BeliefBenchmarkConfig, dict[str, Any]]:
    """Split a flat mapping into a ``BeliefBenchmarkConfig`` and script-only options.

    Script-only keys (``output_dir``, ``latex_export``, ``latex_dir``,
    ``observation_alphas``) are returned in the second mapping and are not part
    of ``BeliefBenchmarkConfig``. List values for tuple-typed benchmark fields
    are coerced to tuples for YAML friendliness.

    Args:
        raw: Typically the top-level mapping from ``yaml.safe_load``.
        base: Optional baseline config; defaults to ``BeliefBenchmarkConfig()``.

    Returns:
        A pair ``(config, script_options)`` where ``script_options`` only contains
        keys that were present in ``raw`` among ``BELIEF_BENCHMARK_SCRIPT_OPTION_KEYS``.

    Raises:
        ValueError: If ``raw`` contains keys that are neither benchmark fields nor
            recognized script options.
    """

    field_names = {f.name for f in fields(BeliefBenchmarkConfig)}
    unknown = set(raw.keys()) - field_names - BELIEF_BENCHMARK_SCRIPT_OPTION_KEYS
    if unknown:
        raise ValueError(
            "Unknown keys in belief benchmark YAML/config: "
            f"{', '.join(sorted(unknown))}. "
            f"Allowed benchmark fields: {', '.join(sorted(field_names))}. "
            "Allowed script keys: "
            f"{', '.join(sorted(BELIEF_BENCHMARK_SCRIPT_OPTION_KEYS))}."
        )
    script_options = {
        key: raw[key]
        for key in BELIEF_BENCHMARK_SCRIPT_OPTION_KEYS
        if key in raw
    }
    if "observation_alphas" in script_options:
        oa = script_options["observation_alphas"]
        if isinstance(oa, (list, tuple)):
            script_options["observation_alphas"] = tuple(float(x) for x in oa)
        else:
            script_options["observation_alphas"] = (float(oa),)
    baseline = BeliefBenchmarkConfig() if base is None else base
    updates: dict[str, Any] = {}
    for name in field_names:
        if name not in raw:
            continue
        value = raw[name]
        if name in _BENCHMARK_LIST_LIKE_FIELD_NAMES and isinstance(value, list):
            value = tuple(value)
        updates[name] = value
    return replace(baseline, **updates), script_options


@dataclass(frozen=True)
class EpisodeResult:
    """Store scalar metrics for one backend on one Monte Carlo episode."""

    method: BeliefMethod
    variant: str
    gt_distribution: GroundTruthDistribution
    gt_target_mean: float
    gt_mean_multiplier: float
    prior_mean: float
    observation_setting: str
    observation_family: GroundTruthDistribution
    eta: float
    episode_index: int
    particle_distribution: str | None
    particle_likelihood_family: str | None
    gt_interval: float
    trigger_time: float
    slack: float
    late_trigger: bool
    posterior_mean: float
    posterior_variance: float
    posterior_mean_abs_error: float
    trigger_abs_error: float
    observation_count: int



def sample_ground_truth_duration(
    *,
    distribution: GroundTruthDistribution,
    base_duration: float,
    gt_variance: float | None,
    rng: np.random.Generator,
) -> float:
    """Sample one latent interval length using the shape-stress GT profile only."""

    return _sample_shape_stress_ground_truth_duration(
        distribution=distribution,
        base_duration=base_duration,
        gt_variance=gt_variance,
        rng=rng,
    )


def _sample_shape_stress_ground_truth_duration(
    *,
    distribution: GroundTruthDistribution,
    base_duration: float,
    gt_variance: float | None,
    rng: np.random.Generator,
) -> float:
    """Sample a shape-stress GT profile: prior mean is correct but GT shape is extreme.

    Variances are chosen so each family is clearly wider / heavier-tailed /
    more bimodal than the Gaussian prior with the same mean.

    * Gaussian  – variance = 900 (std = 30, matches prior std)
    * Lognormal – variance = 10 000 (std = 100, heavy right tail)
    * Mixture   – bimodal at 0.35 × mean and 1.65 × mean, component std = 0.15 × mean
    """

    clipped_mean = max(constants.MIN_VARIANCE, float(base_duration))
    if distribution == "constant":
        return clipped_mean

    if distribution == "gaussian":
        effective_variance = float(gt_variance) if gt_variance is not None else 900.0
        return float(
            _sample_positive_duration(
                distribution="gaussian",
                mean=clipped_mean,
                variance=effective_variance,
                sample_count=1,
                rng=rng,
            )[0]
        )

    if distribution in {"lognormal", "gamma"}:
        effective_variance = (
            max(float(gt_variance), 10000.0) if gt_variance is not None else 10000.0
        )
        return float(
            _sample_positive_duration(
                distribution=distribution,
                mean=clipped_mean,
                variance=effective_variance,
                sample_count=1,
                rng=rng,
            )[0]
        )

    left_mean = 0.35 * clipped_mean
    right_mean = 1.65 * clipped_mean
    component_std = max(5.0, 0.15 * clipped_mean)
    component_mean = float(rng.choice([left_mean, right_mean]))
    return float(
        max(
            constants.MIN_VARIANCE,
            rng.normal(loc=component_mean, scale=component_std),
        )
    )


def _sequential_min_elapsed_step(*, reference_scale: float) -> float:
    """Return a small mandatory advance between sequential monitoring times."""

    return max(constants.MIN_VARIANCE, 1e-4 * float(reference_scale))


def sample_trigger_sequential_observation_sequence(
    *,
    method: BeliefMethod,
    observation_family: GroundTruthDistribution,
    gt_interval: float,
    prior_mean: float,
    prior_variance: float,
    eta: float,
    observation_alpha: float,
    object_name: str,
    rng: np.random.Generator,
    particle_count: int,
    particle_distribution: GroundTruthDistribution | None,
    particle_likelihood_family: GroundTruthDistribution | None,
    backend_seed: int,
    max_observations: int,
    horizon_multiplier: float,
) -> list[ObservationResult]:
    """Sample observations on a backend-specific monitoring timeline.

    Uses ``BayesianMonitoringPolicy`` / ``ParticleFilterMonitoringPolicy`` from
    ``monitoring.py`` (with ``threshold_probability=eta``) to choose absolute
    elapsed times since critical-start end (taken as 0). At each time, the
    observation variance uses the same heteroscedastic rule as the synthetic
    monitoring model: variance scales with ``(belief_mean - elapsed)²``.

    Args:
        method: Inference backend whose trigger rule selects the timeline.
        observation_family: Latent-duration sampling family for the reading.
        gt_interval: Ground-truth interval duration for this episode.
        prior_mean: Initial Gaussian mean (Bayesian) or PF cloud center.
        prior_variance: Initial variance.
        eta: Quantile / threshold probability passed to monitoring policies.
        observation_alpha: Heteroscedastic observation variance scale.
        object_name: Object key required for PF particle quantile triggers.
        rng: RNG stream for observation draws (independent per backend).
        particle_count: PF particle count.
        particle_distribution: PF initialization family.
        particle_likelihood_family: PF observation likelihood family.
        backend_seed: Seed for PF resampling and particle initialization.
        max_observations: Hard cap on monitoring iterations.
        horizon_multiplier: Stops scheduling past ``gt_interval *`` this factor.

    Returns:
        Observation payloads in chronological order.
    """

    horizon = max(
        constants.MIN_VARIANCE,
        float(gt_interval) * float(horizon_multiplier),
    )
    min_step = _sequential_min_elapsed_step(
        reference_scale=max(abs(float(prior_mean)), abs(float(gt_interval)), 1.0)
    )
    last_elapsed = 0.0
    observations: list[ObservationResult] = []

    if method == "bayesian":
        dummy_store = BeliefStore()
        policy = BayesianMonitoringPolicy(
            dummy_store, threshold_probability=float(eta)
        )
        mean = float(prior_mean)
        var = float(prior_variance)
        for _ in range(int(max_observations)):
            abs_trigger = float(
                policy.compute_trigger_time(
                    MonitoringTriggerContext(
                        object_name=None,
                        critical_start_end_time=0.0,
                        mean_duration=mean,
                        variance=var,
                    )
                )
            )
            elapsed = max(min_step, abs_trigger, last_elapsed + min_step)
            elapsed = min(elapsed, horizon)
            variance = max(
                constants.MIN_VARIANCE,
                float(observation_alpha) * (mean - float(elapsed)) ** 2,
            )
            observation = float(
                _sample_positive_duration(
                    distribution=observation_family,
                    mean=float(gt_interval),
                    variance=float(variance),
                    sample_count=1,
                    rng=rng,
                )[0]
            )
            observations.append(
                ObservationResult(
                    observation=observation,
                    variance=variance,
                    metadata={
                        "observation_model": (
                            f"benchmark_trigger_sequential_{observation_family}"
                        ),
                        "observation_mean": float(gt_interval),
                        "elapsed_interval": float(elapsed),
                        "observation_family": observation_family,
                        "observation_schedule": "trigger_sequential",
                        "belief_backend": "bayesian",
                    },
                )
            )
            mean, var = _gaussian_conjugate_update(
                prior_mean=mean,
                prior_variance=var,
                observation=observation,
                likelihood_variance=variance,
            )
            last_elapsed = float(elapsed)
            if last_elapsed >= float(gt_interval):
                break
        return observations

    particle_family = particle_distribution or "gaussian"
    pf_rng = np.random.default_rng(int(backend_seed))
    store = BeliefStore(
        particle_count=int(particle_count),
        particle_distribution=particle_family,
        rng=pf_rng,
    )
    store.set_state(
        object_name,
        {
            "expected_duration": float(prior_mean),
            "variance": float(prior_variance),
            "method": "bayesian",
        },
    )
    store.ensure_method(object_name, "particle_filter")
    policy = ParticleFilterMonitoringPolicy(
        store, threshold_probability=float(eta)
    )
    resample_count = int(store.get_state(object_name).get("resample_count", 0))

    for _ in range(int(max_observations)):
        state = store.get_state(object_name)
        particles = np.asarray(state["particles"], dtype=float)
        weights = _normalize_weights(np.asarray(state["weights"], dtype=float))
        posterior_mean = float(np.sum(weights * particles))
        posterior_variance = max(
            constants.MIN_VARIANCE,
            float(np.sum(weights * np.square(particles - posterior_mean))),
        )
        abs_trigger = float(
            policy.compute_trigger_time(
                MonitoringTriggerContext(
                    object_name=object_name,
                    critical_start_end_time=0.0,
                    mean_duration=posterior_mean,
                    variance=posterior_variance,
                )
            )
        )
        elapsed = max(min_step, abs_trigger, last_elapsed + min_step)
        elapsed = min(elapsed, horizon)
        variance = max(
            constants.MIN_VARIANCE,
            float(observation_alpha)
            * (float(posterior_mean) - float(elapsed)) ** 2,
        )
        observation = float(
            _sample_positive_duration(
                distribution=observation_family,
                mean=float(gt_interval),
                variance=float(variance),
                sample_count=1,
                rng=rng,
            )[0]
        )
        observations.append(
            ObservationResult(
                observation=observation,
                variance=variance,
                metadata={
                    "observation_model": (
                        f"benchmark_trigger_sequential_{observation_family}"
                    ),
                    "observation_mean": float(gt_interval),
                    "elapsed_interval": float(elapsed),
                    "observation_family": observation_family,
                    "observation_schedule": "trigger_sequential",
                    "belief_backend": "particle_filter",
                },
            )
        )
        likelihood = evaluate_duration_observation_likelihood(
            observation=observation,
            hypotheses=particles,
            variance=float(variance),
            family=particle_likelihood_family or "gaussian",
        )
        weights = _normalize_weights(weights * likelihood)
        posterior_mean = float(np.sum(weights * particles))
        posterior_variance = max(
            constants.MIN_VARIANCE,
            float(np.sum(weights * np.square(particles - posterior_mean))),
        )
        ess_after_update = _effective_sample_size(weights)
        if ess_after_update < 0.5 * float(len(particles)):
            particles = _systematic_resample(
                particles=particles, weights=weights, rng=pf_rng
            )
            jitter_std = (
                math.sqrt(max(constants.MIN_VARIANCE, posterior_variance)) * 0.05
            )
            particles = np.clip(
                particles + pf_rng.normal(0.0, jitter_std, size=len(particles)),
                a_min=constants.MIN_VARIANCE,
                a_max=None,
            )
            weights = np.ones_like(weights) / float(len(weights))
            posterior_mean = float(np.sum(weights * particles))
            posterior_variance = max(
                constants.MIN_VARIANCE,
                float(np.sum(weights * np.square(particles - posterior_mean))),
            )
            resample_count += 1

        ess_stored = _effective_sample_size(weights)
        store.set_state(
            object_name,
            {
                "expected_duration": float(posterior_mean),
                "variance": float(posterior_variance),
                "method": "particle_filter",
                "particles": particles.tolist(),
                "weights": weights.tolist(),
                "ess": float(ess_stored),
                "resample_count": int(resample_count),
            },
        )
        last_elapsed = float(elapsed)
        if last_elapsed >= float(gt_interval):
            break

    return observations


def resolve_observation_family(
    *,
    gt_distribution: GroundTruthDistribution,
    observation_family_spec: ObservationFamilySpec,
) -> tuple[str, GroundTruthDistribution]:
    """Resolve an observation-family spec into a stable setting label and family."""

    if observation_family_spec == "same_as_gt":
        return "same_as_gt", gt_distribution
    observation_family = str(observation_family_spec)
    if observation_family == "gaussian":
        return "shared_gaussian", "gaussian"
    if observation_family not in {
        "constant",
        "gaussian",
        "lognormal",
        "gamma",
        "mixture",
    }:
        raise ValueError(
            f"Unsupported observation_family spec: {observation_family_spec}"
        )
    return f"shared_{observation_family}", observation_family  # pragma: no cover


def run_single_episode(
    *,
    method: BeliefMethod,
    gt_distribution: GroundTruthDistribution,
    gt_target_mean: float,
    gt_mean_multiplier: float,
    observation_setting: str,
    observation_family: GroundTruthDistribution,
    eta: float,
    episode_index: int,
    gt_interval: float,
    prior_mean: float,
    prior_variance: float,
    observations: list[ObservationResult],
    particle_count: int,
    particle_distribution: GroundTruthDistribution | None,
    particle_likelihood_family: GroundTruthDistribution | None,
    backend_seed: int,
) -> EpisodeResult:
    """Run one backend on one fixed latent duration and observation sequence."""

    rng = np.random.default_rng(backend_seed)
    if method == "bayesian":
        posterior_mean = float(prior_mean)
        posterior_variance = float(prior_variance)
        for observation_result in observations:
            posterior_mean, posterior_variance = _gaussian_conjugate_update(
                prior_mean=posterior_mean,
                prior_variance=posterior_variance,
                observation=observation_result.observation,
                likelihood_variance=observation_result.variance,
            )
        trigger_time = float(
            posterior_mean
            + math.sqrt(max(constants.MIN_VARIANCE, posterior_variance))
            * float(norm.ppf(float(eta)))
        )
    else:
        particle_family = particle_distribution or "gaussian"
        particles = _sample_positive_duration(
            distribution=particle_family,
            mean=float(prior_mean),
            variance=float(prior_variance),
            sample_count=int(particle_count),
            rng=rng,
        )
        weights = np.ones(int(particle_count), dtype=float) / float(particle_count)
        posterior_mean = float(prior_mean)
        posterior_variance = float(prior_variance)
        trigger_particles = particles.copy()
        trigger_weights = weights.copy()

        for observation_result in observations:
            likelihood = evaluate_duration_observation_likelihood(
                observation=observation_result.observation,
                hypotheses=particles,
                variance=float(observation_result.variance),
                family=particle_likelihood_family or "gaussian",
            )
            weights = _normalize_weights(weights * likelihood)
            # Use the final weighted posterior before any resampling/jitter for
            # trigger computation. This keeps eta-quantile timing tied to the
            # actual posterior mass rather than a resample-maintenance step.
            trigger_particles = particles.copy()
            trigger_weights = weights.copy()
            posterior_mean = float(np.sum(weights * particles))
            posterior_variance = max(
                constants.MIN_VARIANCE,
                float(np.sum(weights * np.square(particles - posterior_mean))),
            )
            ess = _effective_sample_size(weights)
            if ess < 0.5 * float(len(particles)):
                particles = _systematic_resample(
                    particles=particles,
                    weights=weights,
                    rng=rng,
                )
                jitter_std = (
                    math.sqrt(max(constants.MIN_VARIANCE, posterior_variance)) * 0.05
                )
                particles = np.clip(
                    particles + rng.normal(0.0, jitter_std, size=len(particles)),
                    a_min=constants.MIN_VARIANCE,
                    a_max=None,
                )
                weights = np.ones_like(weights) / float(len(weights))
                posterior_mean = float(np.sum(weights * particles))
                posterior_variance = max(
                    constants.MIN_VARIANCE,
                    float(np.sum(weights * np.square(particles - posterior_mean))),
                )

        trigger_time = float(
            _weighted_quantile(trigger_particles, trigger_weights, float(eta))
        )

    slack = float(gt_interval) - trigger_time
    return EpisodeResult(
        method=method,
        variant=_format_variant_label(
            method,
            particle_distribution,
            particle_likelihood_family,
        ),
        gt_distribution=gt_distribution,
        gt_target_mean=float(gt_target_mean),
        gt_mean_multiplier=float(gt_mean_multiplier),
        prior_mean=float(prior_mean),
        observation_setting=observation_setting,
        observation_family=observation_family,
        eta=float(eta),
        episode_index=int(episode_index),
        particle_distribution=particle_distribution,
        particle_likelihood_family=particle_likelihood_family,
        gt_interval=float(gt_interval),
        trigger_time=trigger_time,
        slack=slack,
        late_trigger=trigger_time > float(gt_interval),
        posterior_mean=float(posterior_mean),
        posterior_variance=float(posterior_variance),
        posterior_mean_abs_error=abs(float(posterior_mean) - float(gt_interval)),
        trigger_abs_error=abs(trigger_time - float(gt_interval)),
        observation_count=len(observations),
    )


def summarize_episode_rows(rows: list[EpisodeResult]) -> list[dict[str, Any]]:
    """Aggregate episode-level rows into compact per-cell summaries."""

    grouped: dict[
        tuple[str, float, str, str, float, str, str, str | None],
        list[EpisodeResult],
    ] = {}
    for row in rows:
        key = (
            row.gt_distribution,
            row.gt_mean_multiplier,
            row.observation_setting,
            row.observation_family,
            row.eta,
            row.method,
            row.variant,
            row.particle_likelihood_family,
        )
        grouped.setdefault(key, []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for key in sorted(grouped.keys()):
        (
            gt_distribution,
            gt_mean_multiplier,
            observation_setting,
            observation_family,
            eta,
            method,
            variant,
            particle_likelihood_family,
        ) = key
        group_rows = grouped[key]
        slacks = [row.slack for row in group_rows]
        late_trigger_rate = mean(1.0 if row.late_trigger else 0.0 for row in group_rows)
        summary_rows.append(
            {
                "gt_distribution": gt_distribution,
                "gt_target_mean": mean(row.gt_target_mean for row in group_rows),
                "gt_mean_multiplier": float(gt_mean_multiplier),
                "prior_config": _derive_prior_config(float(gt_mean_multiplier)),
                "prior_mean": mean(row.prior_mean for row in group_rows),
                "observation_setting": observation_setting,
                "observation_family": observation_family,
                "eta": float(eta),
                "method": method,
                "variant": variant,
                "particle_distribution": group_rows[0].particle_distribution,
                "particle_likelihood_family": particle_likelihood_family,
                "episode_count": len(group_rows),
                "mean_gt_interval": mean(row.gt_interval for row in group_rows),
                "late_trigger_rate": late_trigger_rate,
                "calibration_error": abs(late_trigger_rate - float(eta)),
                "safe_trigger_rate": mean(
                    0.0 if row.late_trigger else 1.0 for row in group_rows
                ),
                "mean_slack": mean(slacks),
                "median_slack": median(slacks),
                "mean_positive_slack": mean(max(0.0, row.slack) for row in group_rows),
                "mean_trigger_abs_error": mean(
                    row.trigger_abs_error for row in group_rows
                ),
                "mean_posterior_mean_abs_error": mean(
                    row.posterior_mean_abs_error for row in group_rows
                ),
                "mean_posterior_variance": mean(
                    row.posterior_variance for row in group_rows
                ),
            }
        )

    return summary_rows


def run_belief_robustness_benchmark(
    config: BeliefBenchmarkConfig,
) -> dict[str, Any]:
    """Run the scheduler-free Monte Carlo benchmark and return structured rows."""

    episode_rows: list[EpisodeResult] = []
    master_rng = np.random.default_rng(config.random_seed)

    for gt_distribution in SHAPE_STRESS_GT_DISTRIBUTIONS:
        for gt_mean_multiplier in config.gt_mean_multipliers:
            gt_target_mean = float(config.base_duration) * float(gt_mean_multiplier)
            prior_mean = float(config.base_duration)
            prior_variance = float(config.prior_variance)
            for observation_family_spec in config.observation_families:
                observation_setting, observation_family = (
                    resolve_observation_family(
                        gt_distribution=gt_distribution,
                        observation_family_spec=observation_family_spec,
                    )
                )
                for eta in config.etas:
                    for episode_index in range(config.episode_count):
                        gt_interval = sample_ground_truth_duration(
                            distribution=gt_distribution,
                            base_duration=gt_target_mean,
                            gt_variance=config.gt_variance,
                            rng=master_rng,
                        )

                        variant_index = 0
                        for method_index, method in enumerate(config.methods):
                            if method == "bayesian":
                                backend_seed = (
                                    int(config.random_seed)
                                    + (episode_index * 10000)
                                    + (method_index * 1000)
                                )
                                observations = (
                                    sample_trigger_sequential_observation_sequence(
                                        method=method,
                                        observation_family=observation_family,
                                        gt_interval=gt_interval,
                                        prior_mean=prior_mean,
                                        prior_variance=prior_variance,
                                        eta=float(eta),
                                        observation_alpha=config.observation_alpha,
                                        object_name=config.object_name,
                                        rng=np.random.default_rng(backend_seed),
                                        particle_count=config.particle_count,
                                        particle_distribution=None,
                                        particle_likelihood_family=None,
                                        backend_seed=backend_seed,
                                        max_observations=config.max_sequential_observations,
                                        horizon_multiplier=config.sequential_horizon_multiplier,
                                    )
                                )
                                episode_rows.append(
                                    run_single_episode(
                                        method=method,
                                        gt_distribution=gt_distribution,
                                        gt_target_mean=gt_target_mean,
                                        gt_mean_multiplier=float(
                                            gt_mean_multiplier
                                        ),
                                        observation_setting=observation_setting,
                                        observation_family=observation_family,
                                        eta=float(eta),
                                        episode_index=episode_index,
                                        gt_interval=gt_interval,
                                        prior_mean=prior_mean,
                                        prior_variance=prior_variance,
                                        observations=observations,
                                        particle_count=config.particle_count,
                                        particle_distribution=None,
                                        particle_likelihood_family=None,
                                        backend_seed=backend_seed,
                                    )
                                )
                                continue

                            particle_variants: list[
                                tuple[
                                    GroundTruthDistribution, GroundTruthDistribution
                                ]
                            ] = [
                                (particle_distribution, "gaussian")
                                for particle_distribution in config.particle_distributions
                            ]

                            for (
                                particle_distribution,
                                particle_likelihood_family,
                            ) in particle_variants:
                                backend_seed = (
                                    int(config.random_seed)
                                    + (episode_index * 10000)
                                    + (method_index * 1000)
                                    + variant_index
                                )
                                variant_index += 1
                                observations = (
                                    sample_trigger_sequential_observation_sequence(
                                        method=method,
                                        observation_family=observation_family,
                                        gt_interval=gt_interval,
                                        prior_mean=prior_mean,
                                        prior_variance=prior_variance,
                                        eta=float(eta),
                                        observation_alpha=config.observation_alpha,
                                        object_name=config.object_name,
                                        rng=np.random.default_rng(backend_seed),
                                        particle_count=config.particle_count,
                                        particle_distribution=particle_distribution,
                                        particle_likelihood_family=particle_likelihood_family,
                                        backend_seed=backend_seed,
                                        max_observations=config.max_sequential_observations,
                                        horizon_multiplier=config.sequential_horizon_multiplier,
                                    )
                                )
                                episode_rows.append(
                                    run_single_episode(
                                        method=method,
                                        gt_distribution=gt_distribution,
                                        gt_target_mean=gt_target_mean,
                                        gt_mean_multiplier=float(
                                            gt_mean_multiplier
                                        ),
                                        observation_setting=observation_setting,
                                        observation_family=observation_family,
                                        eta=float(eta),
                                        episode_index=episode_index,
                                        gt_interval=gt_interval,
                                        prior_mean=prior_mean,
                                        prior_variance=prior_variance,
                                        observations=observations,
                                        particle_count=config.particle_count,
                                        particle_distribution=particle_distribution,
                                        particle_likelihood_family=particle_likelihood_family,
                                        backend_seed=backend_seed,
                                    )
                                )

    summary_rows = summarize_episode_rows(episode_rows)
    return {
        "config": asdict(config),
        "summary_rows": summary_rows,
        "episode_rows": [asdict(row) for row in episode_rows],
    }


def save_belief_robustness_results(
    results: dict[str, Any],
    *,
    output_dir: Path,
    write_episode_rows: bool,
    summary_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Persist benchmark outputs as JSON and CSV files.

    Args:
        results: Must include ``config``, ``summary_rows``, and optionally
            ``episode_rows`` (list of dicts) when ``write_episode_rows`` is True.
        output_dir: Directory for ``belief_benchmark_summary.{json,csv}``.
        write_episode_rows: When True, also write ``belief_benchmark_episode_rows.csv``.
        summary_metadata: Optional extra top-level keys merged into the summary
            JSON (for example ``observation_alpha_sweep``).
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = output_dir / "belief_benchmark_summary.json"
    summary_csv_path = output_dir / "belief_benchmark_summary.csv"
    episode_csv_path = output_dir / "belief_benchmark_episode_rows.csv"

    summary_payload: dict[str, Any] = {
        "config": results["config"],
        "summary_rows": results["summary_rows"],
    }
    if summary_metadata:
        for key, value in dict(summary_metadata).items():
            if key in summary_payload:
                raise ValueError(
                    f"summary_metadata key {key!r} collides with reserved summary keys."
                )
            summary_payload[key] = value
    with summary_json_path.open("w", encoding="utf-8") as file_obj:
        json.dump(summary_payload, file_obj, indent=2)

    _write_csv(summary_csv_path, results["summary_rows"])
    written_paths = {
        "summary_json": summary_json_path,
        "summary_csv": summary_csv_path,
    }

    if write_episode_rows:
        _write_csv(episode_csv_path, results["episode_rows"])
        written_paths["episode_csv"] = episode_csv_path

    return written_paths


def build_belief_comparison_rows(
    summary_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract LaTeX-export comparison slices from benchmark summary rows."""

    extracted_rows: list[dict[str, Any]] = []
    for row in summary_rows:
        gt_distribution = row["gt_distribution"]
        observation_setting = row["observation_setting"]
        variant = row["variant"]
        if gt_distribution == "gaussian" and observation_setting == "shared_gaussian":
            if variant in {
                "bayesian",
                "particle_filter[gaussian]",
            }:
                extracted_rows.append(
                    {
                        "scenario": "gaussian_gt_shared_gaussian_observation",
                        "gt_distribution": gt_distribution,
                        "gt_target_mean": row["gt_target_mean"],
                        "gt_mean_multiplier": row["gt_mean_multiplier"],
                        "variant": variant,
                        "observation_setting": observation_setting,
                        "particle_likelihood_family": row["particle_likelihood_family"],
                        "episode_count": row["episode_count"],
                        "late_trigger_rate": row["late_trigger_rate"],
                        "calibration_error": row["calibration_error"],
                        "mean_slack": row["mean_slack"],
                        "mean_trigger_abs_error": row["mean_trigger_abs_error"],
                        "mean_posterior_mean_abs_error": row[
                            "mean_posterior_mean_abs_error"
                        ],
                    }
                )
        elif (
            gt_distribution in {"lognormal", "mixture"}
            and observation_setting == "shared_gaussian"
        ):
            if variant in {
                "bayesian",
                "particle_filter[gaussian]",
            }:
                extracted_rows.append(
                    {
                        "scenario": "non_gaussian_gt_shared_gaussian_observation",
                        "gt_distribution": gt_distribution,
                        "gt_target_mean": row["gt_target_mean"],
                        "gt_mean_multiplier": row["gt_mean_multiplier"],
                        "variant": variant,
                        "observation_setting": observation_setting,
                        "particle_likelihood_family": row["particle_likelihood_family"],
                        "episode_count": row["episode_count"],
                        "late_trigger_rate": row["late_trigger_rate"],
                        "calibration_error": row["calibration_error"],
                        "mean_slack": row["mean_slack"],
                        "mean_trigger_abs_error": row["mean_trigger_abs_error"],
                        "mean_posterior_mean_abs_error": row[
                            "mean_posterior_mean_abs_error"
                        ],
                    }
                )
        elif (
            gt_distribution in {"lognormal", "mixture"}
            and observation_setting == "same_as_gt"
            and variant
            in {
                "bayesian",
                "particle_filter[gaussian]",
                f"particle_filter[gaussian;lik={gt_distribution}]",
            }
        ):
            extracted_rows.append(
                {
                    "scenario": "non_gaussian_gt_same_as_gt_observation",
                    "gt_distribution": gt_distribution,
                    "gt_target_mean": row["gt_target_mean"],
                    "gt_mean_multiplier": row["gt_mean_multiplier"],
                    "variant": variant,
                    "observation_setting": observation_setting,
                    "particle_likelihood_family": row["particle_likelihood_family"],
                    "episode_count": row["episode_count"],
                    "late_trigger_rate": row["late_trigger_rate"],
                    "calibration_error": row["calibration_error"],
                    "mean_slack": row["mean_slack"],
                    "mean_trigger_abs_error": row["mean_trigger_abs_error"],
                    "mean_posterior_mean_abs_error": row[
                        "mean_posterior_mean_abs_error"
                    ],
                }
            )

    return extracted_rows


def build_belief_bf_vs_pf_rows(
    summary_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build paired BF-vs-PF rows for scenarios 1 and 2."""

    rows_by_key: dict[tuple, dict[str, Any]] = {}
    for row in summary_rows:
        key = (
            row["gt_distribution"],
            float(row["gt_mean_multiplier"]),
            row["observation_setting"],
            row["variant"],
            float(row["eta"]),
        )
        if key in rows_by_key:
            raise ValueError(
                f"Duplicate summary row for key {key}. Each "
                "(gt_distribution, gt_mean_multiplier, observation_setting, variant, eta) "
                "combination must appear at most once."
            )
        rows_by_key[key] = row

    paired_rows: list[dict[str, Any]] = []
    targets = [
        ("gaussian", "gaussian_gt_shared_gaussian_observation"),
        ("lognormal", "non_gaussian_gt_shared_gaussian_observation"),
        ("mixture", "non_gaussian_gt_shared_gaussian_observation"),
    ]
    gt_mean_multipliers = sorted(
        {
            float(row["gt_mean_multiplier"])
            for row in summary_rows
            if row["observation_setting"] == "shared_gaussian"
        }
    )
    etas = sorted(
        {
            float(row["eta"])
            for row in summary_rows
            if row["observation_setting"] == "shared_gaussian"
        }
    )
    for gt_distribution, scenario in targets:
        for gt_mean_multiplier in gt_mean_multipliers:
            for eta in etas:
                bayes = rows_by_key.get(
                    (gt_distribution, float(gt_mean_multiplier), "shared_gaussian", "bayesian", eta)
                )
                pf = rows_by_key.get(
                    (gt_distribution, float(gt_mean_multiplier), "shared_gaussian", "particle_filter[gaussian]", eta)
                )
                if bayes is None or pf is None:
                    continue
                paired_rows.append(
                    {
                        "scenario": scenario,
                        "gt_distribution": gt_distribution,
                        "gt_target_mean": bayes["gt_target_mean"],
                        "gt_mean_multiplier": gt_mean_multiplier,
                        "eta": eta,
                        "bayesian_late_trigger_rate": bayes["late_trigger_rate"],
                        "pf_late_trigger_rate": pf["late_trigger_rate"],
                        "bayesian_calibration_error": bayes["calibration_error"],
                        "pf_calibration_error": pf["calibration_error"],
                        "calibration_error_delta_pf_minus_bayesian": (
                            float(pf["calibration_error"])
                            - float(bayes["calibration_error"])
                        ),
                        "late_trigger_delta_pf_minus_bayesian": (
                            float(pf["late_trigger_rate"])
                            - float(bayes["late_trigger_rate"])
                        ),
                        "bayesian_mean_trigger_abs_error": bayes["mean_trigger_abs_error"],
                        "pf_mean_trigger_abs_error": pf["mean_trigger_abs_error"],
                        "trigger_abs_error_delta_pf_minus_bayesian": (
                            float(pf["mean_trigger_abs_error"])
                            - float(bayes["mean_trigger_abs_error"])
                        ),
                    }
                )
    return paired_rows


def build_belief_pf_likelihood_upgrade_rows(
    summary_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare PF with Gaussian likelihood vs GT-family likelihood."""

    rows_by_key: dict[tuple, dict[str, Any]] = {}
    for row in summary_rows:
        key = (
            row["gt_distribution"],
            float(row["gt_mean_multiplier"]),
            row["observation_setting"],
            row["variant"],
            float(row["eta"]),
        )
        if key in rows_by_key:
            raise ValueError(
                f"Duplicate summary row for key {key}. Each "
                "(gt_distribution, gt_mean_multiplier, observation_setting, variant, eta) "
                "combination must appear at most once."
            )
        rows_by_key[key] = row

    comparison_rows: list[dict[str, Any]] = []
    gt_mean_multipliers = sorted(
        {
            float(row["gt_mean_multiplier"])
            for row in summary_rows
            if row["observation_setting"] == "same_as_gt"
        }
    )
    etas = sorted(
        {
            float(row["eta"])
            for row in summary_rows
            if row["observation_setting"] == "same_as_gt"
        }
    )
    for gt_distribution in ("lognormal", "mixture"):
        for gt_mean_multiplier in gt_mean_multipliers:
            for eta in etas:
                pf_gaussian = rows_by_key.get(
                    (gt_distribution, float(gt_mean_multiplier), "same_as_gt", "particle_filter[gaussian]", eta)
                )
                pf_family = rows_by_key.get(
                    (gt_distribution, float(gt_mean_multiplier), "same_as_gt", f"particle_filter[gaussian;lik={gt_distribution}]", eta)
                )
                if pf_gaussian is None or pf_family is None:
                    continue
                comparison_rows.append(
                    {
                        "scenario": "pf_gaussian_vs_gt_family_likelihood",
                        "gt_distribution": gt_distribution,
                        "gt_target_mean": pf_gaussian["gt_target_mean"],
                        "gt_mean_multiplier": gt_mean_multiplier,
                        "eta": eta,
                        "pf_gaussian_likelihood_late_trigger_rate": pf_gaussian[
                            "late_trigger_rate"
                        ],
                        "pf_gt_family_likelihood_late_trigger_rate": pf_family[
                            "late_trigger_rate"
                        ],
                        "pf_gaussian_likelihood_calibration_error": pf_gaussian[
                            "calibration_error"
                        ],
                        "pf_gt_family_likelihood_calibration_error": pf_family[
                            "calibration_error"
                        ],
                        "calibration_error_delta_family_minus_gaussian": (
                            float(pf_family["calibration_error"])
                            - float(pf_gaussian["calibration_error"])
                        ),
                        "late_trigger_delta_family_minus_gaussian": (
                            float(pf_family["late_trigger_rate"])
                            - float(pf_gaussian["late_trigger_rate"])
                        ),
                        "pf_gaussian_likelihood_mean_trigger_abs_error": pf_gaussian[
                            "mean_trigger_abs_error"
                        ],
                        "pf_gt_family_likelihood_mean_trigger_abs_error": pf_family[
                            "mean_trigger_abs_error"
                        ],
                        "trigger_abs_error_delta_family_minus_gaussian": (
                            float(pf_family["mean_trigger_abs_error"])
                            - float(pf_gaussian["mean_trigger_abs_error"])
                        ),
                    }
                )
    return comparison_rows


def build_belief_main_table_rows(
    summary_rows: list[dict[str, Any]],
    *,
    observation_setting: str,
) -> list[dict[str, Any]]:
    """Aggregate rows for one main-table observation setting (mean over duplicate keys)."""

    grouped: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for row in summary_rows:
        if row["observation_setting"] != observation_setting:
            continue
        method_label = _resolve_method_label(row)
        if method_label is None:
            continue
        grouped.setdefault(
            (
                row["gt_distribution"],
                float(row["gt_mean_multiplier"]),
                method_label,
            ),
            [],
        ).append(row)

    main_rows: list[dict[str, Any]] = []
    for (gt_distribution, gt_mean_multiplier, method_label), rows in sorted(
        grouped.items()
    ):
        gt_target_mean = float(rows[0]["gt_target_mean"])
        main_rows.append(
            {
                "scenario": observation_setting,
                "gt_distribution": gt_distribution,
                "gt_mean_multiplier": gt_mean_multiplier,
                "gt_target_mean": gt_target_mean,
                "method_label": method_label,
                "late_trigger_rate": mean(
                    float(row["late_trigger_rate"]) for row in rows
                ),
                "calibration_error": mean(
                    float(row["calibration_error"]) for row in rows
                ),
                "mean_posterior_mean_abs_error": mean(
                    float(row["mean_posterior_mean_abs_error"]) for row in rows
                ),
                "mean_trigger_abs_error": mean(
                    float(row["mean_trigger_abs_error"]) for row in rows
                ),
                "n_prior_configs": len(rows),
            }
        )
    return main_rows


def build_belief_appendix_rows(
    summary_rows: list[dict[str, Any]],
    *,
    observation_setting: str,
) -> list[dict[str, Any]]:
    """Keep one appendix row per method for the given observation setting."""

    appendix_rows: list[dict[str, Any]] = []
    for row in summary_rows:
        if row["observation_setting"] != observation_setting:
            continue
        method_label = _resolve_method_label(row)
        if method_label is None:
            continue
        appendix_rows.append(
            {
                "scenario": observation_setting,
                "gt_distribution": row["gt_distribution"],
                "gt_mean_multiplier": row["gt_mean_multiplier"],
                "gt_target_mean": row["gt_target_mean"],
                "prior_config": str(
                    row.get("prior_config", "CORRECT_ESTIMATE"),
                ),
                "method_label": method_label,
                "late_trigger_rate": row["late_trigger_rate"],
                "calibration_error": row["calibration_error"],
                "mean_posterior_mean_abs_error": row["mean_posterior_mean_abs_error"],
                "mean_trigger_abs_error": row["mean_trigger_abs_error"],
            }
        )
    appendix_rows.sort(
        key=lambda row: (
            row["gt_distribution"],
            float(row["gt_mean_multiplier"]),
            row["method_label"],
        )
    )
    return appendix_rows


def save_belief_latex_export_csvs(
    results: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Path]:
    """Write comparison CSV files used by the LaTeX export pipeline."""

    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_rows = build_belief_comparison_rows(results["summary_rows"])
    bf_vs_pf_rows = build_belief_bf_vs_pf_rows(results["summary_rows"])
    pf_likelihood_rows = build_belief_pf_likelihood_upgrade_rows(
        results["summary_rows"]
    )
    main_shared_gaussian_rows = build_belief_main_table_rows(
        results["summary_rows"],
        observation_setting="shared_gaussian",
    )
    main_same_as_gt_rows = build_belief_main_table_rows(
        results["summary_rows"],
        observation_setting="same_as_gt",
    )
    appendix_shared_gaussian_rows = build_belief_appendix_rows(
        results["summary_rows"],
        observation_setting="shared_gaussian",
    )
    appendix_same_as_gt_rows = build_belief_appendix_rows(
        results["summary_rows"],
        observation_setting="same_as_gt",
    )

    comparison_csv = output_dir / "belief_latex_export_comparison_rows.csv"
    bf_vs_pf_csv = output_dir / "belief_latex_export_bf_vs_pf.csv"
    pf_likelihood_csv = output_dir / "belief_latex_export_pf_likelihood_upgrade.csv"
    main_shared_gaussian_csv = output_dir / "belief_latex_export_main_shared_gaussian.csv"
    main_same_as_gt_csv = output_dir / "belief_latex_export_main_same_as_gt.csv"
    appendix_shared_gaussian_csv = (
        output_dir / "belief_latex_export_appendix_shared_gaussian.csv"
    )
    appendix_same_as_gt_csv = output_dir / "belief_latex_export_appendix_same_as_gt.csv"

    _write_csv(comparison_csv, comparison_rows)
    _write_csv(bf_vs_pf_csv, bf_vs_pf_rows)
    _write_csv(pf_likelihood_csv, pf_likelihood_rows)
    _write_csv(main_shared_gaussian_csv, main_shared_gaussian_rows)
    _write_csv(main_same_as_gt_csv, main_same_as_gt_rows)
    _write_csv(appendix_shared_gaussian_csv, appendix_shared_gaussian_rows)
    _write_csv(appendix_same_as_gt_csv, appendix_same_as_gt_rows)

    return {
        "latex_export_comparison_csv": comparison_csv,
        "latex_export_bf_vs_pf_csv": bf_vs_pf_csv,
        "latex_export_pf_likelihood_upgrade_csv": pf_likelihood_csv,
        "latex_export_main_shared_gaussian_csv": main_shared_gaussian_csv,
        "latex_export_main_same_as_gt_csv": main_same_as_gt_csv,
        "latex_export_appendix_shared_gaussian_csv": appendix_shared_gaussian_csv,
        "latex_export_appendix_same_as_gt_csv": appendix_same_as_gt_csv,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a list of flat dictionaries as CSV."""

    if not rows:
        with path.open("w", encoding="utf-8", newline="") as file_obj:
            file_obj.write("")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_variant_label(
    method: BeliefMethod,
    particle_distribution: GroundTruthDistribution | None,
    particle_likelihood_family: GroundTruthDistribution | None,
) -> str:
    """Return a compact comparison label for one benchmark backend."""

    if method == "bayesian":
        return "bayesian"
    if particle_distribution is None:
        return "particle_filter"
    base_label = f"particle_filter[{particle_distribution}]"
    if particle_likelihood_family in {None, "gaussian"}:
        return base_label
    return f"{base_label[:-1]};lik={particle_likelihood_family}]"


def _resolve_method_label(row: dict[str, Any]) -> str | None:
    """Map one summary row to a human-readable method label for tables."""

    variant = str(row["variant"])
    if variant == "bayesian":
        return "Bayesian"
    if variant == "particle_filter[gaussian]":
        return "PF (Gaussian likelihood)"
    gt_distribution = str(row["gt_distribution"])
    if variant == f"particle_filter[gaussian;lik={gt_distribution}]":
        return "PF (GT-family likelihood)"
    return None


def _gaussian_conjugate_update(
    *,
    prior_mean: float,
    prior_variance: float,
    observation: float,
    likelihood_variance: float,
) -> tuple[float, float]:
    """Apply the Gaussian conjugate update used by the Bayesian baseline."""

    posterior_mean = (
        (prior_variance * observation) + (likelihood_variance * prior_mean)
    ) / (likelihood_variance + prior_variance)
    posterior_variance = max(
        constants.MIN_VARIANCE,
        (likelihood_variance * prior_variance) / (likelihood_variance + prior_variance),
    )
    return float(posterior_mean), float(posterior_variance)


def _derive_prior_config(gt_mean_multiplier: float) -> str:
    """Derive prior condition label from the GT mean multiplier.

    * multiplier > 1  → GT mean > prior mean → prior UNDER_ESTIMATEs
    * multiplier = 1  → GT mean = prior mean → CORRECT_ESTIMATE
    * multiplier < 1  → GT mean < prior mean → prior OVER_ESTIMATEs
    """
    if gt_mean_multiplier > 1.0 + 1e-9:
        return "UNDER_ESTIMATE"
    if gt_mean_multiplier < 1.0 - 1e-9:
        return "OVER_ESTIMATE"
    return "CORRECT_ESTIMATE"


def _normalize_weights(weights: np.ndarray) -> np.ndarray:
    """Normalize non-negative particle weights with a safe fallback."""

    clipped = np.clip(np.asarray(weights, dtype=float), a_min=0.0, a_max=None)
    total = float(np.sum(clipped))
    if total <= 0.0 or not np.isfinite(total):
        return np.ones_like(clipped) / float(len(clipped))
    return clipped / total


def _effective_sample_size(weights: np.ndarray) -> float:
    """Return the effective sample size for normalized weights."""

    normalized = _normalize_weights(weights)
    return float(1.0 / np.sum(np.square(normalized)))
