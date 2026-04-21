"""Render a PF-vs-Bayesian LaTeX table from offline analysis outputs.

Outputs one weighted overall table:
- pf_vs_bayesian_overall.tex

Usage::

    python -m assets.result_analysis.pf_vs_bayesian_table
    python -m assets.result_analysis.pf_vs_bayesian_table \
        --summary path/to/offline_analysis_summary.json \
        --raw path/to/offline_comparison_raw.json \
        --output path/to/latex_tables/pf_vs_bayesian_overall.tex
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SUMMARY = (
    "assets/results/offline_exp_result/analysis/pf_vs_bayesian/"
    "offline_analysis_summary.json"
)
DEFAULT_RAW = (
    "assets/results/offline_exp_result/analysis/pf_vs_bayesian/"
    "offline_comparison_raw.json"
)
DEFAULT_OUTPUT = (
    "assets/results/offline_exp_result/analysis/pf_vs_bayesian/latex_tables/"
    "pf_vs_bayesian_overall.tex"
)

INIT_PRIOR_ORDER: list[str] = [
    "UNDER_ESTIMATE",
    "CORRECT_ESTIMATE",
    "OVER_ESTIMATE",
]
INIT_PRIOR_LABEL: dict[str, str] = {
    "UNDER_ESTIMATE": "Under",
    "CORRECT_ESTIMATE": "Correct",
    "OVER_ESTIMATE": "Over",
}

GT_ORDER: list[str] = [
    "gaussian",
    "lognormal",
    "mixture",
]
GT_LABEL: dict[str, str] = {
    "gaussian": "Gaussian",
    "lognormal": "Log-normal",
    "mixture": "Mixture",
}

EPSILON = 1e-9


def _setting_key(init_prior: str, method: str, gt_distribution: str) -> str:
    """Return the offline summary key for one PF-vs-Bayesian setting."""

    key = f"{init_prior}__{method}__DEFAULT__w10_d10__eta0.1"
    if method == "bayesian":
        if gt_distribution != "constant":
            key += f"__gt{gt_distribution}"
        return key

    key += f"__gt{gt_distribution}"
    if gt_distribution in {"lognormal", "mixture"}:
        key += f"__plik{gt_distribution}"
    return key


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return payload


def _weighted(case_metrics: dict[str, dict[str, Any]], field: str) -> float | None:
    """Aggregate one metric across cases using instruction counts when available."""

    if not case_metrics:
        return None

    weighted: list[tuple[int, float]] = []
    for metrics in case_metrics.values():
        value = metrics.get(field)
        if value is None:
            continue
        n_raw = metrics.get("n_instructions")
        if n_raw is None:
            weighted = []
            break
        n = int(n_raw)
        if n <= 0:
            weighted = []
            break
        weighted.append((n, float(value)))

    if weighted and len(weighted) == len(case_metrics):
        denom = sum(n for n, _value in weighted)
        if denom <= 0:
            return None
        return sum(n * value for n, value in weighted) / denom

    values = [
        float(metrics[field])
        for metrics in case_metrics.values()
        if metrics.get(field) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _weighted_optional(
    case_metrics: dict[str, dict[str, float | int | None]],
    field: str,
    *,
    weight_field: str,
) -> float | None:
    total_weight = 0
    total_value = 0.0
    for metrics in case_metrics.values():
        value = metrics.get(field)
        weight = metrics.get(weight_field)
        if value is None or weight is None:
            continue
        weight_int = int(weight)
        if weight_int <= 0:
            continue
        total_weight += weight_int
        total_value += weight_int * float(value)
    if total_weight <= 0:
        return None
    return total_value / total_weight


def load_gap_plus_summary(
    raw: dict[str, Any],
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Return clipped oracle gap averaged over TCSR-valid instructions only."""

    buckets: dict[str, dict[str, list[float]]] = {}

    for scene_data in raw.values():
        if not isinstance(scene_data, dict):
            continue
        for case_name, instructions in scene_data.items():
            if not isinstance(instructions, dict):
                continue
            for entry in instructions.values():
                if not isinstance(entry, dict):
                    continue
                for setting_key, metrics in entry.items():
                    if setting_key in {"oracle", "oracle_valid"}:
                        continue
                    if not isinstance(metrics, dict):
                        continue
                    tsr = metrics.get("tsr")
                    gap = metrics.get("makespan_gap")
                    if tsr is None or gap is None:
                        continue
                    if float(tsr) < 1.0 - EPSILON:
                        continue
                    buckets.setdefault(setting_key, {}).setdefault(
                        str(case_name), []
                    ).append(max(0.0, float(gap)))

    return {
        key: {
            case: {
                "gap_valid_plus": sum(values) / len(values),
                "n_valid_instructions": len(values),
            }
            for case, values in cases.items()
        }
        for key, cases in buckets.items()
    }


def _format_tex(
    value: float | None,
    digits: int,
    *,
    highlight: bool = False,
) -> str:
    if value is None:
        return "--"
    cell = f"${value:.{digits}f}$"
    if highlight:
        return rf"{{\boldmath {cell}}}"
    return cell


def _best_pair(
    left: float | None,
    right: float | None,
    *,
    higher_is_better: bool,
) -> tuple[bool, bool]:
    if left is None and right is None:
        return False, False
    if left is None:
        return False, True
    if right is None:
        return True, False
    if abs(left - right) <= EPSILON:
        return True, True
    if higher_is_better:
        return left > right, right > left
    return left < right, right < left


def _collect_rows(
    summary: dict[str, Any],
    gap_plus_summary: dict[str, dict[str, dict[str, float | int]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for init_prior in INIT_PRIOR_ORDER:
        for gt_distribution in GT_ORDER:
            bayes_key = _setting_key(init_prior, "bayesian", gt_distribution)
            pf_key = _setting_key(init_prior, "particle_filter", gt_distribution)
            bayes_cases = summary.get(bayes_key)
            pf_cases = summary.get(pf_key)
            if bayes_cases is None and pf_cases is None:
                continue

            bayes_tcsr = (
                _weighted(bayes_cases, "tsr")
                if isinstance(bayes_cases, dict)
                else None
            )
            pf_tcsr = (
                _weighted(pf_cases, "tsr")
                if isinstance(pf_cases, dict)
                else None
            )
            bayes_ct = (
                _weighted(bayes_cases, "computation_time")
                if isinstance(bayes_cases, dict)
                else None
            )
            pf_ct = (
                _weighted(pf_cases, "computation_time")
                if isinstance(pf_cases, dict)
                else None
            )
            bayes_gap = _weighted_optional(
                gap_plus_summary.get(bayes_key, {}),
                "gap_valid_plus",
                weight_field="n_valid_instructions",
            )
            pf_gap = _weighted_optional(
                gap_plus_summary.get(pf_key, {}),
                "gap_valid_plus",
                weight_field="n_valid_instructions",
            )

            rows.append(
                {
                    "init_prior": init_prior,
                    "gt_distribution": gt_distribution,
                    "bayes_tcsr": bayes_tcsr,
                    "pf_tcsr": pf_tcsr,
                    "bayes_gap": bayes_gap,
                    "pf_gap": pf_gap,
                    "bayes_ct": bayes_ct,
                    "pf_ct": pf_ct,
                }
            )

    return rows


def _present_priors(rows: list[dict[str, Any]]) -> list[str]:
    """Return priors that actually appear in the collected rows."""

    return [
        prior
        for prior in INIT_PRIOR_ORDER
        if any(row["init_prior"] == prior for row in rows)
    ]


def _build_caption_text(present_priors: list[str]) -> str:
    """Render a caption that stays natural for one or many prior regimes."""

    prior_phrase = "for each prior-misspecification regime"
    if len(present_priors) == 1:
        prior_phrase = (
            "under the "
            + present_priors[0].replace("_", r"\_")
            + " prior regime"
        )

    return (
        r"\caption{Particle-filter versus Gaussian-Bayesian belief updates "
        r"under non-Gaussian ground-truth duration families "
        r"($W{=}D{=}10$, DEFAULT planner, $\eta{=}0.1$). Metrics are "
        r"instruction-count-weighted across the four task-complexity cases and "
        r"five kitchen scenes "
        + prior_phrase
        + r". Gap$^{+}$ averages $\max(0,\mathrm{makespan}-\mathrm{oracle})$ "
        r"over instructions with TCSR\,=\,100\%; cells with no valid "
        r"instruction are shown as --. Bold marks the better method within "
        r"each row for the given metric.}"
    )


def _build_tabular(
    summary: dict[str, Any],
    gap_plus_summary: dict[str, dict[str, dict[str, float | int]]],
) -> str:
    rows = _collect_rows(summary, gap_plus_summary)
    if not rows:
        raise KeyError("No PF-vs-Bayesian keys found in summary.")

    present_priors = _present_priors(rows)
    single_prior = len(present_priors) == 1

    lines: list[str] = []
    if single_prior:
        lines.append(r"\begin{tabular}{@{}l|rr|rr|rr@{}}" "\n")
    else:
        lines.append(r"\begin{tabular}{@{}ll|rr|rr|rr@{}}" "\n")
    lines.append(r"\toprule" "\n")
    if single_prior:
        lines.append(
            r"\multirow{2}{*}{\textbf{GT}} & "
            r"\multicolumn{2}{c}{\textbf{TCSR (\%)} ($\uparrow$)} & "
            r"\multicolumn{2}{c}{\textbf{Gap$^{+}$ (s)} ($\downarrow$)} & "
            r"\multicolumn{2}{c}{\textbf{CT (s)} ($\downarrow$)} \\"
            "\n"
        )
        lines.append(
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}" "\n"
        )
        lines.append(
            r"& \textbf{Bayes} & \textbf{PF} & "
            r"\textbf{Bayes} & \textbf{PF} & "
            r"\textbf{Bayes} & \textbf{PF} \\"
            "\n"
        )
    else:
        lines.append(
            r"\multirow{2}{*}{\textbf{Init Prior}} & "
            r"\multirow{2}{*}{\textbf{GT}} & "
            r"\multicolumn{2}{c}{\textbf{TCSR (\%)} ($\uparrow$)} & "
            r"\multicolumn{2}{c}{\textbf{Gap$^{+}$ (s)} ($\downarrow$)} & "
            r"\multicolumn{2}{c}{\textbf{CT (s)} ($\downarrow$)} \\"
            "\n"
        )
        lines.append(
            r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}" "\n"
        )
        lines.append(
            r"& & \textbf{Bayes} & \textbf{PF} & "
            r"\textbf{Bayes} & \textbf{PF} & "
            r"\textbf{Bayes} & \textbf{PF} \\"
            "\n"
        )
    lines.append(r"\midrule" "\n")

    if single_prior:
        for row in rows:
            tcsr_best = _best_pair(
                row["bayes_tcsr"],
                row["pf_tcsr"],
                higher_is_better=True,
            )
            gap_best = _best_pair(
                row["bayes_gap"],
                row["pf_gap"],
                higher_is_better=False,
            )
            ct_best = _best_pair(
                row["bayes_ct"],
                row["pf_ct"],
                higher_is_better=False,
            )
            lines.append(
                f"\\textbf{{{GT_LABEL[row['gt_distribution']]}}} & "
                + " & ".join(
                    [
                        _format_tex(
                            row["bayes_tcsr"],
                            1,
                            highlight=tcsr_best[0],
                        ),
                        _format_tex(
                            row["pf_tcsr"],
                            1,
                            highlight=tcsr_best[1],
                        ),
                        _format_tex(
                            row["bayes_gap"],
                            1,
                            highlight=gap_best[0],
                        ),
                        _format_tex(
                            row["pf_gap"],
                            1,
                            highlight=gap_best[1],
                        ),
                        _format_tex(
                            row["bayes_ct"],
                            3,
                            highlight=ct_best[0],
                        ),
                        _format_tex(
                            row["pf_ct"],
                            3,
                            highlight=ct_best[1],
                        ),
                    ]
                )
                + r" \\"
                + "\n"
            )
    else:
        for prior_index, init_prior in enumerate(present_priors):
            prior_rows = [row for row in rows if row["init_prior"] == init_prior]
            for row_index, row in enumerate(prior_rows):
                tcsr_best = _best_pair(
                    row["bayes_tcsr"],
                    row["pf_tcsr"],
                    higher_is_better=True,
                )
                gap_best = _best_pair(
                    row["bayes_gap"],
                    row["pf_gap"],
                    higher_is_better=False,
                )
                ct_best = _best_pair(
                    row["bayes_ct"],
                    row["pf_ct"],
                    higher_is_better=False,
                )

                prefix = (
                    rf"\multirow{{{len(prior_rows)}}}{{*}}{{\textbf{{{INIT_PRIOR_LABEL[init_prior]}}}}}"
                    if row_index == 0
                    else ""
                )
                lines.append(
                    f"{prefix} & \\textbf{{{GT_LABEL[row['gt_distribution']]}}} & "
                    + " & ".join(
                        [
                            _format_tex(
                                row["bayes_tcsr"],
                                1,
                                highlight=tcsr_best[0],
                            ),
                            _format_tex(
                                row["pf_tcsr"],
                                1,
                                highlight=tcsr_best[1],
                            ),
                            _format_tex(
                                row["bayes_gap"],
                                1,
                                highlight=gap_best[0],
                            ),
                            _format_tex(
                                row["pf_gap"],
                                1,
                                highlight=gap_best[1],
                            ),
                            _format_tex(
                                row["bayes_ct"],
                                3,
                                highlight=ct_best[0],
                            ),
                            _format_tex(
                                row["pf_ct"],
                                3,
                                highlight=ct_best[1],
                            ),
                        ]
                    )
                    + r" \\"
                    + "\n"
                )
            if prior_index != len(present_priors) - 1:
                lines.append(r"\midrule" "\n")

    lines.append(r"\bottomrule" "\n")
    lines.append(r"\end{tabular}" "\n")
    return "".join(lines)


def build_tex(
    summary: dict[str, Any],
    raw: dict[str, Any],
) -> str:
    gap_plus_summary = load_gap_plus_summary(raw)
    rows = _collect_rows(summary, gap_plus_summary)
    if not rows:
        raise KeyError("No PF-vs-Bayesian keys found in summary.")
    present_priors = _present_priors(rows)
    tabular = _build_tabular(summary, gap_plus_summary)
    return (
        r"\begin{table*}[t]"
        "\n"
        r"\centering"
        "\n"
        r"{\small"
        "\n"
        r"\setlength{\tabcolsep}{4.2pt}"
        "\n"
        r"\renewcommand{\arraystretch}{1.05}"
        "\n"
        r"\resizebox{\linewidth}{!}{%"
        "\n"
        + tabular
        + "}\n"
        + "}\n"
        + _build_caption_text(present_priors)
        + "\n"
        + r"\label{tab:pf_vs_bayesian_overall}"
        + "\n"
        + r"\end{table*}"
        + "\n"
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
        "--raw",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_RAW,
        help="Path to offline_comparison_raw.json.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_OUTPUT,
        help="Output .tex file path.",
    )
    args = parser.parse_args()

    summary = _load_json(args.summary)
    raw = _load_json(args.raw)
    tex = build_tex(summary, raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(tex, encoding="utf-8")
    print(f"Saved LaTeX table to {args.output}")


if __name__ == "__main__":
    main()
