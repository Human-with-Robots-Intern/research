"""Tests for reviewer-10 belief robustness LaTeX table export."""

from __future__ import annotations

from assets.result_analysis.belief_robustness_tables import (
    render_belief_robustness_tables,
)


def _make_summary_row(
    *,
    gt_distribution: str,
    gt_target_mean: float,
    gt_mean_multiplier: float,
    observation_setting: str,
    prior_config: str,
    variant: str,
    particle_likelihood_family: str | None,
    late_trigger_rate: float,
    calibration_error: float,
    mean_posterior_mean_abs_error: float,
    mean_trigger_abs_error: float,
) -> dict[str, object]:
    return {
        "gt_distribution": gt_distribution,
        "gt_target_mean": gt_target_mean,
        "gt_mean_multiplier": gt_mean_multiplier,
        "observation_setting": observation_setting,
        "observation_family": "gaussian"
        if observation_setting == "shared_gaussian"
        else gt_distribution,
        "prior_config": prior_config,
        "eta": 0.1,
        "method": "bayesian" if variant == "bayesian" else "particle_filter",
        "variant": variant,
        "particle_distribution": None
        if variant == "bayesian"
        else "gaussian",
        "particle_likelihood_family": particle_likelihood_family,
        "episode_count": 20,
        "mean_gt_interval": gt_target_mean,
        "late_trigger_rate": late_trigger_rate,
        "calibration_error": calibration_error,
        "safe_trigger_rate": 1.0 - late_trigger_rate,
        "mean_slack": 1.0,
        "median_slack": 1.0,
        "mean_positive_slack": 1.0,
        "mean_trigger_abs_error": mean_trigger_abs_error,
        "mean_posterior_mean_abs_error": mean_posterior_mean_abs_error,
        "mean_posterior_variance": 1.0,
    }


def test_render_belief_robustness_tables_aggregates_across_priors() -> None:
    """Main tables should average reviewer metrics across prior configs."""

    summary_rows = [
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="UNDER_ESTIMATE",
            variant="bayesian",
            particle_likelihood_family=None,
            late_trigger_rate=0.1,
            calibration_error=0.0,
            mean_posterior_mean_abs_error=1.0,
            mean_trigger_abs_error=2.0,
        ),
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="CORRECT_ESTIMATE",
            variant="bayesian",
            particle_likelihood_family=None,
            late_trigger_rate=0.2,
            calibration_error=0.1,
            mean_posterior_mean_abs_error=2.0,
            mean_trigger_abs_error=3.0,
        ),
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="OVER_ESTIMATE",
            variant="bayesian",
            particle_likelihood_family=None,
            late_trigger_rate=0.3,
            calibration_error=0.2,
            mean_posterior_mean_abs_error=3.0,
            mean_trigger_abs_error=4.0,
        ),
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="UNDER_ESTIMATE",
            variant="particle_filter[gaussian]",
            particle_likelihood_family="gaussian",
            late_trigger_rate=0.4,
            calibration_error=0.3,
            mean_posterior_mean_abs_error=4.0,
            mean_trigger_abs_error=5.0,
        ),
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="CORRECT_ESTIMATE",
            variant="particle_filter[gaussian]",
            particle_likelihood_family="gaussian",
            late_trigger_rate=0.5,
            calibration_error=0.4,
            mean_posterior_mean_abs_error=5.0,
            mean_trigger_abs_error=6.0,
        ),
        _make_summary_row(
            gt_distribution="lognormal",
            gt_target_mean=100.0,
            gt_mean_multiplier=1.0,
            observation_setting="shared_gaussian",
            prior_config="OVER_ESTIMATE",
            variant="particle_filter[gaussian]",
            particle_likelihood_family="gaussian",
            late_trigger_rate=0.6,
            calibration_error=0.5,
            mean_posterior_mean_abs_error=6.0,
            mean_trigger_abs_error=7.0,
        ),
    ]

    rendered = render_belief_robustness_tables(summary_rows, eta=0.1)
    main_table = rendered["tab_belief_robustness_main_shared_gaussian.tex"]

    assert "Lognormal & 100 & Bayesian & 0.200 & 0.100 & 2.000 & 3.000" in main_table
    assert (
        "Lognormal & 100 & PF (Gaussian likelihood) & 0.500 & 0.400 & 5.000 & 6.000"
        in main_table
    )


def test_render_belief_robustness_tables_keeps_appendix_prior_breakdown() -> None:
    """Appendix tables should retain per-prior rows and PF GT-family entries."""

    summary_rows = [
        _make_summary_row(
            gt_distribution="mixture",
            gt_target_mean=120.0,
            gt_mean_multiplier=1.2,
            observation_setting="same_as_gt",
            prior_config="UNDER_ESTIMATE",
            variant="bayesian",
            particle_likelihood_family=None,
            late_trigger_rate=0.3,
            calibration_error=0.2,
            mean_posterior_mean_abs_error=5.0,
            mean_trigger_abs_error=8.0,
        ),
        _make_summary_row(
            gt_distribution="mixture",
            gt_target_mean=120.0,
            gt_mean_multiplier=1.2,
            observation_setting="same_as_gt",
            prior_config="UNDER_ESTIMATE",
            variant="particle_filter[gaussian]",
            particle_likelihood_family="gaussian",
            late_trigger_rate=0.25,
            calibration_error=0.15,
            mean_posterior_mean_abs_error=4.0,
            mean_trigger_abs_error=7.0,
        ),
        _make_summary_row(
            gt_distribution="mixture",
            gt_target_mean=120.0,
            gt_mean_multiplier=1.2,
            observation_setting="same_as_gt",
            prior_config="UNDER_ESTIMATE",
            variant="particle_filter[gaussian;lik=mixture]",
            particle_likelihood_family="mixture",
            late_trigger_rate=0.2,
            calibration_error=0.1,
            mean_posterior_mean_abs_error=3.0,
            mean_trigger_abs_error=6.0,
        ),
    ]

    rendered = render_belief_robustness_tables(summary_rows, eta=0.1)
    appendix_table = rendered["tab_belief_robustness_appendix_same_as_gt.tex"]

    assert "Mixture & 120 & Under & Bayesian" in appendix_table
    assert "Mixture & 120 & Under & PF (Gaussian likelihood)" in appendix_table
    assert "Mixture & 120 & Under & PF (GT-family likelihood)" in appendix_table
