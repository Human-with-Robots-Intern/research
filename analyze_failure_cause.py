import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class FailureAnalyzer:
    def __init__(self, results_root: str):
        self.results_root = Path(results_root)
        self.approaches = ["dag_bayesian_DEFAULT", "dag_edf"]

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
        if not logs["dag_bayesian_DEFAULT"] or not logs["dag_edf"]:
            return None

        # Analyze metrics
        metrics = {app: self.analyze_trajectory(logs[app]) for app in self.approaches}
        results = {app: self.analyze_evaluation(evals[app]) for app in self.approaches}

        # Determine Winner/Loser status
        bayesian_success = results["dag_bayesian_DEFAULT"]["success"]
        edf_success = results["dag_edf"]["success"]

        # Only analyze if EDF won (EDF success, Bayesian fail) or Bayesian is significantly worse
        if not (edf_success and not bayesian_success):
            # Check makespan if both succeeded/failed
            bayesian_makespan = metrics["dag_bayesian_DEFAULT"]["total_time"]
            edf_makespan = metrics["dag_edf"]["total_time"]
            if bayesian_makespan <= edf_makespan:
                return None  # Bayesian is fine here

        # Diagnosis Logic
        bayesian_metrics = metrics["dag_bayesian_DEFAULT"]
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
        if not results["dag_bayesian_DEFAULT"]["success"]:
            diagnosis.append(
                f"Violations: {', '.join(results['dag_bayesian_DEFAULT']['violations'][:3])}"
            )

        return {
            "case_id": str(case_id),
            "diagnosis": diagnosis,
            "metrics": {"bayesian": bayesian_metrics, "edf": edf_metrics},
        }

    def run(self):
        print(f"Scanning {self.results_root} for failure cases...")
        failure_reports = []

        # Walk through directory structure: root/difficulty/instruction/scene
        # We need to find directories that contain both approach folders
        for root, dirs, files in os.walk(self.results_root):
            if "dag_bayesian_DEFAULT" in dirs and "dag_edf" in dirs:
                report = self.compare_cases(Path(root))
                if report:
                    failure_reports.append(report)

        print(f"\nFound {len(failure_reports)} cases where Bayesian underperformed.\n")

        # Aggregate diagnoses
        diag_counts = {}
        for rep in failure_reports:
            print(f"[{rep['case_id']}]")
            for d in rep["diagnosis"]:
                print(f"  - {d}")
                key = d.split("(")[0].strip()  # Group by main reason
                diag_counts[key] = diag_counts.get(key, 0) + 1

            # Print detailed metrics comparison
            b = rep["metrics"]["bayesian"]
            e = rep["metrics"]["edf"]
            print(
                f"  Metrics (Bayesian vs EDF): Wait {b['wait_time']:.1f}/{e['wait_time']:.1f}, Nav {b['nav_time']:.1f}/{e['nav_time']:.1f}, Total {b['total_time']:.1f}/{e['total_time']:.1f}"
            )
            print("-" * 50)

        print("\n=== Failure Cause Summary ===")
        for reason, count in sorted(
            diag_counts.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"{reason}: {count} cases")


if __name__ == "__main__":
    # Point to the specific results directory
    analyzer = FailureAnalyzer("assets/results/states100")
    analyzer.run()
