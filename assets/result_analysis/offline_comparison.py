"""Compare offline batch results against oracle reference.

Produces two output files:

1. offline_comparison_raw.json
   Per scene/case/instruction: oracle fields + per-approach metrics and oracle gaps.

2. offline_analysis_summary.json
   Per approach/case: aggregated metrics (sr, tsr, makespan, makespan_sr_1,
   makespan_gap, makespan_gap_sr_1, computation_time, computation_time_gap).

Optional (--tolerance-sweep):

3. offline_analysis_tol_sweep.json
   Per tolerance/approach/case: TSR re-computed from saved detail_log.
   Does not require re-running the batch scheduler.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.utils.common.logger import create_module_logger
from src.utils.config.constants import (
    CONSECUTIVE_TASK_WAIT_TOLERANCE,
    TIMING_TOLERANCE_RATIO,
)

logger = create_module_logger(__name__)

EPSILON = 1e-6


def build_approach_key(stem: str) -> str:
    """Convert result filename stem to a short approach key.

    Examples:
        cpm__DEFAULT__CORRECT_ESTIMATE                          → cpm
        edf__DEFAULT__CORRECT_ESTIMATE                          → edf
        bayesian__DEFAULT__CORRECT_ESTIMATE__w1_d1              → bayesian__DEFAULT__w1_d1
        bayesian__NONE_MONITORING__CORRECT_ESTIMATE__w5_d5      → bayesian__NONE_MONITORING__w5_d5
        bayesian__DEFAULT__CORRECT_ESTIMATE__w10_d10__eta0.1    → bayesian__DEFAULT__w10_d10__eta0.1
    """
    parts = stem.split("__")
    approach = parts[0]

    if approach == "cpm":
        return "cpm"
    if approach == "edf":
        return "edf"
    if approach == "bayesian":
        # parts: ["bayesian", ablation, init_prior, beam] or
        #        ["bayesian", ablation, init_prior, beam, "eta{value}"]
        ablation = parts[1]
        beam = parts[3]  # e.g. "w1_d1"
        key = f"bayesian__{ablation}__{beam}"
        if len(parts) >= 5 and parts[4].startswith("eta"):
            key += f"__{parts[4]}"
        return key

    return stem


def _oracle_has_constraint_violation(data: dict[str, Any]) -> bool:
    """Return True when any constraint in the oracle's own detail_log is marked [False]."""
    for step in data.get("steps", []):
        for constraint_result in step.get("detail_log", {}).values():
            if isinstance(constraint_result, str) and constraint_result.startswith(
                "[False]"
            ):
                return True
    return False


def load_oracle(path: Path) -> dict[str, Any]:
    with path.open() as f:
        data = json.load(f)
    violated = _oracle_has_constraint_violation(data)
    return {
        "optimal_schedule_time": data["optimal_schedule_time"],
        "computation_time": data["computation_time"],
        "exact": data["exact"],
        "constraint_violated": violated,
    }


def load_baseline(path: Path) -> dict[str, Any]:
    with path.open() as f:
        data = json.load(f)
    tsr_raw = data.get("timing_success_rate_sched")
    return {
        "completed": bool(data.get("completed", False)),
        "tsr": float(tsr_raw) if tsr_raw is not None else 0.0,
        "makespan": data.get("scheduler_makespan"),
        "computation_time": data.get("computation_time"),
    }


def _round(value: float | None, ndigits: int) -> float | None:
    return round(value, ndigits) if value is not None else None


def build_raw(base_dir: Path, task_folder: str) -> dict[str, Any]:
    """Walk oracle reference tree and match each instruction to batch results.

    Returns nested dict: raw[scene][case][instruction] = {oracle: ..., approach: ...}
    """
    oracle_root = base_dir / "offline_oracle_reference" / task_folder
    batch_root = base_dir / "offline_batch" / task_folder

    if not oracle_root.exists():
        raise FileNotFoundError(f"Oracle reference directory not found: {oracle_root}")
    if not batch_root.exists():
        raise FileNotFoundError(f"Batch directory not found: {batch_root}")

    raw: dict[str, Any] = {}

    for scene_dir in sorted(oracle_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        scene = scene_dir.name

        for case_dir in sorted(scene_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            case = case_dir.name

            for oracle_file in sorted(case_dir.glob("*.json")):
                instruction = oracle_file.stem

                try:
                    oracle_data = load_oracle(oracle_file)
                except Exception as e:
                    logger.warning("Failed to load oracle %s: %s", oracle_file, e)
                    continue

                batch_dir = batch_root / scene / case / instruction
                if not batch_dir.exists():
                    logger.warning(
                        "No batch directory: %s / %s / %s", scene, case, instruction
                    )
                    continue

                oracle_valid = not oracle_data.get("constraint_violated", False)
                entry: dict[str, Any] = {
                    "oracle": oracle_data,
                    "oracle_valid": oracle_valid,
                }

                for batch_file in sorted(batch_dir.glob("*.json")):
                    approach_key = build_approach_key(batch_file.stem)
                    try:
                        baseline = load_baseline(batch_file)
                    except Exception as e:
                        logger.warning("Failed to load %s: %s", batch_file, e)
                        continue

                    makespan = baseline["makespan"]
                    comp_time = baseline["computation_time"]
                    oracle_makespan = oracle_data["optimal_schedule_time"]
                    oracle_comp_time = oracle_data["computation_time"]

                    entry[approach_key] = {
                        "completed": baseline["completed"],
                        "tsr": baseline["tsr"],
                        "makespan": _round(makespan, 4),
                        "makespan_gap": (
                            _round(makespan - oracle_makespan, 4)
                            if makespan is not None
                            else None
                        ),
                        "computation_time": _round(comp_time, 6),
                        "computation_time_gap": (
                            _round(comp_time - oracle_comp_time, 6)
                            if comp_time is not None
                            else None
                        ),
                    }

                raw.setdefault(scene, {}).setdefault(case, {})[instruction] = entry

    return raw


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(
    raw: dict[str, Any], *, skip_oracle_violated: bool = False
) -> dict[str, Any]:
    """Aggregate raw per-instruction data into per-approach/case summary.

    Args:
        raw: Output of :func:`build_raw`.
        skip_oracle_violated: When True, exclude instructions where the oracle's
            own schedule violates a constraint (``oracle_valid: False``).  These
            entries have inflated ``optimal_schedule_time`` values that make
            approach makespan gaps artificially negative.
    """

    # Collect records: records[approach][case] = list of per-instruction dicts
    records: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for _scene, cases in raw.items():
        for case, instructions in cases.items():
            for _instruction, entry in instructions.items():
                if skip_oracle_violated and not entry.get("oracle_valid", True):
                    continue
                for approach_key, metrics in entry.items():
                    if approach_key in ("oracle", "oracle_valid"):
                        continue
                    records[approach_key][case].append(metrics)

    summary: dict[str, Any] = {}

    for approach_key, cases in sorted(records.items()):
        summary[approach_key] = {}
        for case, entries in sorted(cases.items()):
            n = len(entries)
            if n == 0:
                continue

            completed = [e for e in entries if e["completed"]]

            sr = len(completed) / n * 100
            tsr = _mean([e["tsr"] for e in entries]) or 0.0
            tsr_pct = tsr * 100

            makespan = _mean(
                [e["makespan"] for e in entries if e["makespan"] is not None]
            )
            makespan_sr_1 = _mean(
                [e["makespan"] for e in completed if e["makespan"] is not None]
            )
            makespan_gap = _mean(
                [e["makespan_gap"] for e in entries if e["makespan_gap"] is not None]
            )
            makespan_gap_sr_1 = _mean(
                [e["makespan_gap"] for e in completed if e["makespan_gap"] is not None]
            )
            computation_time = _mean(
                [
                    e["computation_time"]
                    for e in entries
                    if e["computation_time"] is not None
                ]
            )
            computation_time_gap = _mean(
                [
                    e["computation_time_gap"]
                    for e in entries
                    if e["computation_time_gap"] is not None
                ]
            )

            summary[approach_key][case] = {
                "sr": round(sr, 4),
                "tsr": round(tsr_pct, 4),
                "makespan": _round(makespan, 4),
                "makespan_sr_1": _round(makespan_sr_1, 4),
                "makespan_gap": _round(makespan_gap, 4),
                "makespan_gap_sr_1": _round(makespan_gap_sr_1, 4),
                "computation_time": _round(computation_time, 6),
                "computation_time_gap": _round(computation_time_gap, 6),
            }

    return summary


def _recompute_tsr_from_detail_log(
    detail_log: dict[str, Any],
    tolerance_abs: float,
) -> float | None:
    """Re-compute schedule TSR from a saved detail_log with a different tolerance_abs.

    Only non-zero interval constraints are affected by tolerance_abs.
    (0, True) consecutive constraints always use CONSECUTIVE_TASK_WAIT_TOLERANCE=2.0s
    and their result is read directly from the [True/False] flag.

    Args:
        detail_log: The ``detail_log`` dict from a batch result JSON.
        tolerance_abs: Absolute tolerance cap for non-zero interval constraints.

    Returns:
        TSR as a float in [0, 1], or None when no constraints exist.
    """
    total = 0
    succeeded = 0

    for _edge_key, edge_val in detail_log.items():
        constraint_str = edge_val.get("Original Timing Constraint", "")
        schedule_str = edge_val.get("Schedule Result", "")

        # Parse constraint: "(interval, is_critical)"
        c_match = re.match(r"\(([^,]+),\s*(True|False)\)", constraint_str)
        if not c_match:
            continue
        interval = float(c_match.group(1))
        is_critical = c_match.group(2) == "True"

        # Parse schedule: "[True/False] : (pred_end) -> (succ_interaction_start)"
        t_match = re.match(
            r"\[(True|False)\] : \(([\d.]+)\) -> \(([\d.]+)s?\)", schedule_str
        )
        if not t_match:
            continue

        total += 1

        if is_critical and interval < EPSILON:
            # (0, True) result is independent of tolerance_abs — use saved flag.
            if t_match.group(1) == "True":
                succeeded += 1
            continue

        pred_end = float(t_match.group(2))
        succ_interaction_start = float(t_match.group(3))
        actual_diff = succ_interaction_start - pred_end

        ratio_allowance = interval * TIMING_TOLERANCE_RATIO
        tolerance = max(5.0, min(tolerance_abs, ratio_allowance))

        if is_critical:
            if abs(interval - actual_diff) <= tolerance:
                succeeded += 1
        else:
            if (interval - actual_diff) <= tolerance:
                succeeded += 1

    return succeeded / total if total > 0 else None


def build_tol_sweep(
    base_dir: Path,
    task_folder: str,
    tolerances: list[float],
) -> dict[str, Any]:
    """Re-compute TSR for each tolerance from existing batch detail_logs.

    No scheduler re-run is needed — only the evaluation threshold changes.

    Returns:
        Nested dict:
        result[tolerance_str][approach_key][case] = list of {tsr, makespan, ...}
    """
    batch_root = base_dir / "offline_batch" / task_folder

    # records[tol][approach][case] = list of per-instruction dicts
    records: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {
        str(tol): defaultdict(lambda: defaultdict(list)) for tol in tolerances
    }

    for scene_dir in sorted(batch_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        for case_dir in sorted(scene_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            case = case_dir.name
            for instr_dir in sorted(case_dir.iterdir()):
                if not instr_dir.is_dir():
                    continue
                for batch_file in sorted(instr_dir.glob("*.json")):
                    approach_key = build_approach_key(batch_file.stem)
                    try:
                        with batch_file.open() as f:
                            data = json.load(f)
                    except Exception as e:
                        logger.warning("Failed to load %s: %s", batch_file, e)
                        continue

                    detail_log = data.get("detail_log", {})
                    makespan = data.get("scheduler_makespan")
                    completed = bool(data.get("completed", False))

                    for tol in tolerances:
                        tsr = _recompute_tsr_from_detail_log(detail_log, tol)
                        records[str(tol)][approach_key][case].append(
                            {
                                "tsr": tsr if tsr is not None else 0.0,
                                "makespan": makespan,
                                "completed": completed,
                            }
                        )

    # Aggregate per approach/case
    result: dict[str, Any] = {}
    for tol_str, approaches in records.items():
        result[tol_str] = {}
        for approach_key, cases in sorted(approaches.items()):
            result[tol_str][approach_key] = {}
            for case, entries in sorted(cases.items()):
                n = len(entries)
                if n == 0:
                    continue
                tsr_mean = _mean([e["tsr"] for e in entries]) or 0.0
                makespan_mean = _mean(
                    [e["makespan"] for e in entries if e["makespan"] is not None]
                )
                sr = len([e for e in entries if e["completed"]]) / n * 100
                result[tol_str][approach_key][case] = {
                    "sr": round(sr, 4),
                    "tsr": round(tsr_mean * 100, 4),
                    "makespan": _round(makespan_mean, 4),
                }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare offline batch results against oracle reference."
    )
    parser.add_argument(
        "--task_folder",
        type=str,
        default="sampled_10_instruction_set_for_final_experiment_251203",
        help="Task folder name inside oracle_reference and offline_batch directories.",
    )
    parser.add_argument(
        "--base_dir",
        type=Path,
        default=Path("assets/results/offline_exp_result"),
        help="Root directory containing offline_oracle_reference/ and offline_batch/.",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to --base_dir.",
    )
    parser.add_argument(
        "--skip_oracle_violated",
        action="store_true",
        default=False,
        help=(
            "Exclude instructions where the oracle's own schedule violates a constraint. "
            "These entries have inflated optimal_schedule_time and distort makespan gap metrics."
        ),
    )
    parser.add_argument(
        "--tolerance-sweep",
        nargs="+",
        type=float,
        default=[5.0, 8.0, 12.5],
        metavar="TOL",
        help=(
            "Re-compute TSR for each given tolerance_abs value from saved detail_logs. "
            "No scheduler re-run needed. Example: --tolerance-sweep 5.0 8.0 12.5"
        ),
    )
    args = parser.parse_args()

    output_dir = args.output_dir or args.base_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Building raw comparison...")
    raw = build_raw(args.base_dir, args.task_folder)

    raw_path = output_dir / "offline_comparison_raw.json"
    with raw_path.open("w") as f:
        json.dump(raw, f, indent=2)
    print(f"Saved: {raw_path}")

    # Report oracle constraint violation stats
    total = violated = 0
    for cases in raw.values():
        for instructions in cases.values():
            for entry in instructions.values():
                total += 1
                if not entry.get("oracle_valid", True):
                    violated += 1
    print(f"Oracle constraint violations: {violated}/{total} instructions")

    print("Aggregating summary...")
    summary = aggregate(raw, skip_oracle_violated=args.skip_oracle_violated)

    summary_path = output_dir / "offline_analysis_summary.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print(f"Saved: {summary_path}")

    if args.tolerance_sweep:
        print(f"Running tolerance sweep: {args.tolerance_sweep} ...")
        tol_sweep = build_tol_sweep(
            args.base_dir, args.task_folder, args.tolerance_sweep
        )
        tol_path = output_dir / "offline_analysis_tol_sweep.json"
        with tol_path.open("w") as f:
            json.dump(tol_sweep, f, indent=2, sort_keys=True)
        print(f"Saved: {tol_path}")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
