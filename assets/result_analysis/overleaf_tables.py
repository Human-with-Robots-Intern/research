"""Export post-hoc LaTeX tables from offline analysis summaries."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# parents[0]=result_analysis, parents[1]=assets, parents[2]=repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CASE_LABELS = {
    "tasks_2_constraints_1": "T2C1",
    "tasks_2_constraints_2": "T2C2",
    "tasks_3_constraints_1": "T3C1",
    "tasks_3_constraints_2": "T3C2",
}
CASE_ORDER = list(CASE_LABELS.keys())


@dataclass(frozen=True)
class ParsedSetting:
    """Structured representation of one analysis summary key."""

    raw_key: str
    init_prior: str | None
    baseline_name: str
    ablation_config: str | None
    beam_width: int | None
    beam_depth: int | None
    eta: str | None


@dataclass(frozen=True)
class OverallRow:
    """Weighted overall metrics for one setting."""

    parsed: ParsedSetting
    n_instructions: int
    sr: float
    tsr: float
    makespan: float
    makespan_gap: float
    computation_time: float


PRIMARY_FILENAMES = {
    "overall": "tab_scalability_overall_{prior}.tex",
}

STALE_FILENAME_PATTERNS = (
    "tab_scalability_default_by_case_*.tex",
    "tab_scalability_none_monitoring_by_case_*.tex",
    "tab_scalability_all_*.tex",
    "scalability_default_by_case.tex",
    "scalability_none_monitoring_by_case.tex",
)


def parse_setting_key(setting_key: str) -> ParsedSetting:
    """Parse one summary key from offline_analysis_summary.json."""

    parts = setting_key.split("__")
    if len(parts) == 2:
        return ParsedSetting(
            raw_key=setting_key,
            init_prior=parts[0],
            baseline_name=parts[1],
            ablation_config=None,
            beam_width=None,
            beam_depth=None,
            eta=None,
        )

    init_prior = parts[0] if parts else None
    baseline_name = parts[1] if len(parts) > 1 else setting_key
    ablation_config = parts[2] if len(parts) > 2 else None
    beam_width = None
    beam_depth = None
    eta = None

    for token in parts[3:]:
        if token.startswith("w") and "_d" in token:
            width_token, depth_token = token.split("_d", maxsplit=1)
            beam_width = int(width_token[1:])
            beam_depth = int(depth_token)
        elif token.startswith("eta"):
            eta = token[3:]

    return ParsedSetting(
        raw_key=setting_key,
        init_prior=init_prior,
        baseline_name=baseline_name,
        ablation_config=ablation_config,
        beam_width=beam_width,
        beam_depth=beam_depth,
        eta=eta,
    )


def load_summary(summary_path: Path) -> dict[str, Any]:
    """Load an offline analysis summary JSON."""

    return json.loads(summary_path.read_text(encoding="utf-8"))


def build_overall_rows(
    summary: dict[str, Any],
    *,
    init_prior: str,
    skip_incomplete: bool = True,
) -> list[OverallRow]:
    """Aggregate per-case summary rows into weighted overall rows."""

    overall_rows: list[OverallRow] = []
    for key, cases in summary.items():
        parsed = parse_setting_key(key)
        if parsed.init_prior != init_prior:
            continue

        case_items = [
            (case_name, case_metrics)
            for case_name, case_metrics in cases.items()
            if case_name in CASE_LABELS
        ]
        if skip_incomplete and len(case_items) != len(CASE_ORDER):
            continue

        total_n = sum(int(metrics["n_instructions"]) for _, metrics in case_items)
        if total_n <= 0:
            continue

        def weighted(metric_name: str) -> float:
            return sum(
                float(metrics[metric_name]) * int(metrics["n_instructions"])
                for _, metrics in case_items
            ) / total_n

        overall_rows.append(
            OverallRow(
                parsed=parsed,
                n_instructions=total_n,
                sr=weighted("sr"),
                tsr=weighted("tsr"),
                makespan=weighted("makespan"),
                makespan_gap=weighted("makespan_gap"),
                computation_time=weighted("computation_time"),
            )
        )

    overall_rows.sort(key=_setting_sort_key)
    return overall_rows


def render_scalability_tables(
    summary: dict[str, Any],
    *,
    init_prior: str = "CORRECT_ESTIMATE",
) -> dict[str, str]:
    """Render the main-text Overleaf table for scalability analysis."""

    overall_rows = build_overall_rows(summary, init_prior=init_prior)
    none_rows = [
        row for row in overall_rows if row.parsed.ablation_config == "NONE_MONITORING"
    ]
    edf_rows = [row for row in overall_rows if row.parsed.baseline_name == "edf"]

    overall_table = _render_overall_table(
        none_rows + edf_rows,
        init_prior=init_prior,
    )
    prior_token = _sanitize_label_token(init_prior)
    return {
        PRIMARY_FILENAMES["overall"].format(prior=prior_token): overall_table,
        "scalability_overall.tex": overall_table,
        "scalability_tables.tex": overall_table,
    }


def save_rendered_tables(rendered_tables: dict[str, str], output_dir: Path) -> list[Path]:
    """Persist rendered LaTeX table snippets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for pattern in STALE_FILENAME_PATTERNS:
        for stale_path in output_dir.glob(pattern):
            stale_path.unlink(missing_ok=True)

    written_paths: list[Path] = []
    for filename, content in rendered_tables.items():
        path = output_dir / filename
        path.write_text(content + "\n", encoding="utf-8")
        written_paths.append(path)
    return written_paths


def _render_overall_table(
    rows: list[OverallRow],
    *,
    init_prior: str,
) -> str:
    """Render the main-text scalability table."""

    metric_specs = [
        ("tsr", True, 1),
        ("makespan", False, 1),
        ("makespan_gap", False, 1),
        ("computation_time", False, 3),
    ]
    metric_style_maps: dict[str, dict[int, str]] = {}
    for metric_name, higher_is_better, _digits in metric_specs:
        target_indices = [
            index
            for index, row in enumerate(rows)
            if metric_name in {"tsr", "computation_time"}
            or _has_meaningful_makespan(row.tsr)
        ]
        target_values = [getattr(rows[index], metric_name) for index in target_indices]
        target_styles = _compute_highlight_styles(
            target_values,
            higher_is_better=higher_is_better,
        )
        metric_style_maps[metric_name] = dict(zip(target_indices, target_styles))

    body_lines = []
    for row_index, row in enumerate(rows):
        show_makespan = _has_meaningful_makespan(row.tsr)
        body_lines.append(
            "        "
            + " & ".join(
                [
                    _format_method_label(row.parsed),
                    _format_metric_cell(
                        row.tsr,
                        1,
                        metric_style_maps["tsr"].get(row_index, ""),
                    ),
                    _format_metric_cell(
                        row.makespan,
                        1,
                        metric_style_maps["makespan"].get(row_index, ""),
                        enabled=show_makespan,
                    ),
                    _format_metric_cell(
                        row.makespan_gap,
                        1,
                        metric_style_maps["makespan_gap"].get(row_index, ""),
                        enabled=show_makespan,
                    ),
                    _format_metric_cell(
                        row.computation_time,
                        3,
                        metric_style_maps["computation_time"].get(row_index, ""),
                    ),
                ]
            )
            + r" \\"
        )

    prior_caption = _format_prior_caption(init_prior)
    prior_label = _sanitize_label_token(init_prior)
    return "\n".join(
        [
            r"\begin{table}[t]",
            r"\centering",
            rf"\caption{{Scalability comparison in the no-monitoring control setting under {prior_caption}. Higher TCSR is better ($\uparrow$), while lower makespan, oracle gap, and computation time are better ($\downarrow$). Makespan and oracle gap are shown only when TCSR is 100.0. Bold indicates the best value and underline indicates the second best within the table.}}",
            rf"\label{{tab:scalability_overall_{prior_label}}}",
            r"{\setlength{\tabcolsep}{2pt}",
            r"\renewcommand{\arraystretch}{1.1}",
            r"\begin{tabular}{@{}l|c c c c@{}}",
            r"\toprule",
            r"Method & \textbf{TCSR ($\uparrow$)} & \textbf{MS ($\downarrow$)} & \textbf{Gap ($\downarrow$)} & \textbf{CT ($\downarrow$)} \\",
            r"\midrule",
            *body_lines,
            r"\bottomrule",
            r"\end{tabular}}",
            r"\end{table}",
        ]
    )


def _render_case_table(
    summary: dict[str, Any],
    rows: list[OverallRow],
    *,
    init_prior: str,
) -> str:
    """Render one case-wise table for a family of settings."""

    if not rows:
        return ""

    is_none_monitoring = rows[0].parsed.ablation_config == "NONE_MONITORING"
    prior_label = _sanitize_label_token(init_prior)
    label = (
        f"tab:scalability_none_monitoring_by_case_{prior_label}"
        if is_none_monitoring
        else f"tab:scalability_default_by_case_{prior_label}"
    )
    caption = (
        f"Case-wise scalability results for the none-monitoring ablation under {_format_prior_caption(init_prior)}."
        if is_none_monitoring
        else f"Case-wise scalability results for the monitored scheduler under {_format_prior_caption(init_prior)}."
    )

    case_highlights = _compute_case_highlights(summary, rows)
    body_lines: list[str] = []
    for row in rows:
        case_metrics = summary[row.parsed.raw_key]
        available_cases = [case for case in CASE_ORDER if case in case_metrics]
        for case_index, case_name in enumerate(available_cases):
            metrics = case_metrics[case_name]
            case_label = CASE_LABELS[case_name]
            case_styles = case_highlights[case_name]
            show_makespan = _has_meaningful_makespan(float(metrics["tsr"]))
            metric_cells = [
                rf"\textbf{{{case_label}}}",
                _format_metric_cell(
                    float(metrics["tsr"]),
                    1,
                    case_styles["tsr"][row.parsed.raw_key],
                ),
                _format_metric_cell(
                    float(metrics["makespan"]),
                    1,
                    case_styles["makespan"].get(row.parsed.raw_key, ""),
                    enabled=show_makespan,
                ),
                _format_metric_cell(
                    float(metrics["makespan_gap"]),
                    1,
                    case_styles["makespan_gap"].get(row.parsed.raw_key, ""),
                    enabled=show_makespan,
                ),
                _format_metric_cell(
                    float(metrics["computation_time"]),
                    3,
                    case_styles["computation_time"][row.parsed.raw_key],
                ),
            ]
            if case_index == 0:
                method_cell = (
                    rf"\multirow{{{len(available_cases)}}}{{*}}{{\textbf{{{_format_method_label(row.parsed)}}}}}"
                )
                body_lines.append("        " + " & ".join([method_cell, *metric_cells]) + r" \\")
            else:
                body_lines.append("        " + " & ".join(["", *metric_cells]) + r" \\")
        body_lines.append(r"        \midrule")

    if body_lines and body_lines[-1].strip() == r"\midrule":
        body_lines.pop()

    return "\n".join(
        [
            r"\begin{table}[t]",
            r"\centering",
            rf"\caption{{{caption} Higher TCSR is better ($\uparrow$), while lower makespan, oracle gap, and computation time are better ($\downarrow$). Makespan and oracle gap are shown only when TCSR is 100.0. Bold indicates the best value and underline indicates the second best within each task-complexity block.}}",
            rf"\label{{{label}}}",
            r"{\setlength{\tabcolsep}{2pt}",
            r"\renewcommand{\arraystretch}{1.1}",
            r"\begin{tabular}{@{}l l|c c c c@{}}",
            r"\toprule",
            r"Method & Tasks & \textbf{TCSR ($\uparrow$)} & \textbf{MS ($\downarrow$)} & \textbf{Gap ($\downarrow$)} & \textbf{CT ($\downarrow$)} \\",
            r"\midrule",
            *body_lines,
            r"\bottomrule",
            r"\end{tabular}}",
            r"\end{table}",
        ]
    )


def _format_method_label(parsed: ParsedSetting) -> str:
    """Return a paper-friendly method label."""

    if parsed.baseline_name == "edf":
        return "tDAG+EDF"
    if parsed.baseline_name == "cpm":
        return "tDAG+CPM"
    if parsed.baseline_name == "particle_filter":
        prefix = "PF Ours"
    else:
        prefix = "Ours"

    beam_suffix = ""
    if parsed.beam_width is not None and parsed.beam_depth is not None:
        beam_suffix = rf" ($w{parsed.beam_width},d{parsed.beam_depth}$)"

    if parsed.ablation_config == "NONE_MONITORING":
        return f"{prefix} w/o Mon.{beam_suffix}"
    return f"{prefix}{beam_suffix}"


def _setting_sort_key(row: OverallRow) -> tuple[int, int, int, int]:
    """Provide a stable paper-friendly row ordering."""

    parsed = row.parsed
    baseline_order = {
        ("bayesian", "DEFAULT"): 0,
        ("bayesian", "NONE_MONITORING"): 1,
        ("particle_filter", "DEFAULT"): 2,
        ("particle_filter", "NONE_MONITORING"): 3,
        ("edf", None): 4,
        ("cpm", None): 5,
    }
    return (
        baseline_order.get((parsed.baseline_name, parsed.ablation_config), 99),
        parsed.beam_width if parsed.beam_width is not None else 999,
        parsed.beam_depth if parsed.beam_depth is not None else 999,
        int(float(parsed.eta) * 1000) if parsed.eta is not None else 0,
    )


def _fmt(value: float, digits: int) -> str:
    """Format a scalar for LaTeX output."""

    return f"{value:.{digits}f}"


def _has_meaningful_makespan(tsr: float, tolerance: float = 1e-9) -> bool:
    """Return whether makespan/gap should be shown for the given TCSR."""

    return abs(tsr - 100.0) <= tolerance


def _format_metric_cell(
    value: float,
    digits: int,
    style: str,
    *,
    enabled: bool = True,
) -> str:
    """Apply best/second-best styling to a numeric cell."""

    if not enabled:
        return "--"

    rendered = _fmt(value, digits)
    if style == "best":
        return rf"\textbf{{{rendered}}}"
    if style == "second":
        return rf"\underline{{{rendered}}}"
    return rendered


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


def _compute_case_highlights(
    summary: dict[str, Any],
    rows: list[OverallRow],
) -> dict[str, dict[str, dict[str, str]]]:
    """Compute per-case best/second-best styles across the provided settings."""

    metric_specs = [
        ("tsr", True),
        ("makespan", False),
        ("makespan_gap", False),
        ("computation_time", False),
    ]
    result: dict[str, dict[str, dict[str, str]]] = {}
    for case_name in CASE_ORDER:
        result[case_name] = {}
        for metric_name, higher_is_better in metric_specs:
            raw_keys = [
                row.parsed.raw_key
                for row in rows
                if case_name in summary.get(row.parsed.raw_key, {})
                and (
                    metric_name in {"tsr", "computation_time"}
                    or _has_meaningful_makespan(
                        float(summary[row.parsed.raw_key][case_name]["tsr"])
                    )
                )
            ]
            values = [
                float(summary[raw_key][case_name][metric_name])
                for raw_key in raw_keys
            ]
            styles = _compute_highlight_styles(
                values,
                higher_is_better=higher_is_better,
            )
            result[case_name][metric_name] = dict(zip(raw_keys, styles))
    return result


def _sanitize_label_token(token: str) -> str:
    """Normalize a string for LaTeX labels and filenames."""

    return token.lower().replace("__", "_").replace("-", "_")


def _format_prior_caption(init_prior: str) -> str:
    """Return a readable phrase for the selected init-prior slice."""

    return init_prior.replace("_", " ").lower()


def main() -> None:
    """CLI for exporting Overleaf-ready LaTeX tables."""

    parser = argparse.ArgumentParser(
        description="Export Overleaf-ready LaTeX tables from offline analysis summaries."
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path("assets/results/offline_exp_result/analysis/offline_analysis_summary.json"),
        help="Path to offline_analysis_summary.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/results/offline_exp_result/analysis/latex_tables"),
        help="Directory where LaTeX snippets will be written.",
    )
    parser.add_argument(
        "--init-prior",
        type=str,
        default="CORRECT_ESTIMATE",
        help="Init prior slice to export.",
    )
    args = parser.parse_args()

    summary = load_summary(args.summary_path)
    rendered = render_scalability_tables(summary, init_prior=args.init_prior)
    written_paths = save_rendered_tables(rendered, args.output_dir)
    for path in written_paths:
        print(path)


if __name__ == "__main__":
    main()
