from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple


def aggregate_summary(
    trials: Sequence[Mapping[str, Any]]
) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
    """Aggregate trials into approach x difficulty x states summary.
    
    Returns:
        Structure: {approach: {difficulty: {states: {metric: value}}}}
    """

    by_key: Dict[Tuple[str, str, str], List[Mapping[str, Any]]] = {}
    for t in trials:
        key = (str(t["approach"]), str(t["difficulty"]), str(t["states"]))
        by_key.setdefault(key, []).append(t)
    
    final: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    for (approach, difficulty, states), items in by_key.items():
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
        makespan = (sum(makespan_values) / len(makespan_values)) if makespan_values else 0.0
        
        final.setdefault(approach, {}).setdefault(difficulty, {})[states] = {
            "SR": sr,
            "GCR": gcr,
            "TSR": tsr,
            "Makespan": makespan,
        }
    return final


def summary_to_latex_table(
    final_data: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]]
) -> str:
    """Convert summary to Overleaf-style LaTeX table.
    
    Args:
        final_data: {approach: {difficulty: {states: {metric: value}}}}
    
    Returns:
        Full LaTeX table code in Overleaf format.
    """
    
    # Approach name mapping
    approach_labels = {
        "dag_bayesian_DEFAULT": "Ours (Default)",
        "dag_greedy": "Ours (Greedy)",
        "dag_no_monitoring": "Ours (w/o Mon.)",
        "dag_no_urgency": "Ours (w/o Urg.)",
        "dag_no_rescheduling": "Ours (w/o Rem.)",
        "edf": "EDF",
        "cpm": "CPM",
    }
    
    # Difficulty ordering and formatting
    def format_difficulty(diff: str) -> str:
        """Convert tasks_X_constraints_Y to TX CY format."""
        import re
        match = re.match(r"tasks_(\d+)_constraints_(\d+)", diff)
        if match:
            return f"T{match.group(1)} C{match.group(2)}"
        return diff
    
    def difficulty_sort_key(diff: str) -> Tuple[int, int]:
        """Sort by (num_tasks, num_constraints)."""
        import re
        match = re.match(r"tasks_(\d+)_constraints_(\d+)", diff)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (999, 999)
    
    lines: List[str] = []
    
    # Table header
    lines.append("\\begin{table*}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Performance comparison in the AI2-THOR simulation environment "
                "(Based on final\\_summary.json). Results are presented according to the "
                "initial belief condition. Higher TSR is better (↑), and lower Makespan is "
                "better (↓). }")
    lines.append("\\label{tab:simulation_results_from_json}")
    lines.append("{\\renewcommand{\\arraystretch}{0.75}")
    lines.append("\\resizebox{0.85\\textwidth}{!}{%")
    lines.append("\\begin{tabular}{@{}ll|cccc|cccc|cccc@{}}")
    lines.append("\\toprule")
    
    # Column headers
    lines.append("\\multicolumn{2}{c|}{\\multirow{2}{*}{\\textbf{Method \\& Difficulty "
                "(Tasks, Constraints)}}} & \\multicolumn{4}{c|}{\\textbf{Under-estimate (60s)}} & "
                "\\multicolumn{4}{c|}{\\textbf{Correct (100s)}} & "
                "\\multicolumn{4}{c}{\\textbf{Over-estimate (140s)}} \\\\ \\cmidrule(l){3-14}")
    lines.append("\\multicolumn{2}{c|}{} & \\textbf{SR(\\%) ↑} & \\textbf{GCR(\\%) ↑} & "
                "\\textbf{TSR(\\%) ↑} & \\textbf{Makespan(s) ↓} & \\textbf{SR(\\%) ↑} & "
                "\\textbf{GCR(\\%) ↑} & \\textbf{TSR(\\%) ↑} & \\textbf{Makespan(s) ↓} & "
                "\\textbf{SR(\\%) ↑} & \\textbf{GSR(\\%) ↑} & \\textbf{TSR(\\%) ↑} & "
                "\\textbf{Makespan(s) ↓} \\\\ \\midrule")
    
    # Sort approaches (maintain specific order if needed)
    approach_order = [
        "dag_bayesian_DEFAULT",
        "dag_greedy",
        "dag_no_monitoring",
        "dag_no_urgency",
        "dag_no_rescheduling",
        "edf",
        "cpm",
    ]
    
    # Filter to only include approaches that exist in data
    sorted_approaches = [app for app in approach_order if app in final_data]
    
    for approach in sorted_approaches:
        difficulties_data = final_data[approach]
        sorted_difficulties = sorted(difficulties_data.keys(), key=difficulty_sort_key)
        
        if not sorted_difficulties:
            continue
        
        label = approach_labels.get(approach, approach)
        num_rows = len(sorted_difficulties)
        
        for idx, difficulty in enumerate(sorted_difficulties):
            states_data = difficulties_data[difficulty]
            
            # Get metrics for each states
            states60 = states_data.get("states60", {})
            states100 = states_data.get("states100", {})
            states140 = states_data.get("states140", {})
            
            # Format difficulty label
            diff_label = format_difficulty(difficulty)
            
            # Build row
            if idx == 0:
                # First row: include multirow approach label
                row_parts = [
                    f"\\multirow[t]{{{num_rows}}}{{*}}{{\\textbf{{{label}}}}}",
                    f"& {diff_label}",
                ]
            else:
                # Subsequent rows: empty first column
                row_parts = [f" & {diff_label}"]
            
            # Add metrics for states60
            row_parts.append(f"& {states60.get('SR', 0.0):.2f}")
            row_parts.append(f"& {states60.get('GCR', 0.0):.2f}")
            row_parts.append(f"& {states60.get('TSR', 0.0):.2f}")
            row_parts.append(f"& ${states60.get('Makespan', 0.0):.2f}$")
            
            # Add metrics for states100
            row_parts.append(f"& {states100.get('SR', 0.0):.2f}")
            row_parts.append(f"& {states100.get('GCR', 0.0):.2f}")
            row_parts.append(f"& {states100.get('TSR', 0.0):.2f}")
            row_parts.append(f"& ${states100.get('Makespan', 0.0):.2f}$")
            
            # Add metrics for states140
            row_parts.append(f"& {states140.get('SR', 0.0):.2f}")
            row_parts.append(f"& {states140.get('GCR', 0.0):.2f}")
            row_parts.append(f"& {states140.get('TSR', 0.0):.2f}")
            row_parts.append(f"& ${states140.get('Makespan', 0.0):.2f}$")
            
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


