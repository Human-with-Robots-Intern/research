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
    import re
    
    # Approach name mapping - supports various approach names
    # Default mapping for common approaches
    approach_labels: Dict[str, str] = {
        "dag_bayesian_DEFAULT": "Ours",
        "dag_bayesian": "Ours",
        "dag_bayesian_NONE_URGENCY": "Ours",
        "dag_greedy": "Ours (Greedy)",
        "dag_no_monitoring": "Ours (w/o Mon.)",
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
    lines.append("\\caption{Performance comparison in the AI2-THOR simulation environment. "
                "Results are aggregated by task complexity. Values in parentheses indicate "
                "the performance of the ablation study \\quotes{Ours (w/o Mon.)}. Higher SR "
                "and TSR are better ($\\uparrow$), and lower Makespan is better ($\\downarrow$).}")
    lines.append("\\label{tab:simulation_results_merged}")
    lines.append("{\\renewcommand{\\arraystretch}{1}")
    lines.append("\\resizebox{\\textwidth}{!}{%")
    lines.append("\\begin{tabular}{@{}ll|ccc|ccc|ccc|ccc|ccc@{}}")
    lines.append("\\toprule")
    
    # Column headers - SR, TSR, Makespan only (no GCR)
    lines.append("\\multicolumn{2}{c|}{\\multirow{2}{*}{\\textbf{Method}}} & "
                "\\multicolumn{3}{c|}{\\textbf{Under (60s)}} & "
                "\\multicolumn{3}{c|}{\\textbf{Under-Mid (80s)}} & "
                "\\multicolumn{3}{c|}{\\textbf{Correct (100s)}} & "
                "\\multicolumn{3}{c|}{\\textbf{Over-Mid (120s)}} & "
                "\\multicolumn{3}{c}{\\textbf{Over (140s)}} \\\\")
    lines.append("\\cmidrule(l){3-5} \\cmidrule(l){6-8} \\cmidrule(l){9-11} \\cmidrule(l){12-14} \\cmidrule(l){15-17}")
    lines.append("\\multicolumn{2}{c|}{\\textbf{Difficulty}} & "
                "\\textbf{SR} & \\textbf{TSR} & \\textbf{MS} & "
                "\\textbf{SR} & \\textbf{TSR} & \\textbf{MS} & "
                "\\textbf{SR} & \\textbf{TSR} & \\textbf{MS} & "
                "\\textbf{SR} & \\textbf{TSR} & \\textbf{MS} & "
                "\\textbf{SR} & \\textbf{TSR} & \\textbf{MS} \\\\")
    lines.append("\\midrule")
    
    # Determine approach order: EDF, CPM, then Ours variants
    # Collect all approaches from data
    all_approaches = set(final_data.keys())
    
    # Categorize approaches
    edf_approaches = [a for a in all_approaches if "edf" in a.lower() or a == "edf"]
    cpm_approaches = [a for a in all_approaches if a == "cpm"]
    ours_approaches = [a for a in all_approaches 
                      if a.startswith("dag_bayesian") or 
                      (a.startswith("dag_") and "edf" not in a.lower() and a != "cpm")]
    
    # Sort within each category
    edf_approaches.sort()
    cpm_approaches.sort()
    ours_approaches.sort()
    
    # Build final order: EDF, CPM, then Ours
    sorted_approaches = edf_approaches + cpm_approaches + ours_approaches
    
    # If there are any other approaches not in these categories, add them at the end
    other_approaches = [a for a in all_approaches 
                       if a not in edf_approaches and 
                       a not in cpm_approaches and 
                       a not in ours_approaches]
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
            
            # Add metrics for states60
            sr60 = states60.get('SR', 0.0)
            tsr60 = states60.get('TSR', 0.0)
            makespan60 = states60.get('Makespan', 0.0)
            row_parts.append(f"& {sr60:.1f}")
            row_parts.append(f"& {tsr60:.1f}")
            row_parts.append(f"& {makespan60:.1f}")

            # Add metrics for states80
            sr80 = states80.get('SR', 0.0)
            tsr80 = states80.get('TSR', 0.0)
            makespan80 = states80.get('Makespan', 0.0)
            row_parts.append(f"& {sr80:.1f}")
            row_parts.append(f"& {tsr80:.1f}")
            row_parts.append(f"& {makespan80:.1f}")
            
            # Add metrics for states100
            sr100 = states100.get('SR', 0.0)
            tsr100 = states100.get('TSR', 0.0)
            makespan100 = states100.get('Makespan', 0.0)
            row_parts.append(f"& {sr100:.1f}")
            row_parts.append(f"& {tsr100:.1f}")
            row_parts.append(f"& {makespan100:.1f}")

            # Add metrics for states120
            sr120 = states120.get('SR', 0.0)
            tsr120 = states120.get('TSR', 0.0)
            makespan120 = states120.get('Makespan', 0.0)
            row_parts.append(f"& {sr120:.1f}")
            row_parts.append(f"& {tsr120:.1f}")
            row_parts.append(f"& {makespan120:.1f}")
            
            # Add metrics for states140
            sr140 = states140.get('SR', 0.0)
            tsr140 = states140.get('TSR', 0.0)
            makespan140 = states140.get('Makespan', 0.0)
            row_parts.append(f"& {sr140:.1f}")
            row_parts.append(f"& {tsr140:.1f}")
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


