from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple


def aggregate_summary(
    trials: Sequence[Mapping[str, Any]]
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Aggregate trials into difficulty x approach summary."""

    by_key: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for t in trials:
        key = (str(t["difficulty"]), str(t["approach"]))
        by_key.setdefault(key, []).append(t)
    final: Dict[str, Dict[str, Dict[str, float]]] = {}
    for (difficulty, approach), items in by_key.items():
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
        final.setdefault(difficulty, {})[approach] = {
            "SR": sr,
            "GCR": gcr,
            "TSR": tsr,
            "Makespan": makespan,
        }
    return final


def summary_to_latex_table(final_data: Mapping[str, Mapping[str, Mapping[str, float]]]) -> str:
    """Convert summary to LaTeX tabular code."""

    lines: List[str] = []
    lines.append("\\begin{tabular}{l l r r r r}")
    lines.append("\\toprule")
    lines.append("Difficulty & Approach & SR(\\%) & GCR(\\%) & TSR(\\%) & Makespan \\\\")
    lines.append("\\midrule")
    for difficulty, approaches in sorted(final_data.items()):
        first = True
        for approach, metrics in sorted(approaches.items()):
            row = [
                difficulty if first else "",
                approach,
                f"{metrics.get('SR', 0.0):.2f}",
                f"{metrics.get('GCR', 0.0):.2f}",
                f"{metrics.get('TSR', 0.0):.2f}",
                f"{metrics.get('Makespan', 0.0):.2f}",
            ]
            lines.append(" & ".join(row) + " \\\\")
            first = False
        lines.append("\\midrule")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    return "\n".join(lines)


