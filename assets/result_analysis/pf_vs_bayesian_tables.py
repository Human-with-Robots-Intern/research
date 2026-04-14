"""Export unified PF-vs-Bayesian LaTeX tables from offline analysis summaries."""

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

GT_ORDER = ["gaussian", "lognormal", "mixture"]
METHOD_ORDER = [
    "Bayesian",
    "PF (Gaussian likelihood)",
    "PF (GT-family likelihood)",
]


@dataclass(frozen=True)
class ParsedPFSetting:
    """Structured representation of one PF-vs-Bayesian summary key."""

    raw_key: str
    init_prior: str | None
    baseline_name: str
    ablation_config: str | None
    beam_width: int | None
    beam_depth: int | None
    eta: str | None
    gt_distribution: str
    particle_distribution: str | None
    particle_likelihood_family: str | None


@dataclass(frozen=True)
class PFUnifiedRow:
    """Weighted overall metrics for one unified PF/Bayesian comparison row."""

    gt_distribution: str
    method_label: str
    tsr: float
    makespan: float
    computation_time: float
    n_instructions: int


def load_summary(summary_path: Path) -> dict[str, Any]:
    """Load an offline analysis summary JSON."""

    return json.loads(summary_path.read_text(encoding="utf-8"))


def parse_pf_setting_key(setting_key: str) -> ParsedPFSetting:
    """Parse one summary key relevant to the PF-vs-Bayesian suite."""

    parts = setting_key.split("__")
    init_prior = parts[0] if parts else None
    baseline_name = parts[1] if len(parts) > 1 else setting_key
    ablation_config = parts[2] if len(parts) > 2 else None
    beam_width = None
    beam_depth = None
    eta = None
    gt_distribution = "constant"
    particle_distribution = None
    particle_likelihood_family = None

    for token in parts[3:]:
        if token.startswith("w") and "_d" in token:
            width_token, depth_token = token.split("_d", maxsplit=1)
            beam_width = int(width_token[1:])
            beam_depth = int(depth_token)
        elif token.startswith("eta"):
            eta = token[3:]
        elif token.startswith("gt"):
            gt_distribution = token[2:]
        elif token.startswith("pdist"):
            particle_distribution = token[5:]
        elif token.startswith("plik"):
            particle_likelihood_family = token[4:]

    return ParsedPFSetting(
        raw_key=setting_key,
        init_prior=init_prior,
        baseline_name=baseline_name,
        ablation_config=ablation_config,
        beam_width=beam_width,
        beam_depth=beam_depth,
        eta=eta,
        gt_distribution=gt_distribution,
        particle_distribution=particle_distribution,
        particle_likelihood_family=particle_likelihood_family,
    )


def build_unified_rows(
    summary: dict[str, Any],
    *,
    init_prior: str = "CORRECT_ESTIMATE",
) -> list[PFUnifiedRow]:
    """Build weighted overall rows for the scheduler-attached PF/Bayesian comparison."""

    rows: list[PFUnifiedRow] = []
    for key, cases in summary.items():
        parsed = parse_pf_setting_key(key)
        if parsed.init_prior != init_prior:
            continue
        if parsed.baseline_name not in {"bayesian", "particle_filter"}:
            continue
        if parsed.ablation_config != "DEFAULT":
            continue
        if (parsed.beam_width, parsed.beam_depth, parsed.eta) != (10, 10, "0.1"):
            continue
        if parsed.gt_distribution not in GT_ORDER:
            continue

        method_label = _resolve_method_label(parsed)
        if method_label is None:
            continue

        case_items = [
            metrics
            for case_name, metrics in cases.items()
            if case_name.startswith("tasks_")
        ]
        total_n = sum(int(metrics["n_instructions"]) for metrics in case_items)
        if total_n <= 0:
            continue

        def weighted(metric_name: str) -> float:
            return sum(
                float(metrics[metric_name]) * int(metrics["n_instructions"])
                for metrics in case_items
            ) / total_n

        rows.append(
            PFUnifiedRow(
                gt_distribution=parsed.gt_distribution,
                method_label=method_label,
                tsr=weighted("tsr"),
                makespan=weighted("makespan"),
                computation_time=weighted("computation_time"),
                n_instructions=total_n,
            )
        )

    rows.sort(key=lambda row: (GT_ORDER.index(row.gt_distribution), METHOD_ORDER.index(row.method_label)))
    return rows


def render_pf_vs_bayesian_table(
    summary: dict[str, Any],
    *,
    init_prior: str = "CORRECT_ESTIMATE",
) -> dict[str, str]:
    """Render one unified Overleaf-ready PF-vs-Bayesian table."""

    rows = build_unified_rows(summary, init_prior=init_prior)
    prior_token = _sanitize_label_token(init_prior)
    table = _render_table(rows, init_prior=init_prior)
    return {
        f"tab_pf_vs_bayesian_unified_{prior_token}.tex": table,
        "pf_vs_bayesian_unified.tex": table,
        "pf_vs_bayesian_tables.tex": table,
    }


def save_rendered_tables(rendered_tables: dict[str, str], output_dir: Path) -> list[Path]:
    """Persist rendered LaTeX snippets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for filename, content in rendered_tables.items():
        path = output_dir / filename
        path.write_text(content + "\n", encoding="utf-8")
        written_paths.append(path)
    return written_paths


def _resolve_method_label(parsed: ParsedPFSetting) -> str | None:
    """Map one parsed summary key to a unified table row label."""

    if parsed.baseline_name == "bayesian":
        return "Bayesian"
    if parsed.particle_distribution not in {None, "gaussian"}:
        return None
    if parsed.particle_likelihood_family is None:
        return "PF (Gaussian likelihood)"
    if parsed.gt_distribution in {"lognormal", "mixture"} and parsed.particle_likelihood_family == parsed.gt_distribution:
        return "PF (GT-family likelihood)"
    return None


def _render_table(rows: list[PFUnifiedRow], *, init_prior: str) -> str:
    """Render the unified PF-vs-Bayesian table."""

    body_lines: list[str] = []
    for row in rows:
        show_makespan = row.tsr >= 100.0 - 1e-9
        body_lines.append(
            "        "
            + " & ".join(
                [
                    _format_gt_label(row.gt_distribution),
                    row.method_label,
                    _format_metric(row.tsr, digits=1),
                    _format_metric(row.makespan, digits=1) if show_makespan else "--",
                    _format_metric(row.computation_time, digits=3),
                ]
            )
            + r" \\"
        )

    prior_caption = _format_prior_caption(init_prior)
    prior_token = _sanitize_label_token(init_prior)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{@{}l|l c c c@{}}",
        r"\toprule",
        r"GT & Method & \textbf{TCSR ($\uparrow$)} & \textbf{MS ($\downarrow$)} & \textbf{CT ($\downarrow$)} \\",
        r"\midrule",
        *body_lines,
        r"\bottomrule",
        r"\end{tabular}}",
        (
            r"\caption{Scheduler-attached PF vs Bayesian comparison under "
            + prior_caption
            + r". All PF rows use Gaussian particle initialization. "
            + r"The GT-family likelihood variant is shown only for the non-Gaussian GT settings. "
            + r"Makespan is shown only when TCSR is 100.0.}"
        ),
        rf"\label{{tab:pf_vs_bayesian_unified_{prior_token}}}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def _format_gt_label(gt_distribution: str) -> str:
    return {
        "gaussian": "Gaussian",
        "lognormal": "Lognormal",
        "mixture": "Mixture",
    }.get(gt_distribution, gt_distribution.title())


def _format_metric(value: float, *, digits: int) -> str:
    return f"{value:.{digits}f}"


def _format_prior_caption(init_prior: str) -> str:
    return {
        "CORRECT_ESTIMATE": "Correct Estimate",
        "UNDER_ESTIMATE": "Under Estimate",
        "OVER_ESTIMATE": "Over Estimate",
    }.get(init_prior, init_prior.replace("_", " ").title())


def _sanitize_label_token(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def main() -> None:
    """CLI entrypoint."""

    parser = argparse.ArgumentParser(
        description="Export unified PF-vs-Bayesian Overleaf tables from offline analysis summaries."
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path("assets/results/offline_exp_result/analysis/offline_analysis_summary.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/results/offline_exp_result/analysis/latex_tables"),
    )
    parser.add_argument(
        "--init-prior",
        type=str,
        default="CORRECT_ESTIMATE",
    )
    args = parser.parse_args()

    summary = load_summary(args.summary_path)
    rendered = render_pf_vs_bayesian_table(summary, init_prior=args.init_prior)
    written = save_rendered_tables(rendered, args.output_dir)
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
