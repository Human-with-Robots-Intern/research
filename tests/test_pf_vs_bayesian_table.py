"""Tests for the PF-vs-Bayesian LaTeX table exporter."""

from __future__ import annotations

from assets.result_analysis.pf_vs_bayesian_table import (
    build_tex,
    load_gap_plus_summary,
)


def test_load_gap_plus_summary_keeps_only_tcsr_valid_entries() -> None:
    """Gap+ should only average instructions whose saved TSR is exactly 1.0."""

    bayes_key = "UNDER_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian"
    pf_key = (
        "UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian"
    )
    raw = {
        "FloorPlan1": {
            "tasks_2_constraints_1": {
                "inst_a": {
                    "oracle": {},
                    "oracle_valid": True,
                    bayes_key: {
                        "tsr": 1.0,
                        "makespan_gap": 3.0,
                    },
                    pf_key: {
                        "tsr": 0.5,
                        "makespan_gap": 1.0,
                    },
                },
                "inst_b": {
                    "oracle": {},
                    "oracle_valid": True,
                    bayes_key: {
                        "tsr": 1.0,
                        "makespan_gap": -2.0,
                    },
                },
            }
        }
    }

    summary = load_gap_plus_summary(raw)

    assert summary[bayes_key]["tasks_2_constraints_1"] == {
        "gap_valid_plus": 1.5,
        "n_valid_instructions": 2,
    }
    assert pf_key not in summary


def test_build_tex_renders_compact_single_prior_table() -> None:
    """A single-prior run should collapse the table to GT-only rows."""

    bayes_key = "UNDER_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian"
    pf_key = (
        "UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian"
    )
    summary = {
        bayes_key: {
            "tasks_2_constraints_1": {
                "tsr": 95.0,
                "computation_time": 1.25,
                "n_instructions": 10,
            }
        },
        pf_key: {
            "tasks_2_constraints_1": {
                "tsr": 100.0,
                "computation_time": 2.5,
                "n_instructions": 10,
            }
        },
    }
    raw = {
        "FloorPlan1": {
            "tasks_2_constraints_1": {
                "inst_a": {
                    "oracle": {},
                    "oracle_valid": True,
                    bayes_key: {"tsr": 1.0, "makespan_gap": 4.0},
                    pf_key: {"tsr": 1.0, "makespan_gap": 1.0},
                }
            }
        }
    }

    tex = build_tex(summary, raw)

    assert r"\textbf{Init Prior}" not in tex
    assert r"\textbf{GT}" in tex
    assert r"\textbf{Bayes}" in tex
    assert r"\textbf{PF}" in tex
    assert r"\textbf{Gaussian}" in tex
    assert r"UNDER\_ESTIMATE prior regime" in tex
    assert r"{\boldmath $100.0$}" in tex
    assert r"{\boldmath $1.0$}" in tex
    assert r"{\boldmath $1.250$}" in tex
    assert r"\label{tab:pf_vs_bayesian_overall}" in tex


def test_build_tex_keeps_multi_prior_layout_when_multiple_priors_present() -> None:
    """Multiple priors should preserve the original grouped table layout."""

    summary = {
        "UNDER_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian": {
            "tasks_2_constraints_1": {
                "tsr": 95.0,
                "computation_time": 1.0,
                "n_instructions": 10,
            }
        },
        "UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian": {
            "tasks_2_constraints_1": {
                "tsr": 96.0,
                "computation_time": 1.2,
                "n_instructions": 10,
            }
        },
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian": {
            "tasks_2_constraints_1": {
                "tsr": 98.0,
                "computation_time": 0.9,
                "n_instructions": 10,
            }
        },
        "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian": {
            "tasks_2_constraints_1": {
                "tsr": 97.0,
                "computation_time": 1.1,
                "n_instructions": 10,
            }
        },
    }
    raw = {
        "FloorPlan1": {
            "tasks_2_constraints_1": {
                "inst_a": {
                    "oracle": {},
                    "oracle_valid": True,
                    "UNDER_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian": {
                        "tsr": 1.0,
                        "makespan_gap": 2.0,
                    },
                    "UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian": {
                        "tsr": 1.0,
                        "makespan_gap": 1.0,
                    },
                    "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian": {
                        "tsr": 1.0,
                        "makespan_gap": 1.5,
                    },
                    "CORRECT_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtgaussian": {
                        "tsr": 1.0,
                        "makespan_gap": 1.7,
                    },
                }
            }
        }
    }

    tex = build_tex(summary, raw)

    assert r"\textbf{Init Prior}" in tex
    assert r"\textbf{Under}" in tex
    assert r"\textbf{Correct}" in tex
    assert "for each prior-misspecification regime" in tex
