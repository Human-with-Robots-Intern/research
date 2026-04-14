"""Tests for the scheduler-free belief robustness benchmark."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.core.monitoring import ObservationResult
from src.experiments.belief_robustness import (
    SHAPE_STRESS_GT_DISTRIBUTIONS,
    BeliefBenchmarkConfig,
    belief_benchmark_config_and_script_options_from_flat_mapping,
    build_reviewer10_bf_vs_pf_rows,
    build_reviewer10_main_table_rows,
    build_reviewer10_pf_likelihood_upgrade_rows,
    run_belief_robustness_benchmark,
    run_single_episode,
    sample_ground_truth_duration,
    sample_trigger_sequential_observation_sequence,
    save_belief_robustness_results,
)


def test_belief_robustness_benchmark_returns_paired_summary_rows() -> None:
    """Both methods should see the same GT episodes inside each benchmark cell."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=4,
        gt_mean_multipliers=(1.0,),
        observation_families=("gaussian",),
        random_seed=7,
        write_episode_rows=False,
    )

    results = run_belief_robustness_benchmark(config)

    summary_rows = results["summary_rows"]
    assert len(summary_rows) == len(SHAPE_STRESS_GT_DISTRIBUTIONS) * 2

    rows_by_key = {
        (row["gt_distribution"], row["variant"]): row for row in summary_rows
    }
    for distribution in SHAPE_STRESS_GT_DISTRIBUTIONS:
        bayesian_row = rows_by_key[(distribution, "bayesian")]
        particle_row = rows_by_key[(distribution, "particle_filter[gaussian]")]
        assert bayesian_row["episode_count"] == 4
        assert particle_row["episode_count"] == 4
        assert bayesian_row["mean_gt_interval"] == particle_row["mean_gt_interval"]
        assert 0.0 <= bayesian_row["late_trigger_rate"] <= 1.0
        assert 0.0 <= particle_row["late_trigger_rate"] <= 1.0


def test_belief_robustness_results_are_written_to_json_and_csv(tmp_path) -> None:
    """Saving benchmark results should emit both summary and episode artifacts."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=2,
        gt_mean_multipliers=(1.0,),
        observation_families=("gaussian",),
        random_seed=11,
        write_episode_rows=True,
    )
    results = run_belief_robustness_benchmark(config)

    written_paths = save_belief_robustness_results(
        results,
        output_dir=tmp_path,
        write_episode_rows=True,
    )

    assert written_paths["summary_json"].exists()
    assert written_paths["summary_csv"].exists()
    assert written_paths["episode_csv"].exists()

    payload = json.loads(written_paths["summary_json"].read_text(encoding="utf-8"))
    assert "config" in payload
    assert len(payload["summary_rows"]) == len(SHAPE_STRESS_GT_DISTRIBUTIONS) * 2


def test_belief_robustness_benchmark_supports_multiple_pf_particle_families() -> None:
    """PF variants should be exported as separate summary rows."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=3,
        gt_mean_multipliers=(1.0,),
        observation_families=("gaussian",),
        particle_distributions=("gaussian", "mixture"),
        write_episode_rows=False,
    )

    results = run_belief_robustness_benchmark(config)
    variants = {row["variant"] for row in results["summary_rows"]}

    assert variants == {
        "bayesian",
        "particle_filter[gaussian]",
        "particle_filter[mixture]",
    }
    assert len(results["summary_rows"]) == len(SHAPE_STRESS_GT_DISTRIBUTIONS) * len(
        variants
    )


def test_reviewer10_extractors_build_expected_comparison_rows() -> None:
    """Reviewer-10 helper tables should extract the intended slices."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=2,
        gt_mean_multipliers=(0.6, 1.0, 1.4),
        observation_families=("gaussian", "same_as_gt"),
        particle_distributions=("gaussian",),
        write_episode_rows=False,
    )
    results = run_belief_robustness_benchmark(config)

    bf_vs_pf_rows = build_reviewer10_bf_vs_pf_rows(results["summary_rows"])
    pf_upgrade_rows = build_reviewer10_pf_likelihood_upgrade_rows(
        results["summary_rows"]
    )
    main_rows = build_reviewer10_main_table_rows(
        results["summary_rows"],
        observation_setting="shared_gaussian",
    )

    assert any(
        row["scenario"] == "gaussian_gt_shared_gaussian_observation"
        for row in bf_vs_pf_rows
    )
    assert any(
        row["scenario"] == "non_gaussian_gt_shared_gaussian_observation"
        for row in bf_vs_pf_rows
    )
    assert {row["gt_distribution"] for row in pf_upgrade_rows} == {
        "lognormal",
        "mixture",
    }
    assert {row["gt_mean_multiplier"] for row in bf_vs_pf_rows} == {0.6, 1.0, 1.4}
    assert all("mean_posterior_mean_abs_error" in row for row in main_rows)
    assert any(row["method_label"] == "Bayesian" for row in main_rows)
    assert any(row["method_label"] == "PF (Gaussian likelihood)" for row in main_rows)


def test_gt_mean_multiplier_propagates_into_episode_and_summary_rows() -> None:
    """GT mean shift should be preserved in both episode and summary outputs."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=2,
        gt_mean_multipliers=(0.6, 1.4),
        observation_families=("gaussian",),
        particle_distributions=("gaussian",),
        write_episode_rows=True,
    )

    results = run_belief_robustness_benchmark(config)
    episode_rows = results["episode_rows"]
    summary_rows = results["summary_rows"]

    assert {row["gt_mean_multiplier"] for row in episode_rows} == {0.6, 1.4}
    assert {row["gt_mean_multiplier"] for row in summary_rows} == {0.6, 1.4}
    assert {row["gt_target_mean"] for row in summary_rows} == {60.0, 140.0}


def test_calibration_error_matches_late_rate_minus_eta() -> None:
    """Summary calibration error should be abs(late_trigger_rate - eta)."""

    config = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=4,
        gt_mean_multipliers=(1.0,),
        observation_families=("gaussian",),
        particle_distributions=("gaussian",),
        write_episode_rows=False,
    )

    results = run_belief_robustness_benchmark(config)
    for row in results["summary_rows"]:
        assert row["calibration_error"] == abs(row["late_trigger_rate"] - row["eta"])


def test_trigger_sequential_observation_sequence_is_non_empty() -> None:
    """Sequential monitoring mode should emit at least one observation per backend."""

    rng = np.random.default_rng(0)
    bayes_obs = sample_trigger_sequential_observation_sequence(
        method="bayesian",
        observation_family="gaussian",
        gt_interval=100.0,
        prior_mean=100.0,
        prior_variance=400.0,
        eta=0.1,
        observation_alpha=0.1,
        object_name="BenchmarkObject",
        rng=rng,
        particle_count=32,
        particle_distribution=None,
        particle_likelihood_family=None,
        backend_seed=1,
        max_observations=10,
        horizon_multiplier=2.0,
    )
    pf_obs = sample_trigger_sequential_observation_sequence(
        method="particle_filter",
        observation_family="gaussian",
        gt_interval=100.0,
        prior_mean=100.0,
        prior_variance=400.0,
        eta=0.1,
        observation_alpha=0.1,
        object_name="BenchmarkObject",
        rng=np.random.default_rng(2),
        particle_count=32,
        particle_distribution="gaussian",
        particle_likelihood_family="gaussian",
        backend_seed=3,
        max_observations=10,
        horizon_multiplier=2.0,
    )
    assert bayes_obs
    assert pf_obs
    assert all(
        row.metadata.get("observation_schedule") == "trigger_sequential"
        for row in bayes_obs + pf_obs
    )


def test_pf_trigger_uses_pre_resample_quantile(monkeypatch) -> None:
    """PF trigger timing should use the weighted posterior before resampling."""

    def fake_sample_positive_duration(**_kwargs):
        return np.array([1.0, 100.0, 100.0, 100.0], dtype=float)

    def fake_systematic_resample(*, particles, weights, rng):
        _ = (particles, weights, rng)
        return np.array([100.0, 100.0, 100.0, 100.0], dtype=float)

    monkeypatch.setattr(
        "src.experiments.belief_robustness._sample_positive_duration",
        fake_sample_positive_duration,
    )
    monkeypatch.setattr(
        "src.experiments.belief_robustness._systematic_resample",
        fake_systematic_resample,
    )

    result = run_single_episode(
        method="particle_filter",
        gt_distribution="gaussian",
        gt_target_mean=100.0,
        gt_mean_multiplier=1.0,
        observation_setting="shared_gaussian",
        observation_family="gaussian",
        eta=0.1,
        episode_index=0,
        gt_interval=1.0,
        prior_mean=100.0,
        prior_variance=900.0,
        observations=[
            ObservationResult(
                observation=1.0,
                variance=1.0,
                metadata={"observation_model": "test"},
            )
        ],
        particle_count=4,
        particle_distribution="gaussian",
        particle_likelihood_family="gaussian",
        backend_seed=123,
    )

    assert math.isclose(result.trigger_time, 1.0, rel_tol=0.0, abs_tol=1e-6)


def test_shape_stress_sampling_profile_separates_mixture_modes() -> None:
    """Mixture GT modes should be at 0.35x and 1.65x mean — well separated."""

    rng = np.random.default_rng(123)
    samples = [
        sample_ground_truth_duration(
            distribution="mixture",
            base_duration=100.0,
            gt_variance=None,
            rng=rng,
        )
        for _ in range(200)
    ]

    assert min(samples) < 50.0
    assert max(samples) > 150.0
    assert 90.0 <= float(np.mean(samples)) <= 110.0


def test_shape_stress_sampling_profile_strengthens_lognormal_tail() -> None:
    """Lognormal GT (variance=10000) should have a visibly heavy right tail."""

    rng = np.random.default_rng(321)
    samples = sorted(
        sample_ground_truth_duration(
            distribution="lognormal",
            base_duration=100.0,
            gt_variance=None,
            rng=rng,
        )
        for _ in range(400)
    )

    q10 = samples[int(0.1 * (len(samples) - 1))]
    q90 = samples[int(0.9 * (len(samples) - 1))]
    assert q10 < 45.0
    assert q90 > 165.0


def test_belief_benchmark_flat_mapping_rejects_unknown_keys() -> None:
    """Unknown keys should raise ``ValueError`` with an explicit message."""

    with pytest.raises(ValueError, match="Unknown keys"):
        belief_benchmark_config_and_script_options_from_flat_mapping(
            {"episode_count": 1, "typo_field": 0}
        )


def test_belief_benchmark_flat_mapping_coerces_lists_and_script_options() -> None:
    """YAML-friendly lists should become tuples; script keys are split out."""

    cfg, script_opts = belief_benchmark_config_and_script_options_from_flat_mapping(
        {
            "methods": ["bayesian"],
            "episode_count": 5,
            "output_dir": "/tmp/belief_out",
            "reviewer10_comparison": True,
        }
    )
    assert cfg.methods == ("bayesian",)
    assert cfg.episode_count == 5
    assert script_opts == {
        "output_dir": "/tmp/belief_out",
        "reviewer10_comparison": True,
    }


def test_default_belief_shape_stress_yaml_loads() -> None:
    """Bundled default YAML should parse to the baseline ``BeliefBenchmarkConfig``."""

    repo = Path(__file__).resolve().parents[1]
    yaml_path = (
        repo
        / "scripts"
        / "offline"
        / "configs"
        / "belief_shape_stress_benchmark.yaml"
    )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    cfg, opts = belief_benchmark_config_and_script_options_from_flat_mapping(raw)
    assert cfg == BeliefBenchmarkConfig()
    assert opts == {}
