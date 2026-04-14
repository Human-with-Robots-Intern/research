"""Tests for factor-alpha scalability comparison table rendering."""

from __future__ import annotations

from assets.result_analysis.factor_alpha_scalability_table import build_tex


def _make_case(
    *,
    tsr: float,
    makespan_gap: float,
    computation_time: float,
) -> dict[str, float]:
    return {
        "tsr": tsr,
        "makespan_gap": makespan_gap,
        "computation_time": computation_time,
    }


def test_build_tex_includes_computation_time_columns() -> None:
    """The rendered table should include TCSR/gap columns and bold the better side."""

    left = {
        "CORRECT_ESTIMATE__edf": {
            "tasks_2_constraints_1": _make_case(
                tsr=100.0,
                makespan_gap=1.3,
                computation_time=0.111,
            ),
            "tasks_2_constraints_2": _make_case(
                tsr=100.0,
                makespan_gap=7.8,
                computation_time=0.222,
            ),
            "tasks_3_constraints_1": _make_case(
                tsr=100.0,
                makespan_gap=18.7,
                computation_time=0.333,
            ),
            "tasks_3_constraints_2": _make_case(
                tsr=100.0,
                makespan_gap=11.9,
                computation_time=0.444,
            ),
        }
    }
    right = {
        "CORRECT_ESTIMATE__edf": {
            "tasks_2_constraints_1": _make_case(
                tsr=99.0,
                makespan_gap=1.4,
                computation_time=0.555,
            ),
            "tasks_2_constraints_2": _make_case(
                tsr=99.0,
                makespan_gap=7.9,
                computation_time=0.666,
            ),
            "tasks_3_constraints_1": _make_case(
                tsr=99.0,
                makespan_gap=18.8,
                computation_time=0.777,
            ),
            "tasks_3_constraints_2": _make_case(
                tsr=99.0,
                makespan_gap=12.0,
                computation_time=0.888,
            ),
        }
    }

    for key in (
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w1_d1__eta0.1",
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w5_d5__eta0.1",
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1",
        "CORRECT_ESTIMATE__bayesian__DEFAULT__w20_d20__eta0.1",
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w1_d1",
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w5_d5",
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10",
        "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w20_d20",
    ):
        left[key] = left["CORRECT_ESTIMATE__edf"]
        right[key] = right["CORRECT_ESTIMATE__edf"]

    rendered = build_tex(left, right, label_left=r"$\alpha{=}0.01$", label_right=r"$\alpha{=}0.001$")

    assert r"\begin{table}[t]" in rendered
    assert r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}" in rendered
    assert r"\textbf{Gap} ($\downarrow$)" in rendered
    assert r"Comp. Time" not in rendered
    assert r"{\boldmath $100.0$} & $99.0$" in rendered
    assert r"{\boldmath $1.3$} & $1.4$" in rendered
    assert r"\caption{Factor-alpha comparison under the scalability suite " in rendered
