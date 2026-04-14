"""Build a polished side-by-side LaTeX table from two scalability summaries.

The rendered table compares two factor-alpha settings side by side for:
- TCSR (higher is better)
- makespan gap to oracle (lower is better)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_LEFT = (
    "assets/results/offline_exp_result/factor_alpha_001/"
    "analysis/scalability/offline_analysis_summary.json"
)
DEFAULT_RIGHT = (
    "assets/results/offline_exp_result/factor_alpha_0001/"
    "analysis/scalability/offline_analysis_summary.json"
)
DEFAULT_OUT = (
    "assets/results/offline_exp_result/factor_alpha_comparison/"
    "latex_tables/scalability_factor_alpha_001_vs_0001.tex"
)

KEY_ORDER: list[str] = [
    "CORRECT_ESTIMATE__edf",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w1_d1__eta0.1",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w5_d5__eta0.1",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w20_d20__eta0.1",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w1_d1",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w5_d5",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w20_d20",
]

ROW_LABEL: dict[str, str] = {
    "CORRECT_ESTIMATE__edf": r"tDAG+EDF",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w1_d1__eta0.1": r"Ours $W{=}1$",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w5_d5__eta0.1": r"Ours $W{=}5$",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1": r"Ours $W{=}10$",
    "CORRECT_ESTIMATE__bayesian__DEFAULT__w20_d20__eta0.1": r"Ours $W{=}20$",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w1_d1": r"Ours NM $W{=}1$",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w5_d5": r"Ours NM $W{=}5$",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10": r"Ours NM $W{=}10$",
    "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w20_d20": r"Ours NM $W{=}20$",
}

CASES: list[tuple[str, str]] = [
    ("tasks_2_constraints_1", "T2C1"),
    ("tasks_2_constraints_2", "T2C2"),
    ("tasks_3_constraints_1", "T3C1"),
    ("tasks_3_constraints_2", "T3C2"),
]


def _tex_num(x: float, nd: int = 1) -> str:
    return f"${x:.{nd}f}$"


def _pair(a: float, b: float, *, higher: bool, digits: int = 1) -> str:
    if abs(a - b) < 1e-9:
        return rf"{{\boldmath {_tex_num(a, digits)}}} & {{\boldmath {_tex_num(b, digits)}}}"
    if higher:
        better_left = a > b
    else:
        better_left = a < b
    if better_left:
        return rf"{{\boldmath {_tex_num(a, digits)}}} & {_tex_num(b, digits)}"
    return rf"{_tex_num(a, digits)} & {{\boldmath {_tex_num(b, digits)}}}"


def _build_tabular(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Return one ``tabular`` block with TCSR and oracle gap."""

    head = (
        r"\begin{tabular}{@{}llrrrr@{}}"
        "\n\\toprule\n"
        r"\multirow{2}{*}{\textbf{Method}} & \multirow{2}{*}{\textbf{Task}} & "
        r"\multicolumn{2}{c}{\textbf{TCSR} ($\uparrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Gap} ($\downarrow$)} \\"
        "\n"
        r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}"
        "\n"
        rf"& & \textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} \\"
        "\n\\midrule\n"
    )
    chunks: list[str] = []
    for index, key in enumerate(KEY_ORDER):
        for i, (case, short) in enumerate(CASES):
            xl, xr = left[key][case], right[key][case]
            prefix = (
                rf"\multirow{{4}}{{*}}{{\textbf{{{ROW_LABEL[key]}}}}}"
                if i == 0
                else ""
            )
            chunks.append(
                f"{prefix} & \\textbf{{{short}}} & "
                f"{_pair(xl['tsr'], xr['tsr'], higher=True, digits=1)} & "
                f"{_pair(xl['makespan_gap'], xr['makespan_gap'], higher=False, digits=1)}"
                " \\\\\n"
            )

        if index == 0 or index == 4:
            chunks.append("\\midrule\n")
        elif index != len(KEY_ORDER) - 1:
            chunks.append("\\addlinespace[2pt]\n")

    if chunks and chunks[-1] in {"\\midrule\n", "\\addlinespace[2pt]\n"}:
        chunks.pop()
    return head + "".join(chunks) + "\\bottomrule\n\\end{tabular}\n"


def build_tex(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Return a wrapped LaTeX table for the scalability factor-alpha comparison."""

    tabular = _build_tabular(
        left,
        right,
        label_left=label_left,
        label_right=label_right,
    )
    return (
        r"\begin{table}[t]" "\n"
        r"\centering" "\n"
        r"{\small" "\n"
        r"\setlength{\tabcolsep}{4.5pt}" "\n"
        r"\renewcommand{\arraystretch}{1.05}" "\n"
        + tabular
        + "}\n"
        r"\caption{Factor-alpha comparison under the scalability suite "
        r"(constant GT duration, CORRECT\_ESTIMATE prior, and $\eta=0.1$). "
        r"Higher TCSR is better, while lower oracle gap is better. "
        r"Bold marks the better alpha in each row pair.}"
        "\n"
        r"\label{tab:factor_alpha_scalability_001_vs_0001}"
        "\n"
        r"\end{table}"
        "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, default=PROJECT_ROOT / DEFAULT_LEFT)
    parser.add_argument("--right", type=Path, default=PROJECT_ROOT / DEFAULT_RIGHT)
    parser.add_argument("-o", "--output", type=Path, default=PROJECT_ROOT / DEFAULT_OUT)
    parser.add_argument("--label-left", default=r"$\alpha{=}0.01$")
    parser.add_argument("--label-right", default=r"$\alpha{=}0.001$")
    args = parser.parse_args()

    lo = json.loads(args.left.read_text())
    ro = json.loads(args.right.read_text())
    miss = [k for k in KEY_ORDER if k not in lo or k not in ro]
    if miss:
        raise SystemExit(f"Missing keys: {miss}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build_tex(lo, ro, label_left=args.label_left, label_right=args.label_right),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
