"""Render polished factor-alpha eta-sensitivity comparison tables from result JSONs.

Outputs two LaTeX tables:
- overall: weighted average across all task cases for each (prior, eta)
- by_case: detailed comparison for each (prior, eta, task case)
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_LEFT = (
    "assets/results/offline_exp_result/factor_alpha_001/"
    "analysis/eta_sensitivity/offline_analysis_summary.json"
)
DEFAULT_RIGHT = (
    "assets/results/offline_exp_result/factor_alpha_0001/"
    "analysis/eta_sensitivity/offline_analysis_summary.json"
)
DEFAULT_LEFT_BATCH_ROOT = (
    "assets/results/offline_exp_result/factor_alpha_001/"
    "offline_batch_eta_sensitivity"
)
DEFAULT_RIGHT_BATCH_ROOT = (
    "assets/results/offline_exp_result/factor_alpha_0001/"
    "offline_batch_eta_sensitivity"
)
DEFAULT_OUT_DIR = (
    "assets/results/offline_exp_result/factor_alpha_comparison/latex_tables"
)

INIT_PRIOR_ORDER: list[str] = [
    "CORRECT_ESTIMATE",
    "OVER_ESTIMATE",
    "UNDER_ESTIMATE",
]

INIT_PRIOR_LABEL: dict[str, str] = {
    "CORRECT_ESTIMATE": "Correct",
    "OVER_ESTIMATE": "Over",
    "UNDER_ESTIMATE": "Under",
}

ETA_ORDER: list[str] = ["0.01", "0.1", "0.5", "0.9"]

CASES: list[tuple[str, str]] = [
    ("tasks_2_constraints_1", "T2C1"),
    ("tasks_2_constraints_2", "T2C2"),
    ("tasks_3_constraints_1", "T3C1"),
    ("tasks_3_constraints_2", "T3C2"),
]


def _setting_key(init_prior: str, eta: str) -> str:
    return f"{init_prior}__bayesian__DEFAULT__w10_d10__eta{eta}"


def _eta_token(value: object) -> str:
    return f"{float(value):g}"


def _tex_num(x: float, nd: int = 1) -> str:
    return f"${x:.{nd}f}$"


def _pair(a: float, b: float, *, higher: bool, digits: int = 1) -> str:
    if abs(a - b) < 1e-9:
        return rf"{{\boldmath {_tex_num(a, digits)}}} & {{\boldmath {_tex_num(b, digits)}}}"
    better_left = a > b if higher else a < b
    if better_left:
        return rf"{{\boldmath {_tex_num(a, digits)}}} & {_tex_num(b, digits)}"
    return rf"{_tex_num(a, digits)} & {{\boldmath {_tex_num(b, digits)}}}"


def _weighted_metric(case_metrics: Mapping[str, Mapping[str, float]], field: str) -> float:
    weighted_sum = 0.0
    total = 0
    for metrics in case_metrics.values():
        n = int(metrics["n_instructions"])
        weighted_sum += n * float(metrics[field])
        total += n
    if total <= 0:
        raise ValueError(f"No instructions available for field '{field}'.")
    return weighted_sum / total


@lru_cache(maxsize=None)
def _count_initial_uncontrollable_targets(
    case_name: str,
    scene_name: str,
    instruction_name: str,
) -> int:
    """Count initial positive-length critical target nodes in the tDAG.

    A target is counted when it has at least one incoming critical edge whose
    interval is strictly positive in the initial task graph used by the rollout.
    """

    from src.utils.config.constants import EPSILON
    from src.utils.io_utils.task_io import load_task_data_from_sampled_set
    from src.utils.task.task_util import TaskUtil

    task_data = load_task_data_from_sampled_set(
        case_name,
        scene_name,
        instruction_name,
    )
    _subtasks, constraints, _bayesian_load = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{scene_name}_physics_environment.json",
    )
    targets = {
        end_name
        for _, end_name, data in constraints.edges(data=True)
        if data.get("info", {}).get("IsCritical")
        and float(data.get("info", {}).get("Interval", 0.0)) > EPSILON
    }
    return len(targets)


def load_monitor_summary(
    batch_root: Path,
) -> dict[str, dict[str, dict[str, float]]]:
    """Compute monitor aggregates per (setting, case) from saved batch results."""

    buckets: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for path in batch_root.rglob("*.json"):
        if "_batch_summary" in path.parts:
            continue

        payload = json.loads(path.read_text(encoding="utf-8"))
        meta_data = payload.get("meta_data", {})
        if not isinstance(meta_data, dict):
            continue
        if meta_data.get("suite_name") != "eta_sensitivity":
            continue
        if meta_data.get("ablation_config") != "DEFAULT":
            continue
        if int(meta_data.get("beam_width", -1)) != 10:
            continue
        if int(meta_data.get("beam_depth", -1)) != 10:
            continue

        init_prior = meta_data.get("init_prior_config")
        eta = meta_data.get("eta")
        case_name = payload.get("case")
        scene_name = payload.get("scene_name")
        instruction_name = payload.get("instruction")
        monitor_count = payload.get("actual_monitor_count_total")
        monitor_count_by_interval = payload.get("actual_monitor_count_by_interval")

        if (
            init_prior is None
            or eta is None
            or case_name is None
            or scene_name is None
            or instruction_name is None
            or monitor_count is None
            or not isinstance(monitor_count_by_interval, dict)
        ):
            continue

        uncontrollable_target_count = _count_initial_uncontrollable_targets(
            str(case_name),
            str(scene_name),
            str(instruction_name),
        )
        per_uncontrollable_target = (
            float(monitor_count) / uncontrollable_target_count
            if uncontrollable_target_count > 0
            else 0.0
        )
        key = _setting_key(str(init_prior), _eta_token(eta))
        buckets.setdefault(key, {}).setdefault(str(case_name), []).append(
            (float(monitor_count), per_uncontrollable_target)
        )

    summary: dict[str, dict[str, dict[str, float]]] = {}
    for key, case_buckets in buckets.items():
        summary[key] = {
            case_name: {
                "avg_monitors": sum(total for total, _ in values) / len(values),
                "avg_monitors_per_uncontrollable_target": (
                    sum(per_target for _, per_target in values) / len(values)
                ),
            }
            for case_name, values in case_buckets.items()
            if values
        }
    return summary


def build_overall_summary(
    summary: Mapping[str, Mapping[str, Mapping[str, float]]],
) -> dict[str, dict[str, float]]:
    """Collapse one eta-sensitivity summary into overall rows."""

    overall: dict[str, dict[str, float]] = {}
    for init_prior in INIT_PRIOR_ORDER:
        for eta in ETA_ORDER:
            key = _setting_key(init_prior, eta)
            case_metrics = summary[key]
            overall[key] = {
                "tsr": _weighted_metric(case_metrics, "tsr"),
                "makespan_gap": _weighted_metric(case_metrics, "makespan_gap"),
                "computation_time": _weighted_metric(case_metrics, "computation_time"),
            }
    return overall


def _build_overall_tabular(
    left: Mapping[str, Mapping[str, Mapping[str, float]]],
    right: Mapping[str, Mapping[str, Mapping[str, float]]],
    left_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    right_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Render one compact tabular aggregated across task cases."""

    left_overall = build_overall_summary(left)
    right_overall = build_overall_summary(right)
    head = (
        r"\begin{tabular}{@{}llrrrrrrrr@{}}"
        "\n\\toprule\n"
        r"\multirow{2}{*}{\textbf{Init Prior}} & \multirow{2}{*}{\textbf{$\eta$}} & "
        r"\multicolumn{2}{c}{\textbf{TCSR} ($\uparrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Gap} ($\downarrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Avg. Mon. / Unctrl. Int.} ($\downarrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Avg. Mon.} ($\downarrow$)} \\"
        "\n"
        r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}\cmidrule(lr){9-10}"
        "\n"
        rf"& & \textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} \\"
        "\n\\midrule\n"
    )
    rows: list[str] = []
    for prior_index, init_prior in enumerate(INIT_PRIOR_ORDER):
        for eta_index, eta in enumerate(ETA_ORDER):
            key = _setting_key(init_prior, eta)
            xl = left_overall[key]
            xr = right_overall[key]
            mil = _weighted_metric(
                {
                    case_name: {
                        "avg_monitors_per_uncontrollable_target": left_monitors[key][
                            case_name
                        ]["avg_monitors_per_uncontrollable_target"],
                        "n_instructions": left[key][case_name]["n_instructions"],
                    }
                    for case_name, _ in CASES
                },
                "avg_monitors_per_uncontrollable_target",
            )
            mir = _weighted_metric(
                {
                    case_name: {
                        "avg_monitors_per_uncontrollable_target": right_monitors[key][
                            case_name
                        ]["avg_monitors_per_uncontrollable_target"],
                        "n_instructions": right[key][case_name]["n_instructions"],
                    }
                    for case_name, _ in CASES
                },
                "avg_monitors_per_uncontrollable_target",
            )
            ml = _weighted_metric(
                {
                    case_name: {
                        "avg_monitors": left_monitors[key][case_name]["avg_monitors"],
                        "n_instructions": left[key][case_name]["n_instructions"],
                    }
                    for case_name, _ in CASES
                },
                "avg_monitors",
            )
            mr = _weighted_metric(
                {
                    case_name: {
                        "avg_monitors": right_monitors[key][case_name]["avg_monitors"],
                        "n_instructions": right[key][case_name]["n_instructions"],
                    }
                    for case_name, _ in CASES
                },
                "avg_monitors",
            )
            prior_prefix = (
                rf"\multirow{{4}}{{*}}{{\textbf{{{INIT_PRIOR_LABEL[init_prior]}}}}}"
                if eta_index == 0
                else ""
            )
            rows.append(
                f"{prior_prefix} & ${eta}$ & "
                f"{_pair(xl['tsr'], xr['tsr'], higher=True, digits=1)} & "
                f"{_pair(xl['makespan_gap'], xr['makespan_gap'], higher=False, digits=1)} & "
                f"{_pair(mil, mir, higher=False, digits=2)} & "
                f"{_pair(ml, mr, higher=False, digits=2)}"
                " \\\\\n"
            )
        if prior_index != len(INIT_PRIOR_ORDER) - 1:
            rows.append("\\midrule\n")
    return head + "".join(rows) + "\\bottomrule\n\\end{tabular}\n"


def build_overall_tex(
    left: Mapping[str, Mapping[str, Mapping[str, float]]],
    right: Mapping[str, Mapping[str, Mapping[str, float]]],
    left_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    right_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Render one wrapped LaTeX table aggregated across task cases."""

    tabular = _build_overall_tabular(
        left,
        right,
        left_monitors,
        right_monitors,
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
        r"\caption{Factor-alpha comparison under the eta-sensitivity suite "
        r"(constant GT duration, DEFAULT monitored planner, and $W{=}D{=}10$). "
        r"Each row aggregates over all four task-complexity cases. "
        r"Higher TCSR is better, while lower oracle gap, lower average monitors per initial uncontrollable interval target, "
        r"and lower average monitors per episode are better. "
        r"Bold marks the better alpha in each row pair.}"
        "\n"
        r"\label{tab:factor_alpha_eta_sensitivity_overall}"
        "\n"
        r"\end{table}"
        "\n"
    )


def _build_by_case_tabular(
    left: Mapping[str, Mapping[str, Mapping[str, float]]],
    right: Mapping[str, Mapping[str, Mapping[str, float]]],
    left_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    right_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Render a detailed tabular for each (prior, eta, case) row."""

    head = (
        r"\begin{tabular}{@{}lllrrrrrrrr@{}}"
        "\n\\toprule\n"
        r"\multirow{2}{*}{\textbf{Init Prior}} & \multirow{2}{*}{\textbf{$\eta$}} & \multirow{2}{*}{\textbf{Task}} & "
        r"\multicolumn{2}{c}{\textbf{TCSR} ($\uparrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Gap} ($\downarrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Avg. Mon. / Unctrl. Int.} ($\downarrow$)} & "
        r"\multicolumn{2}{c}{\textbf{Avg. Mon.} ($\downarrow$)} \\"
        "\n"
        r"\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}\cmidrule(lr){10-11}"
        "\n"
        rf"& & & \textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} & "
        rf"\textbf{{{label_left}}} & \textbf{{{label_right}}} \\"
        "\n\\midrule\n"
    )
    rows: list[str] = []
    for prior_index, init_prior in enumerate(INIT_PRIOR_ORDER):
        for eta_index, eta in enumerate(ETA_ORDER):
            key = _setting_key(init_prior, eta)
            for case_index, (case_name, case_label) in enumerate(CASES):
                xl = left[key][case_name]
                xr = right[key][case_name]
                mil = left_monitors[key][case_name][
                    "avg_monitors_per_uncontrollable_target"
                ]
                mir = right_monitors[key][case_name][
                    "avg_monitors_per_uncontrollable_target"
                ]
                ml = left_monitors[key][case_name]["avg_monitors"]
                mr = right_monitors[key][case_name]["avg_monitors"]
                prior_prefix = (
                    rf"\multirow{{16}}{{*}}{{\textbf{{{INIT_PRIOR_LABEL[init_prior]}}}}}"
                    if eta_index == 0 and case_index == 0
                    else ""
                )
                eta_prefix = (
                    rf"\multirow{{4}}{{*}}{{${eta}$}}" if case_index == 0 else ""
                )
                rows.append(
                    f"{prior_prefix} & {eta_prefix} & \\textbf{{{case_label}}} & "
                    f"{_pair(xl['tsr'], xr['tsr'], higher=True, digits=1)} & "
                    f"{_pair(xl['makespan_gap'], xr['makespan_gap'], higher=False, digits=1)} & "
                    f"{_pair(mil, mir, higher=False, digits=2)} & "
                    f"{_pair(ml, mr, higher=False, digits=2)}"
                    " \\\\\n"
                )
            if eta_index != len(ETA_ORDER) - 1:
                rows.append("\\addlinespace[2pt]\n")
        if prior_index != len(INIT_PRIOR_ORDER) - 1:
            rows.append("\\midrule\n")
    return head + "".join(rows) + "\\bottomrule\n\\end{tabular}\n"


def build_by_case_tex(
    left: Mapping[str, Mapping[str, Mapping[str, float]]],
    right: Mapping[str, Mapping[str, Mapping[str, float]]],
    left_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    right_monitors: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    label_left: str,
    label_right: str,
) -> str:
    """Render a wrapped detailed LaTeX table for each (prior, eta, case) row."""

    tabular = _build_by_case_tabular(
        left,
        right,
        left_monitors,
        right_monitors,
        label_left=label_left,
        label_right=label_right,
    )
    return (
        r"\begin{table*}[t]" "\n"
        r"\centering" "\n"
        r"{\small" "\n"
        r"\setlength{\tabcolsep}{4.2pt}" "\n"
        r"\renewcommand{\arraystretch}{1.04}" "\n"
        r"\resizebox{\linewidth}{!}{%" "\n"
        + tabular
        + "}\n"
        + "}\n"
        r"\caption{Detailed factor-alpha comparison under the eta-sensitivity suite "
        r"for each prior-misspecification regime, eta value, and task-complexity case. "
        r"Higher TCSR is better, while lower oracle gap, lower average monitors per initial uncontrollable interval target, "
        r"and lower average monitors per episode are better. "
        r"Bold marks the better alpha in each row pair.}"
        "\n"
        r"\label{tab:factor_alpha_eta_sensitivity_by_case}"
        "\n"
        r"\end{table*}"
        "\n"
    )


def _validate_summary(summary: Mapping[str, Any]) -> None:
    missing = [
        _setting_key(init_prior, eta)
        for init_prior in INIT_PRIOR_ORDER
        for eta in ETA_ORDER
        if _setting_key(init_prior, eta) not in summary
    ]
    if missing:
        raise SystemExit(f"Missing keys: {missing}")


def _validate_monitor_summary(
    monitor_summary: Mapping[str, Mapping[str, Mapping[str, float]]],
) -> None:
    missing = [
        f"{_setting_key(init_prior, eta)}::{case_name}"
        for init_prior in INIT_PRIOR_ORDER
        for eta in ETA_ORDER
        for case_name, _ in CASES
        if _setting_key(init_prior, eta) not in monitor_summary
        or case_name not in monitor_summary[_setting_key(init_prior, eta)]
    ]
    if missing:
        raise SystemExit(f"Missing monitor counts: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, default=PROJECT_ROOT / DEFAULT_LEFT)
    parser.add_argument("--right", type=Path, default=PROJECT_ROOT / DEFAULT_RIGHT)
    parser.add_argument(
        "--left-batch-root",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_LEFT_BATCH_ROOT,
    )
    parser.add_argument(
        "--right-batch-root",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_RIGHT_BATCH_ROOT,
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_OUT_DIR,
    )
    parser.add_argument("--label-left", default=r"$\alpha{=}0.01$")
    parser.add_argument("--label-right", default=r"$\alpha{=}0.001$")
    args = parser.parse_args()

    left = json.loads(args.left.read_text(encoding="utf-8"))
    right = json.loads(args.right.read_text(encoding="utf-8"))
    left_monitors = load_monitor_summary(args.left_batch_root)
    right_monitors = load_monitor_summary(args.right_batch_root)
    _validate_summary(left)
    _validate_summary(right)
    _validate_monitor_summary(left_monitors)
    _validate_monitor_summary(right_monitors)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    overall_path = args.out_dir / "eta_sensitivity_factor_alpha_001_vs_0001_overall.tex"
    by_case_path = args.out_dir / "eta_sensitivity_factor_alpha_001_vs_0001_by_case.tex"

    overall_path.write_text(
        build_overall_tex(
            left,
            right,
            left_monitors,
            right_monitors,
            label_left=args.label_left,
            label_right=args.label_right,
        ),
        encoding="utf-8",
    )
    by_case_path.write_text(
        build_by_case_tex(
            left,
            right,
            left_monitors,
            right_monitors,
            label_left=args.label_left,
            label_right=args.label_right,
        ),
        encoding="utf-8",
    )
    print(overall_path)
    print(by_case_path)


if __name__ == "__main__":
    main()
