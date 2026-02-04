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
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from assets.result_analysis.state_base_evaluation import state_base_eval

# --- Configuration Constants ---

# Metrics to include in the LaTeX table
# Options: "sr", "gcr", "tcsr", "makespan"
INCLUDED_METRICS: List[str] = [
    "sr",
    "gcr",
    "tcsr",
    "makespan",
]

# Order of initial time estimates (all possible values)
INIT_ORDER: List[str] = [
    "init_60",
    "init_70",
    "init_90",
    "init_80",
    "init_100",
    "init_110",
    "init_120",
    "init_130",
    "init_140",
]

# Display names for different methods/approaches
METHOD_DISPLAY_NAMES: Dict[str, str] = {
    "dag_bayesian_DEFAULT": "Ours",
    "dag_bayesian_GREEDY": "Ours (Greedy)",
    "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
    "dag_bayesian_NONE_URGENCY": "Ours (w/o Urg.)",
    "dag_bayesian_NONE_REMAINING_WORK": "Ours (w/o Rem.)",
    "dag_edf": "EDF",
    "cpm": "CPM",
    "progprompt": "Prog.",
    "cap_ai2thor_simulation": "CaP",
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
TASK_ORDER: List[str] = [
    "tasks_2_constraints_1",
    "tasks_2_constraints_2",
    "tasks_3_constraints_1",
    "tasks_3_constraints_2",
    # "tasks_4_constraints_1",
    # "tasks_4_constraints_2",
]
TASK_DISPLAY_NAMES: Dict[str, str] = {
    "tasks_2_constraints_1": "T2 C1",
    "tasks_2_constraints_2": "T2 C2",
    "tasks_3_constraints_1": "T3 C1",
    "tasks_3_constraints_2": "T3 C2",
    # "tasks_4_constraints_1": "Tasks 4 (C=1)",
    # "tasks_4_constraints_2": "Tasks 4 (C=2)",
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
    default_root_dir: Path = Path(__file__).resolve().parents[1] / "results"
    parser = argparse.ArgumentParser(
        description="Process summary data and generate a LaTeX table."
    )
    parser.add_argument(
        "--root_dir",
        type=Path,
        default=default_root_dir,
        help=f"Root directory to search for experiment folders. (default: {default_root_dir})",
    )
    parser.add_argument(
        "--ablation_style",
        type=str,
        default="new_row",
        choices=["parentheses", "new_row", "none"],
        help="Choose how to display ablation study results: 'parentheses' (inline), 'new_row' (separate row), or 'none' (exclude).",
    )
    parser.add_argument(
        "--group_by_task_length",
        action="store_true",
        help="Group results by task length (e.g., merge C1 and C2 into T2).",
    )
    parser.add_argument(
        "--output_json",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "results"
        / "unified_analysis_summary.revised.json",
        help="Path to save the merged JSON result.",
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
    # Define standard metric order (superset of potentially included metrics)
    standard_order = ["sr", "gcr", "tcsr", "makespan", "makespan_sr_1"]

    # Filter based on INCLUDED_METRICS and what's available in data
    # Using standard_order ensures consistent ordering regardless of INCLUDED_METRICS order
    keys_to_keep = [k for k in standard_order if k in data]

    return OrderedDict([(k, data[k]) for k in keys_to_keep])


def merge_by_task_length(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate summary metrics by task and constraint type.

    This function processes a summary dictionary and groups results by
    task length and constraint count (e.g., "tasks_2_constraints_1").

    Note: TCSR (Time Constraint Success Rate) is only calculated for constraints >= 1,
    excluding constraints_0 cases.

    Args:
        summary (Dict[str, Any]): The raw summary data structured as
            summary[approach][task_case]["init"][init_case] = metrics.

    Returns:
        Dict[str, Any]: A new summary dictionary with metrics aggregated
            by task/constraint, structured as
            merged[approach][task_constraint_key][init_case] = averaged_metrics.
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

            if constraints_num == 0:
                continue

            tasks_key = f"tasks_{tasks_num}_constraints_{constraints_num}"
            init_dict = task_data.get("init", {})

            if not isinstance(init_dict, dict):
                continue

            # TCSR은 constraint >= 1인 경우에만 계산
            include_tcsr = constraints_num >= 1

            for init_case, metrics in init_dict.items():
                for metric_name, value in metrics.items():
                    # Map 'tsr' to 'tcsr'
                    if metric_name == "tsr":
                        metric_name = "tcsr"

                    # TCSR의 경우 constraint >= 1일 때만 합산
                    if metric_name == "tcsr" and not include_tcsr:
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

                # TCSR이 metric_sums에 없는 경우 (constraint >= 1인 데이터가 없음)
                # 다른 메트릭들은 있지만 TCSR만 없는 경우를 처리
                if "tcsr" not in avg_metrics and metric_sums:
                    # 다른 메트릭들이 있다면 TCSR을 0으로 설정
                    avg_metrics["tcsr"] = 0.0

                if not avg_metrics:
                    continue

                # Reorder and store
                merged_summary[approach][tasks_key][init_case] = reorder_metrics_dict(
                    avg_metrics
                )

    return dict(merged_summary)


def process_experiment_folder(folder: Path) -> List[Dict[str, Any]]:
    """Process a single experiment folder.

    1. Check for 'unified_analysis_summary*.json'.
       - If missing, run state_base_eval(folder) to generate it.
    2. Load all matching 'unified_analysis_summary*.json', normalize with merge_by_task_length.

    Args:
        folder (Path): Path to the experiment folder.

    Returns:
        List[Dict[str, Any]]: A list of processed and normalized summary data dictionaries.
    """
    # Check if any unified summary exists (excluding revised ones)
    unified_files = [
        f
        for f in folder.glob("unified_analysis_summary*.json")
        if "revised" not in f.name
    ]

    if not unified_files:
        print(f"Generating summary for {folder}...")
        # Check if this folder looks like a valid experiment folder (has states*)
        if list(folder.glob("states*")):
            state_base_eval(folder)
            # Re-check for generated file
            unified_files = [
                f
                for f in folder.glob("unified_analysis_summary*.json")
                if "revised" not in f.name
            ]
        else:
            print(f"Skipping {folder}: No states folders found and no summary.")
            return []

    # 2. Load and Normalize all found summaries
    results = []
    for unified_path in unified_files:
        try:
            with open(unified_path, "r") as f:
                data = json.load(f)
            normalized = merge_by_task_length(data)
            results.append(normalized)
        except Exception as e:
            print(f"Error processing {unified_path}: {e}")

    return results


def is_experiment_folder(path: Path) -> bool:
    """Check if the given path is a valid single experiment folder.

    It is considered an experiment folder if:
    1. It contains 'unified_analysis_summary*.json' (excluding *.revised.json)
    2. OR it contains subdirectories named 'states*'
    """
    if any(
        "revised" not in f.name for f in path.glob("unified_analysis_summary*.json")
    ):
        return True
    if list(path.glob("states*")):
        return True
    return False


def collect_and_aggregate(
    root_dir: Path, group_by_task_length: bool = False
) -> Dict[str, Any]:
    """Discover experiment folders and aggregate their results.

    Handles two cases:
    1. root_dir is itself a single experiment folder.
    2. root_dir is a container for multiple experiment folders.

    Args:
        root_dir (Path): Root directory to search.
        group_by_task_length (bool): Whether to group results by task length.

    Returns:
        Dict[str, Any]: Aggregated data with (mean, std) for each metric.
    """
    collector: Dict[str, Dict[str, Dict[str, Dict[str, List[float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )

    valid_folders = []

    # Case 1: root_dir is a single experiment folder
    if is_experiment_folder(root_dir):
        print(f"Processing single experiment folder: {root_dir}")
        valid_folders.append(root_dir)

    # Case 2: root_dir is a container for multiple experiment folders
    else:
        potential_folders = [f for f in root_dir.iterdir() if f.is_dir()]
        for folder in potential_folders:
            if is_experiment_folder(folder):
                valid_folders.append(folder)

        if not valid_folders:
            print(f"No experiment folders found in {root_dir}")
            return {}

        print(
            f"Found {len(valid_folders)} experiment folders in container: {[f.name for f in valid_folders]}"
        )

    # Process all identified folders
    for folder in valid_folders:
        data_list = process_experiment_folder(folder)
        if not data_list:
            continue

        for data in data_list:
            # Collect values
            for approach, tasks in data.items():
                if approach in APPROACHES_TO_EXCLUDE:
                    continue

                for task_key, inits in tasks.items():
                    if group_by_task_length:
                        match = re.match(r"(tasks_\d+)_constraints_\d+", task_key)
                        if match:
                            task_key = match.group(1)

                    for init_case, metrics in inits.items():
                        for metric, value in metrics.items():
                            collector[approach][task_key][init_case][metric].append(
                                value
                            )

    # Compute Statistics
    # If it was a single folder, std will be 0.0 for all metrics.
    aggregated: Dict[str, Any] = defaultdict(dict)
    for approach, tasks in collector.items():
        for task_key, inits in tasks.items():
            aggregated[approach][task_key] = {}
            for init_case, metrics in inits.items():
                aggregated[approach][task_key][init_case] = {}
                for metric, values in metrics.items():
                    mean_val = np.mean(values)
                    std_val = np.std(values)
                    aggregated[approach][task_key][init_case][metric] = (
                        mean_val,
                        std_val,
                    )

    return dict(aggregated)


# --- LaTeX Generation Functions ---


def find_best_values(data: Dict[str, Any], methods_to_compare: List[str]) -> Tuple[
    Dict[Tuple[str, str, str], float],
    Dict[Tuple[str, str, str], Optional[float]],
    Dict[Tuple[str, str, str], float],
    Dict[Tuple[str, str, str], float],
]:
    """Identify the best metric values.

    Calculates:
    1. Global best (among all methods).
    2. Global second best.
    3. Best baseline (among non-dag_bayesian methods).
    4. Best ours (among dag_bayesian methods).

    Args:
        data (Dict[str, Any]): The revised summary data.
        methods_to_compare (List[str]): List of method keys to include.

    Returns:
        Tuple[Dict, Dict, Dict, Dict]: (global_best, global_second_best, baseline_best, ours_best)
    """
    global_best: Dict[Tuple[str, str, str], float] = {}
    global_second_best: Dict[Tuple[str, str, str], Optional[float]] = {}
    baseline_best: Dict[Tuple[str, str, str], float] = {}
    ours_best: Dict[Tuple[str, str, str], float] = {}

    for task in TASK_ORDER:
        for init in INIT_ORDER:
            # Separate lists for comparison
            global_sr, global_gcr, global_tcsr, global_mk = [], [], [], []
            base_sr, base_gcr, base_tcsr, base_mk = [], [], [], []
            ours_sr, ours_gcr, ours_tcsr, ours_mk = [], [], [], []

            for method in methods_to_compare:
                if not data.get(method, {}).get(task, {}).get(init):
                    continue

                metrics = data[method][task][init]

                def get_val(m_dict, key, default):
                    v = m_dict.get(key, default)
                    if isinstance(v, tuple):
                        return v[0]
                    return v

                sr = get_val(metrics, "sr", -1.0)
                gcr = get_val(metrics, "gcr", -1.0)
                tcsr = get_val(metrics, "tcsr", -1.0)
                mk = get_val(metrics, "makespan_sr_1", float("inf"))

                # Add to global lists
                global_sr.append(sr)
                global_gcr.append(gcr)
                global_tcsr.append(tcsr)
                global_mk.append(mk)

                # Add to specific lists
                if "dag_bayesian" in method:
                    ours_sr.append(sr)
                    ours_gcr.append(gcr)
                    ours_tcsr.append(tcsr)
                    ours_mk.append(mk)
                else:
                    base_sr.append(sr)
                    base_gcr.append(gcr)
                    base_tcsr.append(tcsr)
                    base_mk.append(mk)

            # Helper to find best and second best
            def get_top_two(
                values: List[float], higher_is_better: bool
            ) -> Tuple[float, Optional[float]]:
                unique_vals = sorted(list(set(values)), reverse=higher_is_better)
                if not unique_vals:
                    return (float("-inf") if higher_is_better else float("inf")), None

                best = unique_vals[0]
                second = unique_vals[1] if len(unique_vals) > 1 else None
                return best, second

            # Determine Best Values
            # Global
            if global_sr:
                b, sb = get_top_two(global_sr, True)
                global_best[(task, init, "sr")] = b
                global_second_best[(task, init, "sr")] = sb
            if global_gcr:
                b, sb = get_top_two(global_gcr, True)
                global_best[(task, init, "gcr")] = b
                global_second_best[(task, init, "gcr")] = sb
            if global_tcsr:
                b, sb = get_top_two(global_tcsr, True)
                global_best[(task, init, "tcsr")] = b
                global_second_best[(task, init, "tcsr")] = sb
            if global_mk:
                b, sb = get_top_two(global_mk, False)
                global_best[(task, init, "makespan_sr_1")] = b
                global_second_best[(task, init, "makespan_sr_1")] = sb

            # Baseline
            if base_sr:
                baseline_best[(task, init, "sr")] = max(base_sr)
            if base_gcr:
                baseline_best[(task, init, "gcr")] = max(base_gcr)
            if base_tcsr:
                baseline_best[(task, init, "tcsr")] = max(base_tcsr)
            if base_mk:
                baseline_best[(task, init, "makespan_sr_1")] = min(base_mk)

            # Ours (Comparison among our 3 cases)
            if ours_sr:
                ours_best[(task, init, "sr")] = max(ours_sr)
            if ours_gcr:
                ours_best[(task, init, "gcr")] = max(ours_gcr)
            if ours_tcsr:
                ours_best[(task, init, "tcsr")] = max(ours_tcsr)
            if ours_mk:
                ours_best[(task, init, "makespan_sr_1")] = min(ours_mk)

    return global_best, global_second_best, baseline_best, ours_best


def fmt_cell(
    main_val: Union[float, Tuple[float, float], None],
    metric: str,
    global_best: float,
    global_second_best: Optional[float],
    baseline_best: float,
    ours_best: float,
    is_ours: bool,
    ablation_val: Union[float, Tuple[float, float], None] = None,
    show_ablation_in_parens: bool = True,
) -> str:
    """Format a single table cell with main value, bolding/underlining, and ablation study value.

    Args:
        main_val: The primary metric value (float or (mean, std)).
        metric (str): The name of the metric (e.g., 'sr', 'makespan').
        global_best (float): The global best value.
        global_second_best (Optional[float]): The global second best value.
        baseline_best (float): The best value among baselines.
        ours_best (float): The best value among our methods.
        is_ours (bool): Whether this cell belongs to our method.
        ablation_val: The corresponding value from ablation study.
        show_ablation_in_parens (bool): Whether to show ablation value in parentheses.

    Returns:
        str: The formatted string for the LaTeX table cell.
    """
    if main_val is None:
        return "---"

    # Extract mean/std for main value
    if isinstance(main_val, tuple):
        val_mean, val_std = main_val
        # Wrap in math mode for \pm
        s_main = f"${val_mean:.1f} \\pm {val_std:.1f}$"
    else:
        val_mean = main_val
        s_main = f"{val_mean:.1f}"

    # Bolding/Underlining Logic
    # 1. Bold:
    #    - Ours: if better/equal than baseline AND is the best among Ours
    #    - Baseline: if it is the Global Best
    # 2. Underline:
    #    - if it is the Global Second Best

    should_bold = False
    should_underline = False

    # Comparison logic (handle makespan minimization)
    is_makespan = "makespan" in metric

    # Define comparison with tolerance
    def is_better_or_equal(val, target):
        if is_makespan:
            return val <= target + 0.001
        return val >= target - 0.001

    def is_equal(val, target):
        return abs(val - target) < 0.001

    if is_ours:
        # Ours: Bold if better/equal than baseline AND is the best among Ours
        if is_better_or_equal(val_mean, baseline_best) and is_equal(
            val_mean, ours_best
        ):
            should_bold = True
    else:
        # Baseline: Bold if it is the Global Best
        if is_equal(val_mean, global_best):
            should_bold = True

    # Check for second best (Global)
    if global_second_best is not None and is_equal(val_mean, global_second_best):
        should_underline = True

    # Apply Formatting
    if should_bold:
        if isinstance(main_val, tuple):
            # For math mode, use \boldmath to ensure symbols like \pm are also bolded.
            s_main = f"{{\\boldmath ${val_mean:.1f} \\pm {val_std:.1f}$}}"
        else:
            s_main = f"\\textbf{{{s_main}}}"
    elif should_underline:
        # Underline (apply outside of math mode if possible, or inside)
        # For standard LaTeX, \underline works.
        s_main = f"\\underline{{{s_main}}}"

    # Append ablation value in parentheses if requested
    if show_ablation_in_parens and ablation_val is not None:
        if isinstance(ablation_val, tuple):
            abl_mean, abl_std = ablation_val
            s_abl = f"${abl_mean:.1f} \\pm {abl_std:.1f}$"

            # Ablation Bold Logic:
            # Highlight if better than baseline
            if is_better_or_equal(abl_mean, baseline_best):
                s_abl = f"{{\\boldmath ${abl_mean:.1f} \\pm {abl_std:.1f}$}}"
            elif global_second_best is not None and is_equal(
                abl_mean, global_second_best
            ):
                s_abl = f"\\underline{{{s_abl}}}"

        else:
            abl_mean = ablation_val
            s_abl = f"{abl_mean:.1f}"

            if is_better_or_equal(abl_mean, baseline_best):
                s_abl = f"\\textbf{{{s_abl}}}"
            elif global_second_best is not None and is_equal(
                abl_mean, global_second_best
            ):
                s_abl = f"\\underline{{{s_abl}}}"

        return f"{s_main} ({s_abl})"

    return s_main


def generate_latex_table(
    data: Dict[str, Any],
    init_keys: List[str],
    column_labels: List[str],
    display_methods: List[str],
    ablation_style: str = "parentheses",
) -> str:
    """Generate the complete LaTeX code for the results table.

    Args:
        data (Dict[str, Any]): The revised and filtered summary data.
        init_keys (List[str]): List of init keys to include in this table.
        column_labels (List[str]): List of labels for the init columns.
        display_methods (List[str]): Ordered list of method keys to display as rows.
        ablation_style (str): Style for ablation study display ('parentheses' or 'new_row').

    Returns:
        str: A string containing the full LaTeX table code.
    """
    if len(init_keys) != len(column_labels):
        raise ValueError("Length of init_keys and column_labels must match.")

    # Determine method list based on style
    methods_to_plot = list(display_methods)
    if ablation_style == "new_row":
        # Insert ABLATION_METHOD_KEY after dag_bayesian_DEFAULT
        # Note: If dag_bayesian_DEFAULT is not in display_methods, this is skipped
        if "dag_bayesian_DEFAULT" in methods_to_plot:
            try:
                idx = methods_to_plot.index("dag_bayesian_DEFAULT")
                methods_to_plot.insert(idx + 1, ABLATION_METHOD_KEY)
            except ValueError:
                pass

    # Build candidates for best value comparison
    # Only consider methods that are actually displayed (or their inline ablation counterparts)
    comparison_methods = set(methods_to_plot)
    if ablation_style == "parentheses":
        # Include ablation methods if their parent is in plot list
        if "dag_bayesian_DEFAULT" in comparison_methods:
            comparison_methods.add(ABLATION_METHOD_KEY)
    elif ablation_style == "none":
        # Do not include ablation methods in comparison if style is none
        pass

    best_global, best_global_second, best_baseline, best_ours = find_best_values(
        data, list(comparison_methods)
    )
    lines: List[str] = []

    caption_parts = [
        r"Performance comparison in the AI2-THOR simulation environment.",
        r"Results are aggregated by task complexity.",
    ]
    if ablation_style == "parentheses":
        caption_parts.append(
            r"Values in parentheses indicate the performance of the ablation study \quotes{Ours (w/o Mon.)}."
        )
    caption_parts.append(
        r"Higher SR, GCR and TCSR are better ($\uparrow$), and lower Makespan is better ($\downarrow$)."
    )
    caption_str = " ".join(caption_parts)

    lines.extend(
        [
            r"\begin{table}[t]",
            r"\centering",
            r"\caption{" + caption_str + "}",
            r"\label{tab:simulation_results_merged}",
            r"{\renewcommand{\arraystretch}{1.1}",
            r"\resizebox{\columnwidth}{!}{%",
            # Dynamic column definition based on num_metrics
            # ll | (num_metrics)c | ... * number of init blocks
            f"\\begin{{tabular}}{{@{{}}ll|{'|'.join(['c' * len(INCLUDED_METRICS)] * len(init_keys))}@{{}}}}",
            r"\toprule",
        ]
    )

    # Column Headers

    # Dynamically build the metric header part
    metric_headers = []
    for m in INCLUDED_METRICS:
        if m == "sr":
            metric_headers.append(r"\textbf{SR ($\uparrow$)}")
        elif m == "gcr":
            metric_headers.append(r"\textbf{GCR ($\uparrow$)}")
        elif m == "tcsr":
            metric_headers.append(r"\textbf{TCSR ($\uparrow$)}")
        elif m == "makespan":
            metric_headers.append(r"\textbf{MS ($\downarrow$)}")

    metric_header_str = " & ".join(metric_headers)
    num_metrics = len(INCLUDED_METRICS)

    # Build the second row (Init Labels)
    header_row_2_parts = [r"\multicolumn{2}{c|}{\multirow{2}{*}{\textbf{Method}}}"]
    header_row_3_parts = []  # Will hold cmidrules

    # Calculate column spans
    for i, label in enumerate(column_labels):
        header_row_2_parts.append(rf"\multicolumn{{{num_metrics}}}{{c|}}{{{label}}}")

        # cmidrule calculation
        # First 2 columns are Method/Difficulty. Then blocks of num_metrics.
        # Start col for block i (0-indexed i): 3 + i * num_metrics
        # End col: 3 + i * num_metrics + num_metrics - 1
        start_col = 3 + i * num_metrics
        end_col = start_col + num_metrics - 1

        header_row_3_parts.append(rf"\cmidrule(l){{{start_col}-{end_col}}}")

    # Build the third row (SR, GCR, TSR, Makespan repeated)
    header_row_4_parts = [r"\multicolumn{2}{c|}{\textbf{Difficulty}}"]
    for _ in range(len(column_labels)):
        header_row_4_parts.append(metric_header_str)

    lines.extend(
        [
            " & ".join(header_row_2_parts) + r" \\",
            " ".join(header_row_3_parts),
            " & ".join(header_row_4_parts) + r" \\",
            r"\midrule",
        ]
    )

    # Table Body
    for method_idx, method_key in enumerate(methods_to_plot):
        # Handle display names
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

            # Metric Columns for each requested init key
            for init_key in init_keys:
                metrics = data.get(method_key, {}).get(task_key, {}).get(init_key, {})

                # Get ablation data if applicable AND style is parentheses
                abl_metrics = None
                if ablation_style == "parentheses":
                    if method_key == "dag_bayesian_DEFAULT":
                        abl_metrics = (
                            data.get(ABLATION_METHOD_KEY, {})
                            .get(task_key, {})
                            .get(init_key)
                        )

                for metric_key in INCLUDED_METRICS:
                    # Table display logic: Use makespan_sr_1 for makespan column
                    val_key = (
                        "makespan_sr_1" if metric_key == "makespan" else metric_key
                    )
                    val = metrics.get(val_key)

                    abl_val = None
                    if abl_metrics:
                        abl_val = abl_metrics.get(val_key)

                    # For best value comparison, we also need to look up the correct key
                    # create a temporary key for lookup
                    lookup_metric_key = val_key

                    b_global = best_global.get(
                        (task_key, init_key, lookup_metric_key),
                        float("inf") if metric_key == "makespan" else float("-inf"),
                    )
                    b_global_second = best_global_second.get(
                        (task_key, init_key, lookup_metric_key),
                        None,
                    )
                    b_baseline = best_baseline.get(
                        (task_key, init_key, lookup_metric_key),
                        float("inf") if metric_key == "makespan" else float("-inf"),
                    )
                    b_ours = best_ours.get(
                        (task_key, init_key, lookup_metric_key),
                        float("inf") if metric_key == "makespan" else float("-inf"),
                    )

                    is_ours_method = "dag_bayesian" in method_key

                    row_parts.append(
                        fmt_cell(
                            val,
                            metric_key,
                            b_global,
                            b_global_second,
                            b_baseline,
                            b_ours,
                            is_ours_method,
                            abl_val,
                            show_ablation_in_parens=(ablation_style == "parentheses"),
                        )
                    )

            lines.append(" & ".join(row_parts) + r" \\")

        if method_idx < len(methods_to_plot) - 1:
            lines.append(r"\midrule")

    # Footer
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"}",
            r"\end{table}",
        ]
    )

    return "\n".join(lines)


# --- Main Execution ---


def main() -> None:
    """Run the main script execution pipeline."""
    args = load_argument_parser()
    output_json_path = args.root_dir / "unified_analysis_summary.revised.json"

    # 1. Collect and Aggregate Data from all experiment folders found in root_dir
    final_data = collect_and_aggregate(
        args.root_dir, group_by_task_length=args.group_by_task_length
    )

    if args.group_by_task_length:
        global TASK_ORDER
        TASK_ORDER = ["tasks_2", "tasks_3"]
        TASK_DISPLAY_NAMES.update({"tasks_2": "T2", "tasks_3": "T3"})

    # 2. Save the merged summary for visualization
    if output_json_path:
        # Pre-process for JSON output (extract means from tuples)
        json_output_data = {}
        for method, task_data in final_data.items():
            json_output_data[method] = {}
            for task, init_data in task_data.items():
                json_output_data[method][task] = {}
                for init, metrics in init_data.items():
                    json_output_data[method][task][init] = {}
                    for m_name, m_val in metrics.items():
                        if isinstance(m_val, tuple):
                            # Aggregated data has (mean, std), take mean for visualization
                            json_output_data[method][task][init][m_name] = m_val[0]
                        else:
                            # Single run data is already a float
                            json_output_data[method][task][init][m_name] = m_val

        try:
            with open(output_json_path, "w") as f:
                json.dump(json_output_data, f, indent=4)
            print(f"Saved merged summary to {output_json_path}")
        except Exception as e:
            print(f"Error saving JSON output: {e}")

    # 3. Generate LaTeX Table
    # Configuration for the table
    init_keys_1 = ["init_100"]
    labels_1 = [r"\textbf{Correct (100s)}"]

    # Use standard MAIN_METHODS order, but filter to what we actually have data for
    methods_to_display = []
    for m in MAIN_METHODS:
        if m in final_data:
            methods_to_display.append(m)

    print(
        generate_latex_table(
            final_data, init_keys_1, labels_1, methods_to_display, args.ablation_style
        )
    )


if __name__ == "__main__":
    main()
