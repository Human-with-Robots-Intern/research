"""Render a beam-wise case table for the scalability summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SUMMARY = (
    "assets/results/offline_exp_result/offline_batch_scalability/"
    "analysis/scalability/offline_analysis_summary.json"
)
DEFAULT_OUT = (
    "assets/results/offline_exp_result/offline_batch_scalability/"
    "analysis/scalability/latex_tables/scalability_case_table.tex"
)

BEAMS: list[tuple[str, str]] = [
    ("w1_d1", "B=1"),
    ("w10_d10", "B=10"),
    ("w20_d20", "B=20"),
]

METHOD_SPECS: list[tuple[str, str, dict[str, str]]] = [
    (
        "edf",
        r"EDF",
        {
            "w1_d1": "CORRECT_ESTIMATE__edf",
            "w10_d10": "CORRECT_ESTIMATE__edf",
            "w20_d20": "CORRECT_ESTIMATE__edf",
        },
    ),
    (
        "ours",
        r"Ours",
        {
            "w1_d1": "CORRECT_ESTIMATE__bayesian__DEFAULT__w1_d1__eta0.1",
            "w5_d5": "CORRECT_ESTIMATE__bayesian__DEFAULT__w5_d5__eta0.1",
            "w10_d10": "CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1",
            "w20_d20": "CORRECT_ESTIMATE__bayesian__DEFAULT__w20_d20__eta0.1",
        },
    ),
    (
        "nm",
        r"Ours wo Mon.",
        {
            "w1_d1": "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w1_d1",
            "w5_d5": "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w5_d5",
            "w10_d10": "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w10_d10",
            "w20_d20": "CORRECT_ESTIMATE__bayesian__NONE_MONITORING__w20_d20",
        },
    ),
]

CASES: list[tuple[str, str]] = [
    ("tasks_2_constraints_1", "T2C1"),
    ("tasks_2_constraints_2", "T2C2"),
    ("tasks_3_constraints_1", "T3C1"),
    ("tasks_3_constraints_2", "T3C2"),
]


def _tex_num(x: float, nd: int = 1) -> str:
    return f"${x:.{nd}f}$"


def _fmt_value(value: float, *, digits: int, style: str = "") -> str:
    cell = _tex_num(value, digits)
    if style == "best":
        return rf"{{\boldmath {cell}}}"
    if style == "second":
        return rf"\underline{{{cell}}}"
    return cell


def _compute_highlight_styles(
    values: list[float],
    *,
    higher_is_better: bool,
    tolerance: float = 1e-9,
) -> list[str]:
    """Return cell styles (`best`, `second`, or ``) for one metric column."""

    if not values:
        return []

    unique_sorted = sorted(set(values), reverse=higher_is_better)
    best_value = unique_sorted[0]
    second_value = unique_sorted[1] if len(unique_sorted) > 1 else None
    styles: list[str] = []
    for value in values:
        if abs(value - best_value) <= tolerance:
            styles.append("best")
        elif second_value is not None and abs(value - second_value) <= tolerance:
            styles.append("second")
        else:
            styles.append("")
    return styles


def _build_highlight_map(
    summary: Mapping[str, Any],
    present_methods: list[tuple[str, str, dict[str, str]]],
) -> dict[tuple[str, str, str], dict[str, str]]:
    """Build per-case, per-beam metric highlight styles across methods."""

    metric_specs = [
        ("tsr", True),
        ("makespan_gap", False),
        ("computation_time", False),
    ]
    highlight_map: dict[tuple[str, str, str], dict[str, str]] = {}

    for case, _short in CASES:
        for beam_key, _beam_label in BEAMS:
            for metric_name, higher_is_better in metric_specs:
                summary_keys: list[str] = []
                values: list[float] = []
                for _method_id, _label, key_map in present_methods:
                    summary_key = key_map[beam_key]
                    metrics = summary.get(summary_key, {}).get(case)
                    if metrics is None:
                        continue
                    summary_keys.append(summary_key)
                    values.append(float(metrics[metric_name]))

                styles = _compute_highlight_styles(
                    values,
                    higher_is_better=higher_is_better,
                )
                highlight_map[(case, beam_key, metric_name)] = dict(
                    zip(summary_keys, styles)
                )

    return highlight_map


def _build_tabular(summary: Mapping[str, Any]) -> str:
    head = (
        r"\begin{tabular}{@{}llrrrrrrrrr@{}}"
        "\n\\toprule\n"
        r"\multirow{2}{*}{\textbf{Method}} & \multirow{2}{*}{\textbf{Task}} & "
        r"\multicolumn{3}{c}{\textbf{TCSR} ($\uparrow$)} & "
        r"\multicolumn{3}{c}{\textbf{Gap} ($\downarrow$)} & "
        r"\multicolumn{3}{c}{\textbf{CT} ($\downarrow$)} \\"
        "\n"
        r"\cmidrule(lr){3-5}\cmidrule(lr){6-8}\cmidrule(lr){9-11}"
        "\n"
        r"& & \textbf{B=1} & \textbf{B=10} & \textbf{B=20} "
        r"& \textbf{B=1} & \textbf{B=10} & \textbf{B=20} "
        r"& \textbf{B=1} & \textbf{B=10} & \textbf{B=20} \\"
        "\n\\midrule\n"
    )
    present_methods = [
        (method_id, label, key_map)
        for method_id, label, key_map in METHOD_SPECS
        if any(key in summary for key in key_map.values())
    ]
    if not present_methods:
        raise KeyError("No supported EDF/Ours/Ours wo Mon. keys found in summary.")

    highlight_map = _build_highlight_map(summary, present_methods)
    chunks: list[str] = []
    for method_index, (_method_id, label, key_map) in enumerate(present_methods):
        for case_index, (case, short) in enumerate(CASES):
            prefix = (
                rf"\multirow{{4}}{{*}}{{\textbf{{{label}}}}}" if case_index == 0 else ""
            )
            tsr_cells: list[str] = []
            gap_cells: list[str] = []
            ct_cells: list[str] = []
            for beam_key, _beam_label in BEAMS:
                summary_key = key_map[beam_key]
                metrics = summary.get(summary_key, {}).get(case)
                if metrics is None:
                    tsr_cells.append("--")
                    gap_cells.append("--")
                    ct_cells.append("--")
                    continue
                tsr_cells.append(
                    _fmt_value(
                        float(metrics["tsr"]),
                        digits=1,
                        style=highlight_map[(case, beam_key, "tsr")].get(
                            summary_key, ""
                        ),
                    )
                )
                gap_cells.append(
                    _fmt_value(
                        float(metrics["makespan_gap"]),
                        digits=1,
                        style=highlight_map[(case, beam_key, "makespan_gap")].get(
                            summary_key, ""
                        ),
                    )
                )
                ct_cells.append(
                    _fmt_value(
                        float(metrics["computation_time"]),
                        digits=3,
                        style=highlight_map[(case, beam_key, "computation_time")].get(
                            summary_key, ""
                        ),
                    )
                )
            chunks.append(
                f"{prefix} & \\textbf{{{short}}} & "
                + " & ".join(tsr_cells + gap_cells + ct_cells)
                + " \\\\\n"
            )

        if method_index == len(present_methods) - 1:
            continue
        chunks.append("\\midrule\n")

    if chunks and chunks[-1] in {"\\midrule\n", "\\addlinespace[2pt]\n"}:
        chunks.pop()
    return head + "".join(chunks) + "\\bottomrule\n\\end{tabular}\n"


def build_tex(summary: Mapping[str, Any]) -> str:
    tabular = _build_tabular(summary)
    return (
        r"\begin{table}[t]"
        "\n"
        r"\centering"
        "\n"
        r"{\small"
        "\n"
        r"\setlength{\tabcolsep}{3.5pt}"
        "\n"
        r"\renewcommand{\arraystretch}{1.05}"
        "\n" + tabular + "}\n"
        r"\caption{Scalability results under the constant-duration setting with "
        r"CORRECT\_ESTIMATE prior and $\eta=0.1$. Higher TCSR is better, while "
        r"lower oracle gap and computation time are better. Columns sweep beam "
        r"size $B \in \{1,10,20\}$.}"
        "\n"
        r"\label{tab:scalability_case_results}"
        "\n"
        r"\end{table}"
        "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_SUMMARY,
        help="Path to offline_analysis_summary.json.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_OUT,
        help="Output .tex path.",
    )
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_tex(summary), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
