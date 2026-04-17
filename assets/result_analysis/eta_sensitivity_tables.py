"""Render eta-sensitivity LaTeX tables from a single offline analysis summary.

Outputs two files:
- eta_sensitivity_overall.tex  : weighted-average across cases per (prior, eta)
- eta_sensitivity_by_case.tex  : per (prior, eta, case) breakdown

Usage::

    python -m assets.result_analysis.eta_sensitivity_tables
    python -m assets.result_analysis.eta_sensitivity_tables \\
        --summary path/to/offline_analysis_summary.json \\
        --batch-root path/to/offline_batch_eta_sensitivity \\
        --out-dir path/to/latex_tables
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SUMMARY = (
    "assets/results/offline_exp_result/analysis/eta_sensitivity/"
    "offline_analysis_summary.json"
)
DEFAULT_BATCH_ROOT = (
    "assets/results/offline_exp_result/offline_batch_eta_sensitivity"
)
DEFAULT_OUT_DIR = (
    "assets/results/offline_exp_result/analysis/eta_sensitivity/latex_tables"
)

INIT_PRIOR_ORDER: list[str] = [
    "UNDER_ESTIMATE",
    "CORRECT_ESTIMATE",
    "OVER_ESTIMATE",
]
INIT_PRIOR_LABEL: dict[str, str] = {
    "CORRECT_ESTIMATE": "Correct",
    "OVER_ESTIMATE": "Over",
    "UNDER_ESTIMATE": "Under",
}

ETA_ORDER: list[str] = ["0.01", "0.1", "0.9"]

CASES: list[tuple[str, str]] = [
    ("tasks_2_constraints_1", "T2C1"),
    ("tasks_2_constraints_2", "T2C2"),
    ("tasks_3_constraints_1", "T3C1"),
    ("tasks_3_constraints_2", "T3C2"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setting_key(init_prior: str, eta: str) -> str:
    return f"{init_prior}__bayesian__DEFAULT__w10_d10__eta{eta}"


def _eta_token(value: object) -> str:
    return f"{float(value):g}"


def _tex(
    x: float | None,
    nd: int = 1,
    *,
    bold: bool = False,
    underline: bool = False,
) -> str:
    if x is None:
        return "--"
    s = f"{x:.{nd}f}"
    if bold:
        return rf"{{\boldmath ${s}$}}"
    if underline:
        return rf"$\underline{{{s}}}$"
    return f"${s}$"


def _rank_format(
    values: list[float | None],
    nd: int = 1,
    *,
    higher_is_better: bool,
) -> list[str]:
    """Return formatted strings for each value: bold=best, underline=second-best."""
    eps = 1e-9
    sign = -1.0 if higher_is_better else 1.0
    present_values = [v for v in values if v is not None]
    sorted_unique = sorted(set(sign * v for v in present_values))
    rank0_val = sorted_unique[0] if len(sorted_unique) > 0 else None
    rank1_val = sorted_unique[1] if len(sorted_unique) > 1 else None

    result = []
    for v in values:
        if v is None:
            result.append("--")
            continue
        sv = sign * v
        if rank0_val is not None and abs(sv - rank0_val) < eps:
            result.append(_tex(v, nd=nd, bold=True))
        elif rank1_val is not None and abs(sv - rank1_val) < eps:
            result.append(_tex(v, nd=nd, underline=True))
        else:
            result.append(_tex(v, nd=nd))
    return result


def _weighted(case_metrics: dict[str, dict[str, Any]], field: str) -> float:
    """Aggregate ``field`` across cases.

    When every case provides a positive ``n_instructions``, uses an
    instruction-count-weighted mean. Otherwise falls back to an unweighted
    mean of case-level values (for legacy summaries that omit ``n_instructions``).
    """

    if not case_metrics:
        raise ValueError(f"No cases for field '{field}'.")

    weighted: list[tuple[int, float]] = []
    for m in case_metrics.values():
        if field not in m:
            raise KeyError(field)
        n_raw = m.get("n_instructions")
        if n_raw is None:
            weighted = []
            break
        n = int(n_raw)
        if n <= 0:
            weighted = []
            break
        weighted.append((n, float(m[field])))

    if weighted and len(weighted) == len(case_metrics):
        denom = sum(n for n, _ in weighted)
        if denom == 0:
            raise ValueError(f"No instructions for field '{field}'.")
        return sum(n * v for n, v in weighted) / denom

    values = [float(m[field]) for m in case_metrics.values()]
    return sum(values) / len(values)


def _weighted_optional(
    case_metrics: dict[str, dict[str, float | int | None]],
    field: str,
    *,
    weight_field: str = "n_instructions",
) -> float | None:
    total_n, total_w = 0, 0.0
    for m in case_metrics.values():
        value = m.get(field)
        if value is None:
            continue
        weight = int(m.get(weight_field, 0) or 0)
        if weight <= 0:
            continue
        total_w += weight * float(value)
        total_n += weight
    if total_n == 0:
        return None
    return total_w / total_n


# ---------------------------------------------------------------------------
# Monitor count loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _n_uncontrollable_targets(case_name: str, scene_name: str, instruction_name: str) -> int:
    from src.utils.config.constants import EPSILON
    from src.utils.io_utils.task_io import load_task_data_from_sampled_set
    from src.utils.task.task_util import TaskUtil

    task_data = load_task_data_from_sampled_set(case_name, scene_name, instruction_name)
    _, constraints, _ = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{scene_name}_physics_environment.json",
    )
    return len({
        end
        for _, end, data in constraints.edges(data=True)
        if data.get("info", {}).get("IsCritical")
        and float(data.get("info", {}).get("Interval", 0.0)) > EPSILON
    })


def load_monitor_summary(batch_root: Path) -> dict[str, dict[str, dict[str, float]]]:
    """Return avg monitor counts per (setting_key, case_name)."""

    buckets: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for path in batch_root.rglob("*.json"):
        if "_batch_summary" in path.parts:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("meta_data", {})
        if not isinstance(meta, dict):
            continue
        if meta.get("suite_name") != "eta_sensitivity":
            continue
        if meta.get("ablation_config") != "DEFAULT":
            continue
        if int(meta.get("beam_width", -1)) != 10 or int(meta.get("beam_depth", -1)) != 10:
            continue

        init_prior = meta.get("init_prior_config")
        eta = meta.get("eta")
        case_name = payload.get("case")
        scene_name = payload.get("scene_name")
        instruction_name = payload.get("instruction")
        monitor_count = payload.get("actual_monitor_count_total")

        if any(v is None for v in [init_prior, eta, case_name, scene_name, instruction_name, monitor_count]):
            continue
        if not isinstance(payload.get("actual_monitor_count_by_interval"), dict):
            continue

        n_unc = _n_uncontrollable_targets(str(case_name), str(scene_name), str(instruction_name))
        per_unc = float(monitor_count) / n_unc if n_unc > 0 else 0.0
        key = _setting_key(str(init_prior), _eta_token(eta))
        buckets.setdefault(key, {}).setdefault(str(case_name), []).append(
            (float(monitor_count), per_unc)
        )

    return {
        key: {
            case: {
                "avg_monitors": sum(c for c, _ in vals) / len(vals),
                "avg_monitors_per_unc": sum(p for _, p in vals) / len(vals),
            }
            for case, vals in cases.items()
        }
        for key, cases in buckets.items()
    }


def load_valid_gap_summary(
    raw_path: Path,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Return clipped oracle gap averaged over TCSR-valid instructions only."""

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
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
                    if float(tsr) < 1.0 - 1e-9:
                        continue
                    buckets.setdefault(setting_key, {}).setdefault(str(case_name), []).append(
                        max(0.0, float(gap))
                    )

    return {
        key: {
            case: {
                "gap_valid_plus": sum(vals) / len(vals),
                "n_valid_instructions": len(vals),
            }
            for case, vals in cases.items()
        }
        for key, cases in buckets.items()
    }


# ---------------------------------------------------------------------------
# Overall table
# ---------------------------------------------------------------------------

def _overall_tabular(
    summary: dict[str, Any],
    monitors: dict[str, dict[str, dict[str, float]]],
    valid_gaps: dict[str, dict[str, dict[str, float | int]]],
) -> str:
    lines: list[str] = []
    lines.append(r"\begin{tabular}{@{}llrrrr@{}}" "\n")
    lines.append(r"\toprule" "\n")
    lines.append(
        r"\textbf{Init Prior} & \textbf{$\eta$} & "
        r"\textbf{TCSR (\%)} ($\uparrow$) & "
        r"\textbf{Gap$^{+}$ (s)} ($\downarrow$) & "
        r"\textbf{Mon./Unc.} ($\downarrow$) & "
        r"\textbf{Avg. Mon.} ($\downarrow$) \\" "\n"
    )
    lines.append(r"\midrule" "\n")

    present_priors = [p for p in INIT_PRIOR_ORDER if any(
        _setting_key(p, eta) in summary for eta in ETA_ORDER
    )]

    for prior_idx, prior in enumerate(present_priors):
        present_etas = [eta for eta in ETA_ORDER if _setting_key(prior, eta) in summary]
        for eta_idx, eta in enumerate(present_etas):
            key = _setting_key(prior, eta)
            case_data = summary[key]
            mon_data = monitors.get(key, {})
            gap_data = valid_gaps.get(key, {})

            tsr = _weighted(case_data, "tsr")
            gap = _weighted_optional(
                {
                    c: {
                        "gap_valid_plus": gap_data[c]["gap_valid_plus"],
                        "n_valid_instructions": gap_data[c]["n_valid_instructions"],
                    }
                    for c in case_data
                    if c in gap_data
                },
                "gap_valid_plus",
                weight_field="n_valid_instructions",
            )
            avg_mon = _weighted(
                {
                    c: (
                        {
                            "avg_monitors": mon_data[c]["avg_monitors"],
                            "n_instructions": case_data[c]["n_instructions"],
                        }
                        if "n_instructions" in case_data[c]
                        else {"avg_monitors": mon_data[c]["avg_monitors"]}
                    )
                    for c in case_data
                    if c in mon_data
                },
                "avg_monitors",
            ) if any(c in mon_data for c in case_data) else 0.0
            avg_per_unc = _weighted(
                {
                    c: (
                        {
                            "avg_monitors_per_unc": mon_data[c][
                                "avg_monitors_per_unc"
                            ],
                            "n_instructions": case_data[c]["n_instructions"],
                        }
                        if "n_instructions" in case_data[c]
                        else {
                            "avg_monitors_per_unc": mon_data[c][
                                "avg_monitors_per_unc"
                            ],
                        }
                    )
                    for c in case_data
                    if c in mon_data
                },
                "avg_monitors_per_unc",
            ) if any(c in mon_data for c in case_data) else 0.0

            prior_cell = (
                rf"\multirow{{{len(present_etas)}}}{{*}}{{\textbf{{{INIT_PRIOR_LABEL[prior]}}}}}"
                if eta_idx == 0 else ""
            )
            lines.append(
                f"{prior_cell} & ${eta}$ & "
                f"{_tex(tsr, nd=1, bold=abs(tsr - 100.0) < 1e-6)} & "
                f"{_tex(gap, nd=1)} & "
                f"{_tex(avg_per_unc, nd=2)} & "
                f"{_tex(avg_mon, nd=2)} \\\\\n"
            )
        if prior_idx != len(present_priors) - 1:
            lines.append(r"\midrule" "\n")

    lines.append(r"\bottomrule" "\n")
    lines.append(r"\end{tabular}" "\n")
    return "".join(lines)


def build_overall_tex(
    summary: dict[str, Any],
    monitors: dict[str, dict[str, dict[str, float]]],
    valid_gaps: dict[str, dict[str, dict[str, float | int]]],
) -> str:
    tabular = _overall_tabular(summary, monitors, valid_gaps)
    return (
        r"\begin{table}[t]" "\n"
        r"\centering" "\n"
        r"{\small" "\n"
        r"\setlength{\tabcolsep}{4.5pt}" "\n"
        r"\renewcommand{\arraystretch}{1.05}" "\n"
        + tabular
        + "}\n"
        r"\caption{Eta-sensitivity results (constant GT, DEFAULT planner, $W{=}D{=}10$). "
        r"Rows aggregate over all four task-complexity cases. "
        r"Higher TCSR and lower Gap$^{+}$ / monitor counts are better. "
        r"Gap$^{+}$ averages $\max(0,\text{makespan}-\text{oracle})$ over "
        r"instructions with TCSR\,=\,100\%; cells with no valid instruction are shown as --. "
        r"Bold: TCSR\,=\,100\%.}"
        "\n"
        r"\label{tab:eta_sensitivity_overall}"
        "\n"
        r"\end{table}"
        "\n"
    )


# ---------------------------------------------------------------------------
# By-case table  (rows: prior × case;  eta values as sub-columns per metric)
# ---------------------------------------------------------------------------

def _by_case_tabular(
    summary: dict[str, Any],
    monitors: dict[str, dict[str, dict[str, float]]],
    valid_gaps: dict[str, dict[str, dict[str, float | int]]],
) -> str:
    """Render a tabular with rows = (prior, case) and three eta sub-columns per metric."""

    present_priors = [p for p in INIT_PRIOR_ORDER if any(
        _setting_key(p, eta) in summary for eta in ETA_ORDER
    )]
    # use only etas that are present for at least one prior
    present_etas = [eta for eta in ETA_ORDER if any(
        _setting_key(p, eta) in summary for p in INIT_PRIOR_ORDER
    )]
    n_eta = len(present_etas)
    eta_header = " & ".join(rf"$\eta{{=}}{e}$" for e in present_etas)

    col_spec = "ll|" + "|".join("r" * n_eta for _ in range(3))  # prior, case | 3 metric groups
    lines: list[str] = []
    lines.append(rf"\begin{{tabular}}{{@{{}}{col_spec}@{{}}}}" "\n")
    lines.append(r"\toprule" "\n")

    # header row 1: metric group labels
    lines.append(
        r"\multirow{2}{*}{\textbf{Init Prior}} & \multirow{2}{*}{\textbf{Case}} & "
        rf"\multicolumn{{{n_eta}}}{{c}}{{\textbf{{TCSR (\%)}} ($\uparrow$)}} & "
        rf"\multicolumn{{{n_eta}}}{{c}}{{\textbf{{Gap$^{{+}}$ (s)}} ($\downarrow$)}} & "
        rf"\multicolumn{{{n_eta}}}{{c}}{{\textbf{{Mon./Int.}}}} \\" "\n"
    )
    # cmidrule positions
    def _cmidrule(start: int, end: int) -> str:
        return rf"\cmidrule(lr){{{start}-{end}}}"
    c1, c2 = 3, 2 + n_eta
    c3, c4 = c2 + 1, c2 + n_eta
    c5, c6 = c4 + 1, c4 + n_eta
    lines.append(f"{_cmidrule(c1,c2)}{_cmidrule(c3,c4)}{_cmidrule(c5,c6)}\n")

    # header row 2: eta values repeated per metric group
    eta_cols = " & ".join(rf"${e}$" for e in present_etas)
    lines.append(f"& & {eta_cols} & {eta_cols} & {eta_cols} \\\\\n")
    lines.append(r"\midrule" "\n")

    for prior_idx, prior in enumerate(present_priors):
        for case_idx, (case_name, case_label) in enumerate(CASES):
            prior_cell = (
                rf"\multirow{{{len(CASES)}}}{{*}}{{\textbf{{{INIT_PRIOR_LABEL[prior]}}}}}"
                if case_idx == 0 else ""
            )
            tsr_vals, gap_vals, unc_vals = [], [], []
            for eta in present_etas:
                key = _setting_key(prior, eta)
                m = summary.get(key, {}).get(case_name, {})
                mon = monitors.get(key, {}).get(case_name, {})
                gap_info = valid_gaps.get(key, {}).get(case_name, {})
                tsr_vals.append(float(m.get("tsr", 0.0)))
                gap_value = gap_info.get("gap_valid_plus")
                gap_vals.append(float(gap_value) if gap_value is not None else None)
                unc_vals.append(float(mon.get("avg_monitors_per_unc", 0.0)))

            tsr_cells = _rank_format(tsr_vals, nd=1, higher_is_better=True)
            gap_cells = _rank_format(gap_vals, nd=1, higher_is_better=False)
            unc_cells = [_tex(v, nd=2) for v in unc_vals]

            lines.append(
                f"{prior_cell} & \\textbf{{{case_label}}} & "
                f"{' & '.join(tsr_cells)} & "
                f"{' & '.join(gap_cells)} & "
                f"{' & '.join(unc_cells)} \\\\\n"
            )

        if prior_idx != len(present_priors) - 1:
            lines.append(r"\midrule" "\n")

    lines.append(r"\bottomrule" "\n")
    lines.append(r"\end{tabular}" "\n")
    return "".join(lines)


def build_by_case_tex(
    summary: dict[str, Any],
    monitors: dict[str, dict[str, dict[str, float]]],
    valid_gaps: dict[str, dict[str, dict[str, float | int]]],
) -> str:
    tabular = _by_case_tabular(summary, monitors, valid_gaps)
    return (
        r"\begin{table*}[t]" "\n"
        r"\centering" "\n"
        r"{\small" "\n"
        r"\setlength{\tabcolsep}{4.2pt}" "\n"
        r"\renewcommand{\arraystretch}{1.05}" "\n"
        r"\resizebox{\linewidth}{!}{%" "\n"
        + tabular
        + "}\n"
        "}\n"
        r"\caption{Eta-sensitivity results per prior-misspecification regime and "
        r"task-complexity case (constant GT, DEFAULT planner, $W{=}D{=}10$). "
        r"Each metric shows three values for $\eta\in\{0.01,0.1,0.9\}$. "
        r"Gap$^{+}$ averages $\max(0,\text{makespan}-\text{oracle})$ over "
        r"instructions with TCSR\,=\,100\%; cells with no valid instruction are shown as --. "
        r"Bold: best $\eta$ per row for TCSR / Gap$^{+}$; underline: second-best. "
        r"Mon./Int. is reported for reference only and is not highlighted.}"
        "\n"
        r"\label{tab:eta_sensitivity_by_case}"
        "\n"
        r"\end{table*}"
        "\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_SUMMARY,
        help="Path to offline_analysis_summary.json.",
    )
    parser.add_argument(
        "--batch-root",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_BATCH_ROOT,
        help="Batch results root directory (for monitor counts).",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=None,
        help="Path to offline_comparison_raw.json. Defaults to a sibling of --summary.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_OUT_DIR,
    )
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    monitors = load_monitor_summary(args.batch_root)
    raw_path = args.raw or args.summary.with_name("offline_comparison_raw.json")
    valid_gaps = load_valid_gap_summary(raw_path)

    # warn about any missing keys (OVER_ESTIMATE may not exist yet)
    for prior in INIT_PRIOR_ORDER:
        for eta in ETA_ORDER:
            key = _setting_key(prior, eta)
            if key not in summary:
                print(f"[warn] missing in summary, will be skipped: {key}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    overall_path = args.out_dir / "eta_sensitivity_overall.tex"
    by_case_path = args.out_dir / "eta_sensitivity_by_case.tex"

    overall_path.write_text(
        build_overall_tex(summary, monitors, valid_gaps),
        encoding="utf-8",
    )
    by_case_path.write_text(
        build_by_case_tex(summary, monitors, valid_gaps),
        encoding="utf-8",
    )
    print(overall_path)
    print(by_case_path)


if __name__ == "__main__":
    main()
