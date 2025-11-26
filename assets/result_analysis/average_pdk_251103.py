import argparse
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Add the project root to the Python path to enable imports from 'src'
sys.path.append(str(Path(__file__).resolve().parents[3]))

from src.utils.common import create_module_logger

# --- Constants ---
MIN_REQUIRED_SIMULATIONS = 1
APPROACH_LIST: Set[str] = {
    "prog_ai2thor_simulation.json",
    "cap_ai2thor_simulation.json",
    "dag_bayesian_simulation.json",
    "cpm_simulation.json",
    "dag_edf_simulation.json",
    "dag_bayesian_simulation_DEFAULT.json",
    "dag_bayesian_simulation_GREEDY.json",
    "dag_bayesian_simulation_NONE_MONITORING.json",
    "dag_bayesian_simulation_NONE_REMAINING_WORK.json",
    "dag_bayesian_simulation_NONE_URGENCY.json",
}

# Scene classifications based on project structure and content
KITCHEN_SCENES: Set[str] = {
    "FloorPlan1",
    "FloorPlan7",
    "FloorPlan13",
    "FloorPlan18",
    "FloorPlan27",
    "FloorPlan_kitchen",
}
BATHROOM_SCENES: Set[str] = {
    "FloorPlan419",
    "FloorPlan422",
    "FloorPlan426",
    "FloorPlan427",
    "FloorPlan_bathroom",
}

# Metrics to extract from JSON files
METRIC_KEYS: List[str] = [
    "computation_time",
    "simulation_makespan",
    "scheduler_makespan",
    "total_primitive_actions",
    "success_rate",
    "timing_success_rate_sim",
    "timing_success_rate_sched",
]


# --- Logger ---
log = create_module_logger(module_name=__name__, module_log=True)


# --- Helper Functions ---
def get_scene_type(scene_name: str) -> str:
    """Determines scene type ('kitchen' or 'bathroom') from scene name."""
    if scene_name in KITCHEN_SCENES:
        return "kitchen"
    if scene_name in BATHROOM_SCENES:
        return "bathroom"
    log.warning(
        f"Scene '{scene_name}' could not be classified as 'kitchen' or 'bathroom'."
    )
    return "unknown"


def load_json_data(file_path: Path) -> Dict[str, Any]:
    """Loads and returns data from a JSON file."""
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
        log.error(f"Failed to read file: {file_path} - {e}")
        return {}


def compute_stats(
    values: List[Union[int, float]], min_samples: int
) -> Dict[str, Optional[Union[float, int]]]:
    """
    Computes the average, standard deviation, and count for a list of values.
    Filters out None and -1 values.

    Args:
        values: A list of numbers.
        min_samples: The minimum number of data points required to compute stats.

    Returns:
        A dictionary with computed average, standard deviation, and count.
    """
    valid_values = [
        v
        for v in values
        if v is not None
        and v != -1
        and isinstance(v, (int, float))
        and not math.isinf(v)
    ]
    count = len(valid_values)

    if count >= min_samples:
        mean = statistics.mean(valid_values) if count > 0 else 0.0
        std_dev = statistics.stdev(valid_values) if count > 1 else 0.0
        return {"average": mean, "std": std_dev, "count": count}

    return {"average": None, "std": None, "count": count}


def make_average(base_dir: Path) -> None:
    """
    Analyzes simulation results to compute and store average statistics,
    grouped by various criteria.
    """
    # Nested defaultdict for flexible and deep metric storage
    metrics: Dict[str, Any] = {
        "overall": defaultdict(lambda: defaultdict(list)),
        "by_scene": defaultdict(lambda: defaultdict(lambda: defaultdict(list))),
        "by_scene_type": defaultdict(lambda: defaultdict(lambda: defaultdict(list))),
    }

    # --- Data Accumulation ---
    log.info("Starting data accumulation from result files...")
    unclassified_scenes = set()
    file_count = 0

    for task_dir in base_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name == "average":
            continue

        for scene_dir in task_dir.iterdir():
            if not scene_dir.is_dir():
                continue

            scene_name = scene_dir.name
            scene_type = get_scene_type(scene_name)
            approach_dir = scene_dir / "approach"

            if not approach_dir.is_dir():
                continue

            for json_file in approach_dir.glob("*.json"):
                file_count += 1
                approach_name = json_file.name
                if approach_name not in APPROACH_LIST:
                    continue

                if scene_type == "unknown":
                    unclassified_scenes.add(scene_name)

                log.debug(
                    f"Processing: {json_file.relative_to(base_dir)} | "
                    f"Scene: {scene_name} (Type: {scene_type}) | "
                    f"Approach: {approach_name}"
                )

                data = load_json_data(json_file)
                if not data:
                    continue

                for metric_key in METRIC_KEYS:
                    value = data.get(metric_key)
                    if value is not None:
                        try:
                            val = float(value)
                            metrics["overall"][approach_name][metric_key].append(val)
                            metrics["by_scene"][scene_name][approach_name][
                                metric_key
                            ].append(val)
                            metrics["by_scene_type"][scene_type][approach_name][
                                metric_key
                            ].append(val)
                        except (ValueError, TypeError):
                            log.warning(
                                f"Could not convert metric '{metric_key}' with value '{value}' to float in {json_file}"
                            )

    log.info(f"Finished data accumulation. Processed {file_count} JSON files.")
    if unclassified_scenes:
        log.warning(
            f"Found {len(unclassified_scenes)} unclassified scenes that were marked as 'unknown':"
        )
        for scene in sorted(list(unclassified_scenes)):
            log.warning(f"  - {scene}")

    # --- Statistics Computation ---
    final_results: Dict[str, Any] = {
        "overall": defaultdict(dict),
        "by_scene": defaultdict(dict),
        "by_scene_type": defaultdict(dict),
    }

    # 0. Overall
    for approach, metrics_dict in metrics["overall"].items():
        final_results["overall"][approach] = {
            metric: compute_stats(values, MIN_REQUIRED_SIMULATIONS)
            for metric, values in metrics_dict.items()
        }

    # 1. By Scene
    for scene, approaches in metrics["by_scene"].items():
        for approach, metrics_dict in approaches.items():
            final_results["by_scene"][scene][approach] = {
                metric: compute_stats(values, MIN_REQUIRED_SIMULATIONS)
                for metric, values in metrics_dict.items()
            }

    # 2. By Scene Type
    for scene_type, approaches in metrics["by_scene_type"].items():
        for approach, metrics_dict in approaches.items():
            final_results["by_scene_type"][scene_type][approach] = {
                metric: compute_stats(values, MIN_REQUIRED_SIMULATIONS)
                for metric, values in metrics_dict.items()
            }

    # --- Save Results ---
    output_file = base_dir / "average.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=4)
        log.info(f"Average and standard deviation results saved to '{output_file}'")
    except Exception as e:
        log.error(f"Failed to save results file: {e}")


def main():
    """Main execution function to find, analyze, and combine all result directories."""
    parser = argparse.ArgumentParser(description="Analyze simulation results.")
    parser.add_argument(
        "results_root",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "results_merged_1103"),
        help="The root directory containing all 'init_*' folders. Defaults to '../results'.",
    )
    args = parser.parse_args()
    results_root = Path(args.results_root)

    if not results_root.is_dir():
        log.error(f"Provided results root does not exist: {results_root}")
        return

    log.info(f"Starting analysis from root directory: {results_root}")

    # --- Step 1: Generate individual average.json files ---
    init_dirs = sorted(
        [d for d in results_root.iterdir() if d.is_dir() and d.name.startswith("init_")]
    )

    for init_dir in init_dirs:
        log.info(f"--- Processing Directory: {init_dir.name} ---")
        case_dirs = sorted(
            [d for d in init_dir.iterdir() if d.is_dir() and "tasks" in d.name]
        )

        if not case_dirs:
            log.warning(f"No 'tasks_*' directories found in {init_dir.name}")
            continue

        for case_dir in case_dirs:
            log.info(f"--- Analyzing Case: {case_dir.relative_to(results_root)} ---")
            try:
                make_average(case_dir)
            except Exception as e:
                log.error(f"Error processing {case_dir.name}: {e}", exc_info=True)

    log.info("--- Analysis complete for all directories. ---")

    # --- Step 2: Combine all average.json files into one summary ---
    log.info(
        "--- Starting to combine all 'average.json' files into a final summary. ---"
    )
    final_summary: Dict[str, Any] = defaultdict(dict)

    for init_dir in init_dirs:
        case_dirs = sorted(
            [d for d in init_dir.iterdir() if d.is_dir() and "tasks" in d.name]
        )
        for case_dir in case_dirs:
            average_file = case_dir / "average.json"
            if average_file.exists():
                log.info(f"Combining {average_file.relative_to(results_root)}")
                data = load_json_data(average_file)
                if data:
                    final_summary[init_dir.name][case_dir.name] = data
            else:
                log.warning(f"Could not find 'average.json' in {case_dir.name}")

    summary_output_file = results_root / "final_summary.json"
    try:
        with summary_output_file.open("w", encoding="utf-8") as f:
            json.dump(final_summary, f, indent=4)
        log.info(f"Final summary of all results saved to '{summary_output_file}'")
    except Exception as e:
        log.error(f"Failed to save the final summary file: {e}")

    log.info("--- All processes are complete. ---")


if __name__ == "__main__":
    main()
