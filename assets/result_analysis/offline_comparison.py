"""Compare offline batch results against oracle reference.

Produces two output files:

1. offline_comparison_raw.json
   Per scene/case/instruction: oracle fields + per-approach metrics and oracle gaps.

2. offline_analysis_summary.json
   Per approach/case: aggregated metrics (sr, tsr, makespan, makespan_sr_1,
   makespan_gap, makespan_gap_sr_1, computation_time, computation_time_gap).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.utils.common.logger import create_module_logger

logger = create_module_logger(__name__)


def build_approach_key(stem: str) -> str:
    """Convert result filename stem to a short approach key.

    Examples:
        cpm__DEFAULT__CORRECT_ESTIMATE          → cpm
        edf__DEFAULT__CORRECT_ESTIMATE          → edf
        bayesian__DEFAULT__CORRECT_ESTIMATE__w1_d1
                                                → bayesian__DEFAULT__w1_d1
        bayesian__NONE_MONITORING__CORRECT_ESTIMATE__w5_d5
                                                → bayesian__NONE_MONITORING__w5_d5
    """
    parts = stem.split("__")
    approach = parts[0]

    if approach == "cpm":
        return "cpm"
    if approach == "edf":
        return "edf"
    if approach == "bayesian":
        # parts: ["bayesian", ablation, init_prior, beam]
        ablation = parts[1]
        beam = parts[3]  # e.g. "w1_d1"
        return f"bayesian__{ablation}__{beam}"

    return stem


def _oracle_has_constraint_violation(data: dict[str, Any]) -> bool:
    """Return True when any constraint in the oracle's own detail_log is marked [False]."""
    for step in data.get("steps", []):
        for constraint_result in step.get("detail_log", {}).values():
            if isinstance(constraint_result, str) and constraint_result.startswith("[False]"):
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
                entry: dict[str, Any] = {"oracle": oracle_data, "oracle_valid": oracle_valid}

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


def aggregate(raw: dict[str, Any], *, skip_oracle_violated: bool = False) -> dict[str, Any]:
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
                [e["computation_time"] for e in entries if e["computation_time"] is not None]
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


if __name__ == "__main__":
    main()
