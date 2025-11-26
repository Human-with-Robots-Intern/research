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


def get_difficulty(task_name: str) -> str:
    """
    Determines the difficulty of a task based on the number of sub-tasks in its name.

    Args:
        task_name: The name of the task directory.

    Returns:
        A string representing the difficulty ('easy', 'medium', 'hard').
    """
    critical_list = [
        "fill_bathtub_with_shower_head",
        "clean_the_toilet_with_spray_bottle_and_scrub_brush",
        "clean_the_sink_with_spray_and_dish_sponge",
        "boil_water_with_kettle",
        "cook_egg",
        "boil_potato",
        "fill_pot_with_water",
    ]
    critical_count = 0
    for critical_task in critical_list:
        if critical_task in task_name:
            critical_count += 1

    if critical_count == 0:
        return "easy"
    elif critical_count == 1:
        return "medium"
    else:
        return "hard"


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
        "by_scene": defaultdict(lambda: defaultdict(lambda: defaultdict(list))),
        "by_scene_type": defaultdict(lambda: defaultdict(lambda: defaultdict(list))),
        "by_scene_and_difficulty": defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        ),
        "by_scene_type_and_difficulty": defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        ),
    }

    # --- Data Accumulation ---
    log.info("Starting data accumulation from result files...")
    unclassified_scenes = set()
    file_count = 0

    for task_dir in base_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name == "average":
            continue

        task_name = task_dir.name
        difficulty = get_difficulty(task_name)

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

                # --- Enhanced Debugging ---
                if scene_type == "unknown":
                    unclassified_scenes.add(scene_name)

                log.debug(
                    f"Processing: {json_file.relative_to(base_dir)} | "
                    f"Scene: {scene_name} (Type: {scene_type}) | "
                    f"Difficulty: {difficulty} | "
                    f"Approach: {approach_name}"
                )
                # -------------------------

                data = load_json_data(json_file)
                if not data:
                    continue

                for metric_key in METRIC_KEYS:
                    value = data.get(metric_key)
                    if value is not None:
                        try:
                            val = float(value)
                            metrics["by_scene"][scene_name][approach_name][
                                metric_key
                            ].append(val)
                            metrics["by_scene_type"][scene_type][approach_name][
                                metric_key
                            ].append(val)
                            metrics["by_scene_and_difficulty"][scene_name][difficulty][
                                approach_name
                            ][metric_key].append(val)
                            metrics["by_scene_type_and_difficulty"][scene_type][
                                difficulty
                            ][approach_name][metric_key].append(val)
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
        "by_scene": defaultdict(dict),
        "by_scene_type": defaultdict(dict),
        "by_scene_and_difficulty": defaultdict(dict),
        "by_scene_type_and_difficulty": defaultdict(dict),
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

    # 3. By Scene and Difficulty
    for scene, difficulties in metrics["by_scene_and_difficulty"].items():
        final_results["by_scene_and_difficulty"][scene] = defaultdict(dict)
        for difficulty, approaches in difficulties.items():
            for approach, metrics_dict in approaches.items():
                final_results["by_scene_and_difficulty"][scene][difficulty][
                    approach
                ] = {
                    metric: compute_stats(values, MIN_REQUIRED_SIMULATIONS)
                    for metric, values in metrics_dict.items()
                }

    # 4. By Scene Type and Difficulty
    for scene_type, difficulties in metrics["by_scene_type_and_difficulty"].items():
        final_results["by_scene_type_and_difficulty"][scene_type] = defaultdict(dict)
        for difficulty, approaches in difficulties.items():
            for approach, metrics_dict in approaches.items():
                final_results["by_scene_type_and_difficulty"][scene_type][difficulty][
                    approach
                ] = {
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
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Analyze simulation results.")
    parser.add_argument(
        "base_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parent),
        help="The base directory containing the results to analyze. Defaults to the script's directory.",
    )
    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    if not base_dir.is_dir():
        log.error(
            f"Provided base directory does not exist or is not a directory: {base_dir}"
        )
        return

    make_average(base_dir)


if __name__ == "__main__":
    main()
