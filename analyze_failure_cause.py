import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class FailureAnalyzer:
    def __init__(self, results_root: str):
        self.results_root = Path(results_root)
        self.approaches = [
            "dag_bayesian_DEFAULT",
            "dag_bayesian_NONE_MONITORING",
            # "dag_edf",
        ]

    def load_json(self, path: Path) -> Optional[Dict]:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def analyze_trajectory(self, log: List[Dict]) -> Dict:
        """Analyze trajectory log to extract key metrics."""
        if not log:
            return {
                "wait_time": 0.0,
                "nav_time": 0.0,
                "interact_time": 0.0,
                "total_actions": 0,
                "wait_count": 0,
            }

        wait_time = 0.0
        nav_time = 0.0
        interact_time = 0.0
        wait_count = 0

        for action in log:
            act_type = action.get("primitive_action", "").split()[0]
            duration = action.get("duration", 0.0)

            if act_type == "WAIT":
                wait_time += duration
                wait_count += 1
            elif act_type == "MOVE_TO":  # Assuming MOVE_TO or NAVIGATE_TO
                nav_time += duration
            else:
                interact_time += duration

        return {
            "wait_time": wait_time,
            "nav_time": nav_time,
            "interact_time": interact_time,
            "total_time": wait_time + nav_time + interact_time,
            "total_actions": len(log),
            "wait_count": wait_count,
        }

    def analyze_evaluation(self, result: Dict) -> Dict:
        """Extract success/failure status and constraint violations."""
        if not result or "tasks" not in result:
            return {"success": False, "violations": []}

        all_passed = True
        violations = []

        for task_name, task_info in result.get("tasks", {}).items():
            # Check Goal Condition (GCR)
            if not task_info.get("gcr_satisfied", False):
                all_passed = False
                violations.append(f"GCR failed: {task_name}")

            # Check Temporal Constraints (TSR)
            tsrs = task_info.get("tsrs", {})
            for constraint_name, constraint_info in tsrs.items():
                if not constraint_info.get("passed", False):
                    all_passed = False
                    dur = constraint_info.get("duration")
                    if dur is None:
                        dur_str = "None"
                    else:
                        dur_str = f"{dur:.2f}"
                    violations.append(f"TSR failed: {constraint_name} (Dur: {dur_str})")

        return {"success": all_passed, "violations": violations}

    def compare_cases(self, case_path: Path):
        """Compare Bayesian vs EDF for a single case."""
        case_id = case_path.relative_to(self.results_root)

        logs = {}
        evals = {}

        for app in self.approaches:
            app_dir = case_path / app
            logs[app] = self.load_json(app_dir / "trajectory_log.json")
            evals[app] = self.load_json(app_dir / "evaluation_result.json")

        # Skip if logs missing
        if not logs["dag_bayesian_NONE_MONITORING"] or not logs["dag_edf"]:
            return None

        # Analyze metrics
        metrics = {app: self.analyze_trajectory(logs[app]) for app in self.approaches}
        results = {app: self.analyze_evaluation(evals[app]) for app in self.approaches}

        # Determine Winner/Loser status
        bayesian_success = results["dag_bayesian_NONE_MONITORING"]["success"]
        edf_success = results["dag_edf"]["success"]

        # Only analyze if EDF won (EDF success, Bayesian fail) or Bayesian is significantly worse
        if not (edf_success and not bayesian_success):
            # Check makespan if both succeeded/failed
            bayesian_makespan = metrics["dag_bayesian_NONE_MONITORING"]["total_time"]
            edf_makespan = metrics["dag_edf"]["total_time"]
            if bayesian_makespan <= edf_makespan:
                return None  # Bayesian is fine here

        # Diagnosis Logic
        bayesian_metrics = metrics["dag_bayesian_NONE_MONITORING"]
        edf_metrics = metrics["dag_edf"]

        diagnosis = []

        # 1. Wait Time Analysis
        if bayesian_metrics["wait_time"] > edf_metrics["wait_time"] + 10.0:
            diagnosis.append(
                f"Excessive Waiting (+{bayesian_metrics['wait_time'] - edf_metrics['wait_time']:.1f}s)"
            )
        elif bayesian_metrics["wait_time"] < edf_metrics["wait_time"] - 10.0:
            # Bayesian waited LESS but still failed/slower? -> Likely failed interleaving
            diagnosis.append(
                f"Insufficient Waiting / Failed Interleaving (Wait diff: {bayesian_metrics['wait_time'] - edf_metrics['wait_time']:.1f}s)"
            )

        # 2. Navigation Efficiency
        if bayesian_metrics["nav_time"] > edf_metrics["nav_time"] * 1.3:
            diagnosis.append(
                f"Inefficient Navigation (Nav time: {bayesian_metrics['nav_time']:.1f}s vs EDF {edf_metrics['nav_time']:.1f}s)"
            )

        # 3. Constraint Violation Specifics
        if not results["dag_bayesian_NONE_MONITORING"]["success"]:
            diagnosis.append(
                f"Violations: {', '.join(results['dag_bayesian_NONE_MONITORING']['violations'][:3])}"
            )

        return {
            "case_id": str(case_id),
            "diagnosis": diagnosis,
            "metrics": {"bayesian": bayesian_metrics, "edf": edf_metrics},
        }

    def run(
        self,
        output_file: str = "missing_cases_report.txt",
        cleanup: bool = False,
        dry_run: bool = False,
    ):
        print(
            f"Scanning {self.results_root.parent} for 'states*' folders and checking missing end_state.json..."
        )
        if cleanup and dry_run:
            print("[INFO] Dry-run mode enabled. No files will be actually deleted.")

        # results_root의 상위 폴더(assets/results)에서 states* 폴더들을 찾음
        base_dir = self.results_root.parent
        target_dirs = sorted([d for d in base_dir.glob("states*") if d.is_dir()])

        # 접근법별로 결측치 현황을 저장할 딕셔너리
        # { approach_name: { states_folder_name: [missing_case_paths...] } }
        missing_summary_by_approach = {app: {} for app in self.approaches}
        total_missing_count = 0
        cleaned_count = 0

        for state_dir in target_dirs:
            print(f"\nChecking directory: {state_dir}")

            # 각 states 폴더 내부 순회
            # os.walk yields tuples (root, dirs, files)
            # We want to process them in a consistent order, so we can sort dirs in-place to affect traversal order if needed,
            # or just iterate and collect. Since we are just collecting paths, os.walk order is fine,
            # but sorting the output display is more important.
            for root, dirs, files in os.walk(state_dir):
                # Sort dirs to ensure consistent walk order if we cared, but os.walk order is usually sufficient for collection.
                # However, to be deterministic:
                dirs.sort()

                # assets/results/statesXX/tasks_N_.../instruction/scene 이 구조라고 가정하면
                # statesXX 폴더 기준으로 상대 경로 depth가 3인 곳이 scene 폴더임.

                rel_path = Path(root).relative_to(state_dir)

                # Filter out 'constraint_0' (no constraints) cases
                # path string example: tasks_2_constraints_2/... or tasks_4_constraints_0/...
                if "constraints_0" in str(rel_path):
                    continue

                # rel_path parts: (tasks_..., instruction, scene) -> len == 3
                if len(rel_path.parts) == 3:
                    # 이곳은 Scene 폴더임. 여기서 모든 approach를 검사해야 함.
                    for app in self.approaches:
                        app_path = Path(root) / app
                        is_missing = False

                        # 1. 폴더 자체가 없는 경우
                        if not app_path.exists():
                            is_missing = True
                        # 2. 폴더는 있는데 end_state.json이 없는 경우
                        elif not (app_path / "end_state.json").exists():
                            is_missing = True
                            # Cleanup incomplete files if requested
                            if cleanup:
                                if self._cleanup_incomplete_files(
                                    app_path, dry_run=dry_run
                                ):
                                    cleaned_count += 1

                        if is_missing:
                            if state_dir.name not in missing_summary_by_approach[app]:
                                missing_summary_by_approach[app][state_dir.name] = []

                            missing_summary_by_approach[app][state_dir.name].append(
                                str(rel_path)
                            )
                            total_missing_count += 1

        # --- Report Generation ---
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("MISSING 'end_state.json' SUMMARY BY BASELINE")
        report_lines.append("=" * 60)

        if total_missing_count == 0:
            report_lines.append("All clean! No missing end_state.json files found.")
        else:
            for app, folder_map in missing_summary_by_approach.items():
                if not folder_map:
                    continue

                report_lines.append(f"\n>>> Baseline: {app}")
                # Sort by folder name (states10, states100, etc.)
                for folder, cases in sorted(folder_map.items()):
                    sorted_cases = sorted(cases)
                    report_lines.append(
                        f"  [{folder}] - {len(sorted_cases)} cases missing:"
                    )
                    for c in sorted_cases:
                        report_lines.append(f"    - {c}")

        report_lines.append("-" * 60)
        report_lines.append(
            f"Total missing cases (all baselines): {total_missing_count}"
        )
        if cleanup:
            msg = "would be cleaned" if dry_run else "cleaned"
            report_lines.append(f"Total incomplete folders {msg}: {cleaned_count}")
        report_lines.append("=" * 60)

        # Print to console
        print("\n".join(report_lines))

        # Save to file
        with open(output_file, "w") as f:
            f.write("\n".join(report_lines))
        print(f"\nReport saved to {output_file}")

    def _cleanup_incomplete_files(
        self, folder_path: Path, dry_run: bool = False
    ) -> bool:
        """
        Remove incomplete result files from the directory.
        Returns True if any file was found and processed (deleted or marked for deletion).
        """
        # Files that might exist but are invalid without end_state.json
        targets = ["trajectory_log.json", "evaluation_result.json"]
        found_any = False

        for target in targets:
            target_path = folder_path / target
            if target_path.exists():
                found_any = True
                if dry_run:
                    print(f"[Dry-Run] Would remove incomplete file: {target_path}")
                else:
                    try:
                        target_path.unlink()
                        print(f"[Clean] Removed incomplete file: {target_path}")
                    except Exception as e:
                        print(f"[Error] Failed to remove {target_path}: {e}")
        return found_any


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze failure causes and missing results."
    )
    parser.add_argument(
        "--results_root",
        type=str,
        default="assets/results/states60",
        help="Path to the results directory (e.g., assets/results/states60).",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="If set, deletes incomplete result files (e.g. trajectory_log.json without end_state.json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set with --cleanup, only shows what would be deleted without actually deleting.",
    )

    args = parser.parse_args()

    # Point to the specific results directory
    analyzer = FailureAnalyzer(args.results_root)
    analyzer.run(cleanup=args.cleanup, dry_run=args.dry_run)
