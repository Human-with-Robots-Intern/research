"""Tests for factor-alpha eta-sensitivity comparison table rendering."""

from __future__ import annotations

from assets.result_analysis.factor_alpha_eta_sensitivity_tables import (
    ETA_ORDER,
    INIT_PRIOR_ORDER,
    build_by_case_tex,
    build_overall_summary,
    build_overall_tex,
)


def _make_case(
    *,
    tsr: float,
    makespan_gap: float,
    computation_time: float,
    n_instructions: int = 50,
) -> dict[str, float]:
    return {
        "tsr": tsr,
        "makespan_gap": makespan_gap,
        "computation_time": computation_time,
        "n_instructions": n_instructions,
    }


def _make_summary(left_bias: float = 0.0) -> dict[str, dict[str, dict[str, float]]]:
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for prior_index, init_prior in enumerate(INIT_PRIOR_ORDER):
        for eta_index, eta in enumerate(ETA_ORDER):
            key = f"{init_prior}__bayesian__DEFAULT__w10_d10__eta{eta}"
            summary[key] = {
                "tasks_2_constraints_1": _make_case(
                    tsr=90.0 + left_bias + prior_index + eta_index,
                    makespan_gap=10.0 - left_bias + prior_index,
                    computation_time=1.0 - left_bias + eta_index * 0.1,
                ),
                "tasks_2_constraints_2": _make_case(
                    tsr=91.0 + left_bias + prior_index + eta_index,
                    makespan_gap=11.0 - left_bias + prior_index,
                    computation_time=1.1 - left_bias + eta_index * 0.1,
                ),
                "tasks_3_constraints_1": _make_case(
                    tsr=92.0 + left_bias + prior_index + eta_index,
                    makespan_gap=12.0 - left_bias + prior_index,
                    computation_time=1.2 - left_bias + eta_index * 0.1,
                ),
                "tasks_3_constraints_2": _make_case(
                    tsr=93.0 + left_bias + prior_index + eta_index,
                    makespan_gap=13.0 - left_bias + prior_index,
                    computation_time=1.3 - left_bias + eta_index * 0.1,
                ),
            }
    return summary


def _make_monitor_summary(
    left_bias_total: float = 0.0,
    left_bias_interval: float = 0.0,
) -> dict[str, dict[str, dict[str, float]]]:
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for prior_index, init_prior in enumerate(INIT_PRIOR_ORDER):
        for eta_index, eta in enumerate(ETA_ORDER):
            key = f"{init_prior}__bayesian__DEFAULT__w10_d10__eta{eta}"
            summary[key] = {
                "tasks_2_constraints_1": {
                    "avg_monitors": 2.0 - left_bias_total + 0.1 * prior_index + 0.01 * eta_index,
                    "avg_monitors_per_uncontrollable_target": 1.5 - left_bias_interval + 0.1 * prior_index + 0.01 * eta_index,
                },
                "tasks_2_constraints_2": {
                    "avg_monitors": 2.2 - left_bias_total + 0.1 * prior_index + 0.01 * eta_index,
                    "avg_monitors_per_uncontrollable_target": 1.7 - left_bias_interval + 0.1 * prior_index + 0.01 * eta_index,
                },
                "tasks_3_constraints_1": {
                    "avg_monitors": 2.4 - left_bias_total + 0.1 * prior_index + 0.01 * eta_index,
                    "avg_monitors_per_uncontrollable_target": 1.9 - left_bias_interval + 0.1 * prior_index + 0.01 * eta_index,
                },
                "tasks_3_constraints_2": {
                    "avg_monitors": 2.6 - left_bias_total + 0.1 * prior_index + 0.01 * eta_index,
                    "avg_monitors_per_uncontrollable_target": 2.1 - left_bias_interval + 0.1 * prior_index + 0.01 * eta_index,
                },
            }
    return summary


def test_build_overall_summary_computes_weighted_means() -> None:
    summary = _make_summary()

    overall = build_overall_summary(summary)
    row = overall["CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.01"]

    assert row["tsr"] == 91.5
    assert row["makespan_gap"] == 11.5
    assert row["computation_time"] == 1.15


def test_build_tex_outputs_include_pairwise_bolding() -> None:
    left = _make_summary(left_bias=1.0)
    right = _make_summary(left_bias=0.0)
    left_monitors = _make_monitor_summary(left_bias_total=1.0, left_bias_interval=0.5)
    right_monitors = _make_monitor_summary(left_bias_total=0.0, left_bias_interval=0.0)

    overall_rendered = build_overall_tex(
        left,
        right,
        left_monitors,
        right_monitors,
        label_left=r"$\alpha{=}0.01$",
        label_right=r"$\alpha{=}0.001$",
    )
    by_case_rendered = build_by_case_tex(
        left,
        right,
        left_monitors,
        right_monitors,
        label_left=r"$\alpha{=}0.01$",
        label_right=r"$\alpha{=}0.001$",
    )

    assert r"\begin{table}[t]" in overall_rendered
    assert r"\multicolumn{2}{c}{\textbf{Avg. Mon. / Unctrl. Int.} ($\downarrow$)}" in overall_rendered
    assert r"\multicolumn{2}{c}{\textbf{Avg. Mon.} ($\downarrow$)}" in overall_rendered
    assert r"\multirow{4}{*}{\textbf{Correct}}" in overall_rendered
    assert r"{\boldmath $92.5$} & $91.5$" in overall_rendered
    assert r"{\boldmath $10.5$} & $11.5$" in overall_rendered
    assert r"{\boldmath $1.30$} & $1.80$" in overall_rendered
    assert r"{\boldmath $1.30$} & $2.30$" in overall_rendered
    assert r"\caption{Factor-alpha comparison under the eta-sensitivity suite " in overall_rendered

    assert r"\begin{table*}[t]" in by_case_rendered
    assert r"\resizebox{\linewidth}{!}{%" in by_case_rendered
    assert r"\multirow{16}{*}{\textbf{Correct}}" in by_case_rendered
    assert r"\multirow{4}{*}{$0.01$}" in by_case_rendered
    assert r"\textbf{T2C1}" in by_case_rendered
    assert r"{\boldmath $91.0$} & $90.0$" in by_case_rendered
    assert r"{\boldmath $9.0$} & $10.0$" in by_case_rendered
    assert r"{\boldmath $1.00$} & $1.50$" in by_case_rendered
    assert r"{\boldmath $1.00$} & $2.00$" in by_case_rendered
