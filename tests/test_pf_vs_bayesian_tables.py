"""Tests for unified PF-vs-Bayesian LaTeX export helpers."""

from __future__ import annotations

from assets.result_analysis.pf_vs_bayesian_tables import (
    build_unified_rows,
    render_pf_vs_bayesian_table,
)


def test_build_unified_rows_distinguishes_pf_likelihood_variants() -> None:
    """Unified rows should keep PF Gaussian and GT-family likelihood variants separate."""

    summary = {
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 100.0,
                "makespan_gap": 0.0,
                "computation_time": 1.0,
            }
        },
        "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtlognormal__pdistgaussian": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 99.0,
                "makespan": 110.0,
                "makespan_gap": 10.0,
                "computation_time": 2.0,
            }
        },
        "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtlognormal__pdistgaussian__pliklognormal": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 108.0,
                "makespan_gap": 8.0,
                "computation_time": 2.5,
            }
        },
    }

    rows = build_unified_rows(summary, init_prior="CORRECT_ESTIMATE")

    labels = [(row.gt_distribution, row.method_label) for row in rows]
    assert ("gaussian", "Bayesian") in labels
    assert ("lognormal", "PF (Gaussian likelihood)") in labels
    assert ("lognormal", "PF (GT-family likelihood)") in labels


def test_render_pf_vs_bayesian_table_contains_unified_rows() -> None:
    """Rendered table should expose the unified PF-vs-Bayesian comparison layout."""

    summary = {
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtmixture": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 120.0,
                "makespan_gap": 20.0,
                "computation_time": 1.5,
            }
        },
        "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtmixture__pdistgaussian": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 98.0,
                "makespan": 125.0,
                "makespan_gap": 25.0,
                "computation_time": 2.0,
            }
        },
        "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtmixture__pdistgaussian__plikmixture": {
            "tasks_2_constraints_1": {
                "n_instructions": 10,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 118.0,
                "makespan_gap": 18.0,
                "computation_time": 2.3,
            }
        },
    }

    rendered = render_pf_vs_bayesian_table(summary, init_prior="CORRECT_ESTIMATE")
    table = rendered["pf_vs_bayesian_unified.tex"]

    assert "\\begin{table}[t]" in table
    assert "PF (Gaussian likelihood)" in table
    assert "PF (GT-family likelihood)" in table
    assert "\\label{tab:pf_vs_bayesian_unified_correct_estimate}" in table
