"""Tests for Overleaf table export helpers."""

from __future__ import annotations

from assets.result_analysis.overleaf_tables import (
    build_overall_rows,
    parse_setting_key,
    render_scalability_tables,
)


def test_parse_setting_key_extracts_scheduler_fields() -> None:
    """Complex bayesian keys should be parsed into structured fields."""

    parsed = parse_setting_key(
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1"
    )

    assert parsed.init_prior == "CORRECT_ESTIMATE"
    assert parsed.baseline_name == "bayesian"
    assert parsed.ablation_config == "DEFAULT"
    assert parsed.beam_width == 10
    assert parsed.beam_depth == 10
    assert parsed.eta == "0.1"


def test_build_overall_rows_computes_weighted_means() -> None:
    """Overall rows should be weighted by n_instructions across cases."""

    summary = {
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10": {
            "tasks_2_constraints_1": {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 160.0,
                "makespan_gap": 0.0,
                "computation_time": 1.0,
            },
            "tasks_2_constraints_2": {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 200.0,
                "makespan_gap": 10.0,
                "computation_time": 3.0,
            },
            "tasks_3_constraints_1": {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 180.0,
                "makespan_gap": 20.0,
                "computation_time": 5.0,
            },
            "tasks_3_constraints_2": {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 220.0,
                "makespan_gap": 30.0,
                "computation_time": 7.0,
            },
        }
    }

    rows = build_overall_rows(summary, init_prior="CORRECT_ESTIMATE")

    assert len(rows) == 1
    assert rows[0].makespan == 190.0
    assert rows[0].makespan_gap == 15.0
    assert rows[0].computation_time == 4.0


def test_render_scalability_tables_contains_overleaf_structure() -> None:
    """Rendered snippets should contain only the main no-monitoring table."""

    summary = {
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w1_d1__eta0.1": {
            case: {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 99.0,
                "makespan": 180.0,
                "makespan_gap": 10.0,
                "computation_time": 0.5,
            }
            for case in (
                "tasks_2_constraints_1",
                "tasks_2_constraints_2",
                "tasks_3_constraints_1",
                "tasks_3_constraints_2",
            )
        },
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10": {
            case: {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 175.0,
                "makespan_gap": 5.0,
                "computation_time": 3.0,
            }
            for case in (
                "tasks_2_constraints_1",
                "tasks_2_constraints_2",
                "tasks_3_constraints_1",
                "tasks_3_constraints_2",
            )
        },
        "CORRECT_ESTIMATE__edf": {
            case: {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 100.0,
                "makespan": 181.0,
                "makespan_gap": 9.0,
                "computation_time": 0.1,
            }
            for case in (
                "tasks_2_constraints_1",
                "tasks_2_constraints_2",
                "tasks_3_constraints_1",
                "tasks_3_constraints_2",
            )
        },
    }

    rendered = render_scalability_tables(summary)

    assert "\\begin{table}[t]" in rendered["scalability_overall.tex"]
    assert "\\label{tab:scalability_overall_correct_estimate}" in rendered["scalability_overall.tex"]
    assert "no-monitoring control setting" in rendered["scalability_overall.tex"]
    assert "Method & \\textbf{TCSR ($\\uparrow$)}" in rendered["scalability_overall.tex"]
    assert "Ours ($w1,d1$)" not in rendered["scalability_overall.tex"]
    assert "Ours w/o Mon. ($w10,d10$)" in rendered["scalability_overall.tex"]
    assert "\\underline{" in rendered["scalability_overall.tex"]
    assert "tab_scalability_overall_correct_estimate.tex" in rendered
    assert "scalability_default_by_case.tex" not in rendered
    assert "scalability_none_monitoring_by_case.tex" not in rendered


def test_render_scalability_tables_masks_makespan_when_tcsr_is_not_100() -> None:
    """Makespan and gap should be hidden when TCSR is below 100."""

    summary = {
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w1_d1": {
            case: {
                "n_instructions": 50,
                "sr": 100.0,
                "tsr": 99.0,
                "makespan": 180.0,
                "makespan_gap": 10.0,
                "computation_time": 0.5,
            }
            for case in (
                "tasks_2_constraints_1",
                "tasks_2_constraints_2",
                "tasks_3_constraints_1",
                "tasks_3_constraints_2",
            )
        }
    }

    rendered = render_scalability_tables(summary)

    assert "& -- & -- &" in rendered["scalability_overall.tex"]
    assert "180.0" not in rendered["scalability_overall.tex"]
