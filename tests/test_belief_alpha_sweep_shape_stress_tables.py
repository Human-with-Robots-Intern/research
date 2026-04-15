"""Tests for the combined alpha-sweep belief robustness table renderer."""

from __future__ import annotations

from assets.result_analysis.belief_alpha_sweep_shape_stress_tables import (
    build_alpha_sweep_rows,
    render_alpha_sweep_latex_table,
    render_alpha_sweep_markdown,
)


def _make_summary_row(
    *,
    gt_distribution: str,
    variant: str,
    late_trigger_rate: float,
    calibration_error: float,
    mean_posterior_mean_abs_error: float,
    mean_trigger_abs_error: float,
) -> dict[str, object]:
    return {
        "gt_distribution": gt_distribution,
        "gt_target_mean": 100.0,
        "gt_mean_multiplier": 1.0,
        "observation_setting": "same_as_gt",
        "observation_family": gt_distribution,
        "prior_config": "CORRECT_ESTIMATE",
        "eta": 0.1,
        "method": "bayesian" if variant == "bayesian" else "particle_filter",
        "variant": variant,
        "particle_distribution": None if variant == "bayesian" else "gaussian",
        "particle_likelihood_family": None,
        "episode_count": 200,
        "mean_gt_interval": 100.0,
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


def test_build_alpha_sweep_rows_keeps_gaussian_and_mixture_layout() -> None:
    """The combined table should omit redundant Gaussian GT-family PF rows."""

    summary_rows_by_alpha = {
        0.1: [
            _make_summary_row(
                gt_distribution="gaussian",
                variant="bayesian",
                late_trigger_rate=0.2,
                calibration_error=0.1,
                mean_posterior_mean_abs_error=2.0,
                mean_trigger_abs_error=3.0,
            ),
            _make_summary_row(
                gt_distribution="gaussian",
                variant="particle_filter[gaussian]",
                late_trigger_rate=0.3,
                calibration_error=0.2,
                mean_posterior_mean_abs_error=4.0,
                mean_trigger_abs_error=5.0,
            ),
            _make_summary_row(
                gt_distribution="mixture",
                variant="bayesian",
                late_trigger_rate=0.4,
                calibration_error=0.3,
                mean_posterior_mean_abs_error=6.0,
                mean_trigger_abs_error=7.0,
            ),
            _make_summary_row(
                gt_distribution="mixture",
                variant="particle_filter[gaussian]",
                late_trigger_rate=0.35,
                calibration_error=0.25,
                mean_posterior_mean_abs_error=5.0,
                mean_trigger_abs_error=6.0,
            ),
            _make_summary_row(
                gt_distribution="mixture",
                variant="particle_filter[gaussian;lik=mixture]",
                late_trigger_rate=0.25,
                calibration_error=0.15,
                mean_posterior_mean_abs_error=4.0,
                mean_trigger_abs_error=5.0,
            ),
        ]
    }

    rows = build_alpha_sweep_rows(
        summary_rows_by_alpha,
        gt_distributions=("gaussian", "mixture"),
    )

    assert len(rows) == 5
    assert [row["method_label"] for row in rows] == [
        "Bayesian",
        "PF (Gaussian)",
        "Bayesian",
        "PF (Gaussian)",
        "PF (GT-family)",
    ]


def test_build_alpha_sweep_rows_accepts_results_without_gt_family_variant() -> None:
    """New benchmark outputs should render with Bayesian and PF-only rows."""

    summary_rows_by_alpha = {
        0.01: [
            _make_summary_row(
                gt_distribution="lognormal",
                variant="bayesian",
                late_trigger_rate=0.2,
                calibration_error=0.1,
                mean_posterior_mean_abs_error=2.0,
                mean_trigger_abs_error=3.0,
            ),
            _make_summary_row(
                gt_distribution="lognormal",
                variant="particle_filter[gaussian]",
                late_trigger_rate=0.3,
                calibration_error=0.2,
                mean_posterior_mean_abs_error=4.0,
                mean_trigger_abs_error=5.0,
            ),
        ]
    }

    rows = build_alpha_sweep_rows(summary_rows_by_alpha, gt_distributions=("lognormal",))

    assert len(rows) == 2
    assert [row["method_label"] for row in rows] == [
        "Bayesian",
        "PF (Gaussian)",
    ]


def test_render_alpha_sweep_outputs_include_formulas_and_bold_minima() -> None:
    """Rendered LaTeX/Markdown should expose formulas and highlight best metrics."""

    rows = build_alpha_sweep_rows(
        {
            0.1: [
                _make_summary_row(
                    gt_distribution="gaussian",
                    variant="bayesian",
                    late_trigger_rate=0.2,
                    calibration_error=0.1,
                    mean_posterior_mean_abs_error=2.0,
                    mean_trigger_abs_error=3.0,
                ),
                _make_summary_row(
                    gt_distribution="gaussian",
                    variant="particle_filter[gaussian]",
                    late_trigger_rate=0.3,
                    calibration_error=0.2,
                    mean_posterior_mean_abs_error=4.0,
                    mean_trigger_abs_error=5.0,
                ),
                _make_summary_row(
                    gt_distribution="mixture",
                    variant="bayesian",
                    late_trigger_rate=0.4,
                    calibration_error=0.3,
                    mean_posterior_mean_abs_error=6.0,
                    mean_trigger_abs_error=7.0,
                ),
                _make_summary_row(
                    gt_distribution="mixture",
                    variant="particle_filter[gaussian]",
                    late_trigger_rate=0.35,
                    calibration_error=0.25,
                    mean_posterior_mean_abs_error=5.0,
                    mean_trigger_abs_error=6.0,
                ),
                _make_summary_row(
                    gt_distribution="mixture",
                    variant="particle_filter[gaussian;lik=mixture]",
                    late_trigger_rate=0.25,
                    calibration_error=0.15,
                    mean_posterior_mean_abs_error=4.0,
                    mean_trigger_abs_error=5.0,
                ),
                _make_summary_row(
                    gt_distribution="lognormal",
                    variant="bayesian",
                    late_trigger_rate=0.22,
                    calibration_error=0.12,
                    mean_posterior_mean_abs_error=3.5,
                    mean_trigger_abs_error=4.5,
                ),
                _make_summary_row(
                    gt_distribution="lognormal",
                    variant="particle_filter[gaussian]",
                    late_trigger_rate=0.28,
                    calibration_error=0.18,
                    mean_posterior_mean_abs_error=5.5,
                    mean_trigger_abs_error=6.5,
                ),
                _make_summary_row(
                    gt_distribution="lognormal",
                    variant="particle_filter[gaussian;lik=lognormal]",
                    late_trigger_rate=0.30,
                    calibration_error=0.20,
                    mean_posterior_mean_abs_error=7.5,
                    mean_trigger_abs_error=8.5,
                ),
            ]
        }
    )

    latex = render_alpha_sweep_latex_table(rows)
    markdown = render_alpha_sweep_markdown(rows)

    assert r"\textbf{0.200}" in latex
    assert "Trigger Time Error" in latex
    assert latex.index("Trigger Time Error") < latex.index("Posterior Mean Error")
    assert (
        r"v_{\mathrm{obs},i,k}=\max(\epsilon,\alpha(\hat{\mu}_{i,k-1}-t_{i,k})^2)"
        in latex
    )
    assert "PF with GT-family is identical to PF with Gaussian" in latex
    assert "Heavy-tail (Lognormal)" in latex
    assert r"0.5\mathcal{N}(35,15^2)+0.5\mathcal{N}(165,15^2)" in latex
    assert "**0.200**" in markdown
    assert (
        "| Alpha | GT | Method | Late | |Late-eta| | Trigger Time Error | Posterior Mean Error |"
        in markdown
    )
    assert "## Metric Definitions" in markdown
    assert r"$$\mathrm{Late}=\frac{1}{N}\sum_{i=1}^{N}\mathbf{1}" in markdown
    assert (
        r"$$\mathrm{TriggerTimeError}=\frac{1}{N}\sum_{i=1}^{N}\left|\hat{t}_i^{(\eta)}-T_i\right|$$"
        in markdown
    )
    assert "PF (GT-family)" in markdown
    assert "same observation-setting family" in markdown
