"""Export LaTeX tables for belief robustness benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# parents[0]=result_analysis, parents[1]=assets, parents[2]=repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiments.belief_robustness import (
    build_belief_appendix_rows,
    build_belief_main_table_rows,
)

GT_ORDER = ["gaussian", "lognormal", "mixture"]
METHOD_ORDER = [
    "Bayesian",
    "PF (Gaussian likelihood)",
    "PF (GT-family likelihood)",
]
PRIOR_ORDER = ["UNDER_ESTIMATE", "CORRECT_ESTIMATE", "OVER_ESTIMATE"]


def load_summary_rows(summary_path: Path) -> list[dict[str, Any]]:
    """Load summary rows from a saved belief benchmark summary JSON."""

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return list(payload.get("summary_rows", []))


def render_belief_robustness_tables(
    summary_rows: list[dict[str, Any]],
    *,
    eta: float = 0.1,
) -> dict[str, str]:
    """Render main and appendix LaTeX tables for the belief benchmark."""

    eta_rows = [row for row in summary_rows if abs(float(row["eta"]) - eta) < 1e-9]
    main_shared_gaussian_rows = build_belief_main_table_rows(
        eta_rows,
        observation_setting="shared_gaussian",
    )
    main_same_as_gt_rows = build_belief_main_table_rows(
        eta_rows,
        observation_setting="same_as_gt",
    )
    appendix_shared_gaussian_rows = build_belief_appendix_rows(
        eta_rows,
        observation_setting="shared_gaussian",
    )
    appendix_same_as_gt_rows = build_belief_appendix_rows(
        eta_rows,
        observation_setting="same_as_gt",
    )

    rendered = {
        "tab_belief_robustness_main_shared_gaussian.tex": _render_main_table(
            main_shared_gaussian_rows,
            eta=eta,
            observation_setting="shared_gaussian",
        ),
        "tab_belief_robustness_main_same_as_gt.tex": _render_main_table(
            main_same_as_gt_rows,
            eta=eta,
            observation_setting="same_as_gt",
        ),
        "tab_belief_robustness_appendix_shared_gaussian.tex": _render_appendix_table(
            appendix_shared_gaussian_rows,
            eta=eta,
            observation_setting="shared_gaussian",
        ),
        "tab_belief_robustness_appendix_same_as_gt.tex": _render_appendix_table(
            appendix_same_as_gt_rows,
            eta=eta,
            observation_setting="same_as_gt",
        ),
    }
    rendered["belief_robustness_tables.tex"] = "\n\n".join(rendered.values())
    return rendered


def save_rendered_tables(rendered_tables: dict[str, str], output_dir: Path) -> list[Path]:
    """Persist rendered LaTeX snippets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for filename, content in rendered_tables.items():
        path = output_dir / filename
        path.write_text(content + "\n", encoding="utf-8")
        written_paths.append(path)
    return written_paths


def _render_main_table(
    rows: list[dict[str, Any]],
    *,
    eta: float,
    observation_setting: str,
) -> str:
    body_lines = [
        "        "
        + " & ".join(
            [
                _format_gt_label(str(row["gt_distribution"])),
                _format_mean(float(row["gt_target_mean"])),
                str(row["method_label"]),
                _format_metric(float(row["late_trigger_rate"]), digits=3),
                _format_metric(float(row["calibration_error"]), digits=3),
                _format_metric(
                    float(row["mean_posterior_mean_abs_error"]),
                    digits=3,
                ),
                _format_metric(float(row["mean_trigger_abs_error"]), digits=3),
            ]
        )
        + r" \\"
        for row in _sort_main_rows(rows)
    ]

    setting_token = _setting_token(observation_setting)
    setting_caption = _setting_caption(observation_setting)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{@{}l c|l c c c c@{}}",
        r"\toprule",
        r"GT & Mean & Method & \textbf{Late ($\downarrow$)} & \textbf{|Late-$\eta$| ($\downarrow$)} & \textbf{Posterior Mean Error ($\downarrow$)} & \textbf{Trigger Error ($\downarrow$)} \\",
        r"\midrule",
        *body_lines,
        r"\bottomrule",
        r"\end{tabular}}",
        (
            r"\caption{Belief robustness benchmark under "
            + setting_caption
            + rf". Metrics are aggregated across UNDER/CORRECT/OVER priors with equal weight. Here $\eta={eta:.1f}$."
            + r"}"
        ),
        rf"\label{{tab:belief_robustness_main_{setting_token}}}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def _render_appendix_table(
    rows: list[dict[str, Any]],
    *,
    eta: float,
    observation_setting: str,
) -> str:
    body_lines = [
        "        "
        + " & ".join(
            [
                _format_gt_label(str(row["gt_distribution"])),
                _format_mean(float(row["gt_target_mean"])),
                _format_prior_label(str(row["prior_config"])),
                str(row["method_label"]),
                _format_metric(float(row["late_trigger_rate"]), digits=3),
                _format_metric(float(row["calibration_error"]), digits=3),
                _format_metric(
                    float(row["mean_posterior_mean_abs_error"]),
                    digits=3,
                ),
                _format_metric(float(row["mean_trigger_abs_error"]), digits=3),
            ]
        )
        + r" \\"
        for row in _sort_appendix_rows(rows)
    ]

    setting_token = _setting_token(observation_setting)
    setting_caption = _setting_caption(observation_setting)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{@{}l c l|l c c c c@{}}",
        r"\toprule",
        r"GT & Mean & Prior & Method & \textbf{Late ($\downarrow$)} & \textbf{|Late-$\eta$| ($\downarrow$)} & \textbf{Posterior Mean Error ($\downarrow$)} & \textbf{Trigger Error ($\downarrow$)} \\",
        r"\midrule",
        *body_lines,
        r"\bottomrule",
        r"\end{tabular}}",
        (
            r"\caption{Appendix belief robustness results under "
            + setting_caption
            + rf", split by prior condition. Here $\eta={eta:.1f}$."
            + r"}"
        ),
        rf"\label{{tab:belief_robustness_appendix_{setting_token}}}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def _order_index(order: list[str], value: str, list_name: str) -> int:
    """Return the position of *value* in *order*, raising a clear error if missing."""
    try:
        return order.index(value)
    except ValueError:
        raise ValueError(
            f"{value!r} not found in {list_name} = {order}. "
            "Add it to the ordering list at the top of this module."
        ) from None


def _sort_main_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _order_index(GT_ORDER, str(row["gt_distribution"]), "GT_ORDER"),
            float(row["gt_mean_multiplier"]),
            _order_index(METHOD_ORDER, str(row["method_label"]), "METHOD_ORDER"),
        ),
    )


def _sort_appendix_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _order_index(GT_ORDER, str(row["gt_distribution"]), "GT_ORDER"),
            float(row["gt_mean_multiplier"]),
            _order_index(PRIOR_ORDER, str(row["prior_config"]), "PRIOR_ORDER"),
            _order_index(METHOD_ORDER, str(row["method_label"]), "METHOD_ORDER"),
        ),
    )


def _format_gt_label(gt_distribution: str) -> str:
    return {
        "gaussian": "Gaussian",
        "lognormal": "Lognormal",
        "mixture": "Mixture",
    }.get(gt_distribution, gt_distribution.title())


def _format_prior_label(prior_config: str) -> str:
    return {
        "UNDER_ESTIMATE": "Under",
        "CORRECT_ESTIMATE": "Correct",
        "OVER_ESTIMATE": "Over",
    }.get(prior_config, prior_config.replace("_", " ").title())


def _format_mean(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.1f}"


def _format_metric(value: float, *, digits: int) -> str:
    return f"{value:.{digits}f}"


def _setting_caption(observation_setting: str) -> str:
    if observation_setting == "shared_gaussian":
        return "shared Gaussian observation"
    if observation_setting == "same_as_gt":
        return "same-as-GT observation stress"
    return observation_setting.replace("_", " ")


def _setting_token(observation_setting: str) -> str:
    return observation_setting.lower()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export LaTeX tables for the belief robustness benchmark.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path(
            "assets/results/offline_exp_result/belief_latex_export/belief_benchmark_summary.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "assets/results/offline_exp_result/belief_latex_export/latex_tables"
        ),
    )
    parser.add_argument(
        "--eta",
        type=float,
        default=0.1,
    )
    args = parser.parse_args()

    rendered = render_belief_robustness_tables(
        load_summary_rows(args.summary_path),
        eta=float(args.eta),
    )
    for path in save_rendered_tables(rendered, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
