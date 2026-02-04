from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple, Optional


def aggregate_summary(
    trials: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Optional[float]]]]]]:
    """Aggregate trials into approach x difficulty x init x init_* summary.

    Returns:
        Structure: {approach: {difficulty: {init: {init_60/100/140: {metric: value}}}}}
    """

    by_key: Dict[Tuple[str, str, str], List[Mapping[str, Any]]] = {}
    for t in trials:
        key = (str(t["approach"]), str(t["difficulty"]), str(t["states"]))
        by_key.setdefault(key, []).append(t)

    final: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Optional[float]]]]]] = {}
    for (approach, difficulty, states), items in by_key.items():
        # Map states to init_* format and filter out states80 and states120
        states_mapping = {
            "states60": "init_60",
            "states70": "init_70",
            "states80": "init_80",
            "states90": "init_90",
            "states100": "init_100",
            "states110": "init_110",
            "states120": "init_120",
            "states130": "init_130",
            "states140": "init_140",
        }

        if states not in states_mapping:
            # Skip states80 and states120
            continue

        init_key = states_mapping[states]

        total = len(items)
        if total == 0:
            continue
        # SR: trial_metrics에서 넘어온 sr(0/1)을 그대로 집계
        sr_successes = sum(int(it.get("sr", 0)) for it in items)
        sr = (sr_successes / total) * 100.0
        gcr_successes = sum(int(it.get("instruction_gcr", 0)) for it in items)
        gcr = (gcr_successes / total) * 100.0
        # TSR: average over numeric-only, ignore None
        tsr_samples: List[float] = []
        for it in items:
            v = it.get("tsr", None)
            if v is None:
                continue
            try:
                tsr_samples.append(float(v))
            except Exception:
                continue
        tsr = (sum(tsr_samples) / len(tsr_samples) * 100.0) if tsr_samples else 0.0
        makespan_values = [float(it.get("makespan", 0.0)) for it in items]
        makespan = (
            (sum(makespan_values) / len(makespan_values)) if makespan_values else 0.0
        )

        makespan_sr_1_values = [
            float(it.get("makespan", 0.0)) for it in items if int(it.get("sr", 0)) == 1
        ]
        makespan_sr_1 = (
            (sum(makespan_sr_1_values) / len(makespan_sr_1_values))
            if makespan_sr_1_values
            else 0.0
        )

        # Structure: {approach: {difficulty: {init: {init_60/100/140: {metric: value}}}}}
        final.setdefault(approach, {}).setdefault(difficulty, {}).setdefault(
            "init", {}
        )[init_key] = {
            "sr": sr,
            "gcr": gcr,
            "tsr": tsr,
            "makespan": makespan,
            "makespan_sr_1": makespan_sr_1,
        }
    return final


def summary_to_latex_table(
    final_data: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
) -> str:
    """Convert summary to Overleaf-style LaTeX table.

    Args:
        final_data: {approach: {difficulty: {states: {metric: value}}}}

    Returns:
        Full LaTeX table code in Overleaf format.
    """
    import re

    # Approach name mapping - supports various approach names
    # Default mapping for common approaches
    approach_labels: Dict[str, str] = {
        "dag_bayesian_DEFAULT": "Ours",
        "dag_bayesian": "Ours",
        "dag_bayesian_NONE_URGENCY": "Ours",
        "dag_greedy": "Ours (Greedy)",
        "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
        "dag_no_urgency": "Ours (w/o Urg.)",
        "dag_no_rescheduling": "Ours (w/o Rem.)",
        "dag_edf": "DAG + EDF",
        "edf": "DAG + EDF",
        "cpm": "DAG + CPM",
    }

    def get_approach_label(approach: str) -> str:
        """Get display label for approach, with fallback logic."""
        # Check exact match first
        if approach in approach_labels:
            return approach_labels[approach]

        # Check if it starts with known prefixes
        if approach.startswith("dag_bayesian"):
            return "Ours"
        if approach.startswith("dag_edf") or approach == "edf":
            return "DAG + EDF"
        if approach == "cpm":
            return "DAG + CPM"

        # Default: use approach name as-is
        return approach

    # Difficulty ordering and formatting
    def format_difficulty(diff: str) -> str:
        """Keep original format: tasks_X_constraints_Y."""
        return diff.replace("_", "\\_")  # Escape underscores for LaTeX

    def difficulty_sort_key(diff: str) -> Tuple[int, int]:
        """Sort by (num_tasks, num_constraints)."""
        match = re.match(r"tasks_(\d+)_constraints_(\d+)", diff)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (999, 999)

    lines: List[str] = []

    # Table header - matching example format
    lines.append("\\begin{table*}[t]")
    lines.append("\\centering")
    lines.append(
        "\\caption{Performance comparison in the AI2-THOR simulation environment. "
        "Results are aggregated by task complexity. Values in parentheses indicate "
        "the performance of the ablation study \\quotes{Ours (w/o Mon.)}. Higher SR, GCR, "
        "and TSR are better ($\\uparrow$), and lower Makespan is better ($\\downarrow$).}"
    )
    lines.append("\\label{tab:simulation_results_merged}")
    lines.append("{\\renewcommand{\\arraystretch}{1}")
    lines.append("\\resizebox{\\textwidth}{!}{%")
    lines.append("\\begin{tabular}{@{}ll|cccc|cccc|cccc|cccc|cccc@{}}")
    lines.append("\\toprule")

    # Column headers - SR, GCR, TSR, Makespan
    lines.append(
        "\\multicolumn{2}{c|}{\\multirow{2}{*}{\\textbf{Method}}} & "
        "\\multicolumn{4}{c|}{\\textbf{Under (60s)}} & "
        "\\multicolumn{4}{c|}{\\textbf{Under-Mid (80s)}} & "
        "\\multicolumn{4}{c|}{\\textbf{Correct (100s)}} & "
        "\\multicolumn{4}{c|}{\\textbf{Over-Mid (120s)}} & "
        "\\multicolumn{4}{c}{\\textbf{Over (140s)}} \\\\"
    )
    lines.append(
        "\\cmidrule(l){3-6} \\cmidrule(l){7-10} \\cmidrule(l){11-14} \\cmidrule(l){15-18} \\cmidrule(l){19-22}"
    )
    lines.append(
        "\\multicolumn{2}{c|}{\\textbf{Difficulty}} & "
        "\\textbf{SR} & \\textbf{GCR} & \\textbf{TSR} & \\textbf{MS} & "
        "\\textbf{SR} & \\textbf{GCR} & \\textbf{TSR} & \\textbf{MS} & "
        "\\textbf{SR} & \\textbf{GCR} & \\textbf{TSR} & \\textbf{MS} & "
        "\\textbf{SR} & \\textbf{GCR} & \\textbf{TSR} & \\textbf{MS} & "
        "\\textbf{SR} & \\textbf{GCR} & \\textbf{TSR} & \\textbf{MS} \\\\"
    )
    lines.append("\\midrule")

    # Determine approach order: EDF, CPM, then Ours variants
    # Collect all approaches from data
    all_approaches = set(final_data.keys())

    # Categorize approaches
    edf_approaches = [a for a in all_approaches if "edf" in a.lower() or a == "edf"]
    cpm_approaches = [a for a in all_approaches if a == "cpm"]
    ours_approaches = [
        a
        for a in all_approaches
        if a.startswith("dag_bayesian")
        or (a.startswith("dag_") and "edf" not in a.lower() and a != "cpm")
    ]

    # Sort within each category
    edf_approaches.sort()
    cpm_approaches.sort()
    ours_approaches.sort()

    # Build final order: EDF, CPM, then Ours
    sorted_approaches = edf_approaches + cpm_approaches + ours_approaches

    # If there are any other approaches not in these categories, add them at the end
    other_approaches = [
        a
        for a in all_approaches
        if a not in edf_approaches
        and a not in cpm_approaches
        and a not in ours_approaches
    ]
    other_approaches.sort()
    sorted_approaches.extend(other_approaches)

    for approach in sorted_approaches:
        difficulties_data = final_data[approach]
        sorted_difficulties = sorted(difficulties_data.keys(), key=difficulty_sort_key)

        if not sorted_difficulties:
            continue

        label = get_approach_label(approach)
        num_rows = len(sorted_difficulties)

        for idx, difficulty in enumerate(sorted_difficulties):
            states_data = difficulties_data[difficulty]

            # Get metrics for each states
            states60 = states_data.get("states60", {})
            states80 = states_data.get("states80", {})
            states100 = states_data.get("states100", {})
            states120 = states_data.get("states120", {})
            states140 = states_data.get("states140", {})

            # Format difficulty label - keep original format
            diff_label = format_difficulty(difficulty)

            # Build row
            if idx == 0:
                # First row: include multirow approach label
                row_parts = [
                    f"\\multirow{{{num_rows}}}{{*}}{{\\textbf{{{label}}}}}",
                    f"& \\textbf{{{diff_label}}}",
                ]
            else:
                # Subsequent rows: empty first column
                row_parts = [f" & \\textbf{{{diff_label}}}"]

            # Helper to format TSR based on constraints
            def _fmt_tsr(state_data: Dict[str, float]) -> str:
                if "constraints_0" in difficulty:
                    return "-"
                return f"{state_data.get('TSR', 0.0):.1f}"

            # Add metrics for states60
            sr60 = states60.get("SR", 0.0)
            gcr60 = states60.get("GCR", 0.0)
            makespan60 = states60.get("Makespan", 0.0)
            row_parts.append(f"& {sr60:.1f}")
            row_parts.append(f"& {gcr60:.1f}")
            row_parts.append(f"& {_fmt_tsr(states60)}")
            row_parts.append(f"& {makespan60:.1f}")

            # Add metrics for states80
            sr80 = states80.get("SR", 0.0)
            gcr80 = states80.get("GCR", 0.0)
            makespan80 = states80.get("Makespan", 0.0)
            row_parts.append(f"& {sr80:.1f}")
            row_parts.append(f"& {gcr80:.1f}")
            row_parts.append(f"& {_fmt_tsr(states80)}")
            row_parts.append(f"& {makespan80:.1f}")

            # Add metrics for states100
            sr100 = states100.get("SR", 0.0)
            gcr100 = states100.get("GCR", 0.0)
            makespan100 = states100.get("Makespan", 0.0)
            row_parts.append(f"& {sr100:.1f}")
            row_parts.append(f"& {gcr100:.1f}")
            row_parts.append(f"& {_fmt_tsr(states100)}")
            row_parts.append(f"& {makespan100:.1f}")

            # Add metrics for states120
            sr120 = states120.get("SR", 0.0)
            gcr120 = states120.get("GCR", 0.0)
            makespan120 = states120.get("Makespan", 0.0)
            row_parts.append(f"& {sr120:.1f}")
            row_parts.append(f"& {gcr120:.1f}")
            row_parts.append(f"& {_fmt_tsr(states120)}")
            row_parts.append(f"& {makespan120:.1f}")

            # Add metrics for states140
            sr140 = states140.get("SR", 0.0)
            gcr140 = states140.get("GCR", 0.0)
            makespan140 = states140.get("Makespan", 0.0)
            row_parts.append(f"& {sr140:.1f}")
            row_parts.append(f"& {gcr140:.1f}")
            row_parts.append(f"& {_fmt_tsr(states140)}")
            row_parts.append(f"& {makespan140:.1f}")

            lines.append(" ".join(row_parts) + " \\\\")

        # Add midrule after each approach
        lines.append("\\midrule")

    # Table footer
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}%")
    lines.append("}")
    lines.append("}")
    lines.append("\\end{table*}")

    return "\n".join(lines)
