"""
Process experiment summary data and generate a LaTeX table.

This script performs two main functions:
1.  Revises a raw JSON summary file by aggregating results based on task length.
    It calculates the average metrics (SR, TSR, makespan) across different
    constraints for tasks of the same length.
2.  Generates a LaTeX table from the revised summary, comparing different
    scheduling approaches and highlighting the best-performing ones.

The script is intended to be run from the command line, taking the path to the
input summary file as an argument.
"""

import argparse
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Configuration Constants ---

# Order of initial time estimates for table columns
INIT_ORDER: List[str] = ["init_60", "init_80", "init_100", "init_120", "init_140"]

# Display names for different methods/approaches
METHOD_DISPLAY_NAMES: Dict[str, str] = {
    "dag_bayesian_DEFAULT": "Ours",
    "dag_bayesian_GREEDY": "Ours (Greedy)",
    "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
    "dag_bayesian_NONE_URGENCY": "Ours (w/o Urg.)",
    "dag_bayesian_NONE_REMAINING_WORK": "Ours (w/o Rem.)",
    "dag_edf": "EDF",
    "cpm": "CPM",
    "progprompt": "ProgPrompt",
    "cap_ai2thor_simulation": "CAP",
}

# Methods to be included in the main comparison table and their order
MAIN_METHODS: List[str] = [
    "dag_edf",
    "cpm",
    "progprompt",
    "cap_ai2thor_simulation",
    "dag_bayesian_DEFAULT",
]

# Key for the ablation study method
ABLATION_METHOD_KEY: str = "dag_bayesian_NONE_MONITORING"

# Order and labels for task difficulties (based on number of subtasks)
TASK_ORDER: List[str] = ["tasks_2", "tasks_3", "tasks_4"]
TASK_DISPLAY_NAMES: Dict[str, str] = {
    "tasks_2": "Simple",
    "tasks_3": "Medium",
    "tasks_4": "Complex",
}

# Approaches to exclude from the final analysis
APPROACHES_TO_EXCLUDE: List[str] = [
    "dag_bayesian_GREEDY",
    "dag_bayesian_NONE_URGENCY",
    "dag_bayesian_NONE_REMAINING_WORK",
]


# --- Argument Parsing ---


def load_argument_parser() -> argparse.Namespace:
    """Set up and parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Process summary data and generate a LaTeX table."
    )
    parser.add_argument(
        "--summary_file_path",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "results"
        / "unified_analysis_summary.json",
        help="Path to the input JSON summary file.",
    )
    parser.add_argument(
        "--save_revised_summary",
        action="store_true",
        help="If set, save the intermediate revised summary to a '.revised.json' file.",
    )
    return parser.parse_args()


# --- Data Processing Functions ---


def reorder_metrics_dict(data: Dict[str, float]) -> "OrderedDict[str, float]":
    """Reorder metric keys in a dictionary for consistent output.

    Args:
        data (Dict[str, float]): A dictionary of metrics.

    Returns:
        OrderedDict[str, float]: The dictionary with sorted keys.
    """
    metric_order = ["sr", "tsr", "makespan"]
    return OrderedDict([(k, data[k]) for k in metric_order if k in data])


def merge_by_task_length(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate summary metrics by task length.

    This function processes a summary dictionary, identifies task cases like
    "tasks_<n>_constraints_<m>", and averages their metrics across all
    constraint variations for each task length 'n'.
    
    Note: TSR (Timing Success Rate) is only calculated for constraints >= 1,
    excluding constraints_0 cases.

    Args:
        summary (Dict[str, Any]): The raw summary data structured as
            summary[approach][task_case]["init"][init_case] = metrics.

    Returns:
        Dict[str, Any]: A new summary dictionary with metrics aggregated
            by task length, structured as
            merged[approach]["tasks_<n>"][init_case] = averaged_metrics.
    """
    sums: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    )
    counts: Dict[str, Dict[str, Dict[str, Dict[str, int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    )

    for approach, task_cases in summary.items():
        for task_case, task_data in task_cases.items():
            match = re.match(r"tasks_(\d+)_constraints_(\d+)", task_case)
            if not match:
                continue

            tasks_num = int(match.group(1))
            constraints_num = int(match.group(2))
            tasks_key = f"tasks_{tasks_num}"
            init_dict = task_data.get("init", {})

            if not isinstance(init_dict, dict):
                continue

            # TSR은 constraint >= 1인 경우에만 계산
            include_tsr = constraints_num >= 1

            for init_case, metrics in init_dict.items():
                for metric_name, value in metrics.items():
                    # TSR의 경우 constraint >= 1일 때만 합산
                    if metric_name == "tsr" and not include_tsr:
                        continue
                    
                    sums[approach][tasks_key][init_case][metric_name] += value
                    counts[approach][tasks_key][init_case][metric_name] += 1

    merged_summary: Dict[str, Any] = defaultdict(dict)
    for approach, tasks_dict in sums.items():
        for tasks_key, init_dict in tasks_dict.items():
            merged_summary[approach][tasks_key] = {}
            for init_case, metric_sums in init_dict.items():
                avg_metrics: Dict[str, float] = {}
                
                for metric_name, total in metric_sums.items():
                    count = counts[approach][tasks_key][init_case][metric_name]
                    if count > 0:
                        avg_metrics[metric_name] = total / count
                
                # TSR이 metric_sums에 없는 경우 (constraint >= 1인 데이터가 없음)
                # 다른 메트릭들은 있지만 TSR만 없는 경우를 처리
                if "tsr" not in avg_metrics and metric_sums:
                    # 다른 메트릭들이 있다면 TSR을 0으로 설정
                    avg_metrics["tsr"] = 0.0

                if not avg_metrics:
                    continue

                # Rename 'gcr' to 'sr' for consistency
                if "gcr" in avg_metrics:
                    avg_metrics["sr"] = avg_metrics.pop("gcr")

                # Reorder and store
                merged_summary[approach][tasks_key][init_case] = reorder_metrics_dict(
                    avg_metrics
                )

    return dict(merged_summary)


# --- LaTeX Generation Functions ---


def find_best_values(data: Dict[str, Any]) -> Dict[Tuple[str, str, str], float]:
    """Identify the best metric values among main methods for highlighting.

    Compares only the methods listed in `MAIN_METHODS` to find the best
    (max for SR/TSR, min for makespan) value for each metric under each
    task and initial condition. This is used for bolding in the table.

    Args:
        data (Dict[str, Any]): The revised summary data.

    Returns:
        Dict[Tuple[str, str, str], float]: A dictionary mapping
            (task, init, metric) to the best value.
    """
    best_vals: Dict[Tuple[str, str, str], float] = {}

    for task in TASK_ORDER:
        for init in INIT_ORDER:
            # Collect values for comparison
            sr_vals = [
                data[method][task][init].get("sr", -1.0)
                for method in MAIN_METHODS
                if data.get(method, {}).get(task, {}).get(init)
            ]
            tsr_vals = [
                data[method][task][init].get("tsr", -1.0)
                for method in MAIN_METHODS
                if data.get(method, {}).get(task, {}).get(init)
            ]
            mk_vals = [
                data[method][task][init].get("makespan", float("inf"))
                for method in MAIN_METHODS
                if data.get(method, {}).get(task, {}).get(init)
            ]

            # Determine best values
            if sr_vals:
                best_vals[(task, init, "sr")] = max(sr_vals)
            if tsr_vals:
                best_vals[(task, init, "tsr")] = max(tsr_vals)
            if mk_vals:
                best_vals[(task, init, "makespan")] = min(mk_vals)

    return best_vals


def fmt_cell(
    main_val: Optional[float],
    metric: str,
    best_val: float,
    ablation_val: Optional[float] = None,
) -> str:
    """Format a single table cell with main value, bolding, and ablation study value.

    Args:
        main_val (Optional[float]): The primary metric value for the cell.
        metric (str): The name of the metric (e.g., 'sr', 'makespan').
        best_val (float): The best value for this metric across methods.
        ablation_val (Optional[float], optional): The corresponding value from
            the ablation study. Defaults to None.

    Returns:
        str: The formatted string for the LaTeX table cell.
    """
    if main_val is None:
        return "---"

    # Format the main value to one decimal place
    s_main = f"{main_val:.1f}"

    # Apply bolding if the main value is the best (within a small tolerance)
    if abs(main_val - best_val) < 0.001:
        s_main = f"\\textbf{{{s_main}}}"

    # Append ablation value in parentheses for TSR and Makespan
    if ablation_val is not None and metric != "sr":
        s_abl = f"{ablation_val:.1f}"
        return f"{s_main} ({s_abl})"

    return s_main


def generate_latex_table(data: Dict[str, Any]) -> str:
    """Generate the complete LaTeX code for the results table.

    Args:
        data (Dict[str, Any]): The revised and filtered summary data.

    Returns:
        str: A string containing the full LaTeX table code.
    """
    best_values = find_best_values(data)
    lines: List[str] = []

    # Header and Caption
    lines.extend(
        [
            r"\begin{table*}[t]",
            r"\centering",
            r"\caption{Performance comparison in the AI2-THOR simulation environment. "
            r"Results are aggregated by task complexity. "
            r"Values in parentheses indicate the performance of the ablation study \quotes{Ours (w/o Mon.)}. "
            r"Higher SR and TSR are better ($\uparrow$), and lower Makespan is better ($\downarrow$).}",
            r"\label{tab:simulation_results_merged}",
            r"{\renewcommand{\arraystretch}{1.1}",
            r"\resizebox{\textwidth}{!}{%",
            r"\begin{tabular}{@{}ll|ccc|ccc|ccc|ccc|ccc@{}}",
            r"\toprule",
        ]
    )

    # Column Headers
    lines.extend(
        [
            r"\multicolumn{2}{c|}{\multirow{2}{*}{\textbf{Method}}} & \multicolumn{3}{c|}{\textbf{Under-estimate (60s)}} & \multicolumn{3}{c|}{\textbf{Under-mid-estimate (80s)}} & \multicolumn{3}{c|}{\textbf{Correct (100s)}} & \multicolumn{3}{c|}{\textbf{Over-mid-estimate (120s)}} & \multicolumn{3}{c}{\textbf{Over-estimate (140s)}} \\",
            r"\cmidrule(l){3-5} \cmidrule(l){6-8} \cmidrule(l){9-11} \cmidrule(l){12-14} \cmidrule(l){15-17}",
            r"\multicolumn{2}{c|}{\textbf{Difficulty}} & \textbf{SR ($\uparrow$)} & \textbf{TSR ($\uparrow$)} & \textbf{Makespan ($\downarrow$)} & \textbf{SR ($\uparrow$)} & \textbf{TSR ($\uparrow$)} & \textbf{Makespan ($\downarrow$)} & \textbf{SR ($\uparrow$)} & \textbf{TSR ($\uparrow$)} & \textbf{Makespan ($\downarrow$)} & \textbf{SR ($\uparrow$)} & \textbf{TSR ($\uparrow$)} & \textbf{Makespan ($\downarrow$)} & \textbf{SR ($\uparrow$)} & \textbf{TSR ($\uparrow$)} & \textbf{Makespan ($\downarrow$)} \\",
            r"\midrule",
        ]
    )

    # Table Body
    for method_idx, method_key in enumerate(MAIN_METHODS):
        method_label = METHOD_DISPLAY_NAMES.get(method_key, method_key)

        for task_idx, task_key in enumerate(TASK_ORDER):
            row_parts = []

            # Method Name Column (with multirow)
            if task_idx == 0:
                row_parts.append(f"\\multirow{{3}}{{*}}{{\\textbf{{{method_label}}}}}")
            else:
                # For subsequent rows in a multirow block, leave the first column empty.
                row_parts.append("")

            # Task Difficulty Column
            row_parts.append(
                f"\\textbf{{{TASK_DISPLAY_NAMES.get(task_key, task_key)}}}"
            )

            # Metric Columns
            for init_key in INIT_ORDER:
                metrics = data.get(method_key, {}).get(task_key, {}).get(init_key, {})
                sr = metrics.get("sr")
                tsr = metrics.get("tsr")
                mk = metrics.get("makespan")

                # Get ablation data if applicable
                abl_metrics = None
                if method_key == "dag_bayesian_DEFAULT":
                    abl_metrics = (
                        data.get(ABLATION_METHOD_KEY, {})
                        .get(task_key, {})
                        .get(init_key)
                    )

                abl_sr = abl_metrics.get("sr") if abl_metrics else None
                abl_tsr = abl_metrics.get("tsr") if abl_metrics else None
                abl_mk = abl_metrics.get("makespan") if abl_metrics else None

                # Get best values for comparison
                best_sr = best_values.get((task_key, init_key, "sr"), float("-inf"))
                best_tsr = best_values.get((task_key, init_key, "tsr"), float("-inf"))
                best_mk = best_values.get(
                    (task_key, init_key, "makespan"), float("inf")
                )

                # Format cells
                row_parts.append(fmt_cell(sr, "sr", best_sr, abl_sr))
                row_parts.append(fmt_cell(tsr, "tsr", best_tsr, abl_tsr))
                row_parts.append(fmt_cell(mk, "makespan", best_mk, abl_mk))

            lines.append(" & ".join(row_parts) + r" \\")

        if method_idx < len(MAIN_METHODS) - 1:
            lines.append(r"\midrule")

    # Footer
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"}",
            r"\end{table*}",
        ]
    )

    return "\n".join(lines)


# --- Main Execution ---


def main() -> None:
    """Run the main script execution pipeline."""
    args = load_argument_parser()

    # 1. Load data from the source file
    try:
        with open(args.summary_file_path, "r") as f:
            summary_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.summary_file_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {args.summary_file_path}")
        return

    # 2. Process and revise the summary
    revised_summary = merge_by_task_length(summary_data)

    # 3. Filter out excluded approaches
    for approach in APPROACHES_TO_EXCLUDE:
        revised_summary.pop(approach, None)

    # 4. Save the revised summary if requested
    if args.save_revised_summary:
        output_path = args.summary_file_path.with_suffix(".revised.json")
        with open(output_path, "w") as f:
            json.dump(revised_summary, f, indent=4)
        print(f"Revised summary saved to: {output_path}")

    # 5. Generate and print the LaTeX table
    latex_output = generate_latex_table(revised_summary)
    print("\n--- LaTeX Table Output ---\n")
    print(latex_output)


if __name__ == "__main__":
    main()
