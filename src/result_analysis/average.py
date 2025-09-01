import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

# Add the project root to the Python path to enable imports from 'src'
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.utils.common import create_module_logger

# --- Constants ---
MIN_REQUIRED_SIMULATIONS = 1
LLM_LIST: Set[str] = {"prog_ai2thor_simulation.json", "cap_ai2thor_simulation.json"}
DAG_LIST: Set[str] = {
    "dag_bayesian_simulation.json",
    "cpm_simulation.json",
    "dag_edf_simulation.json",
}

# Scene classifications based on project structure and content
KITCHEN_SCENES: Set[str] = {
    "FloorPlan1", "FloorPlan7", "FloorPlan13", "FloorPlan18", "FloorPlan27", "FloorPlan_kitchen"
}
BATHROOM_SCENES: Set[str] = {
    "FloorPlan419", "FloorPlan422", "FloorPlan426", "FloorPlan427", "FloorPlan_bathroom"
}

# --- Logger ---
log = create_module_logger(module_name=__name__, module_log=True)


# --- Helper Functions ---
def get_scene_type(scene_name: str) -> str:
    """Determines scene type ('kitchen' or 'bathroom') from scene name."""
    if scene_name in KITCHEN_SCENES:
        return "kitchen"
    if scene_name in BATHROOM_SCENES:
        return "bathroom"
    log.warning(f"Scene '{scene_name}' could not be classified as 'kitchen' or 'bathroom'.")
    return "unknown"

def load_summary_data(file_path: Path) -> Dict[str, Any]:
    """Loads and returns data from a JSON summary file."""
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
        log.error(f"Failed to read file: {file_path} - {e}")
        return {}

def compute_stats(metrics_dict: Dict[str, List[float]], min_samples: int) -> Dict[str, float]:
    """
    Computes the average and variance for each metric in the dictionary.

    Args:
        metrics_dict: A dictionary where keys are metric names and values are lists of numbers.
        min_samples: The minimum number of data points required to compute stats.

    Returns:
        A dictionary with computed average and variance for each metric.
    """
    results = {}
    for metric, values in metrics_dict.items():
        # Ensure values are valid floats
        valid_values = [v for v in values if isinstance(v, (int, float)) and not math.isinf(v)]
        
        if len(valid_values) >= min_samples:
            mean = statistics.mean(valid_values)
            variance = statistics.variance(valid_values) if len(valid_values) > 1 else 0.0
            results[f"{metric}_average"] = mean
            results[f"{metric}_variance"] = variance
        else:
            results[f"{metric}_average"] = None
            results[f"{metric}_variance"] = None
    return results

def make_average(base_dir: Path) -> None:
    """
    Analyzes simulation results to compute and store average and variance statistics,
    grouped by difficulty, scene type, and individual scenes.
    """
    # Nested defaultdict for flexible and deep metric storage
    metrics: Dict[str, Any] = {
        "by_difficulty": defaultdict(lambda: defaultdict(lambda: defaultdict(list))),
        "by_scene_type_and_difficulty": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))),
        "by_scene_and_difficulty": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))),
    }
    
    # --- Data Accumulation ---
    for task_dir in base_dir.iterdir():
        if not task_dir.is_dir():
            continue

        for scene_dir in task_dir.iterdir():
            if not scene_dir.is_dir():
                continue

            metadata_dir = scene_dir / "metadata"
            summary_path = metadata_dir / "summary.json"
            if not summary_path.exists():
                summary_path = metadata_dir / "summary_insuff.json"
                if not summary_path.exists():
                    continue
            
            summary_data = load_summary_data(summary_path)
            if not summary_data:
                continue

            difficulty = summary_data.get("difficulty", "unknown")
            scene = summary_data.get("scene", "unknown_scene")
            scene_type = get_scene_type(scene)

            for entry in summary_data.get("approach_comparisons", []):
                approach = entry.get("approach_name")
                if not approach:
                    continue

                def accumulate(metric_name: str, value: Any):
                    if value is None: return
                    try:
                        val = float(value)
                        if not math.isinf(val):
                            metrics["by_difficulty"][difficulty][approach][metric_name].append(val)
                            metrics["by_scene_type_and_difficulty"][scene_type][difficulty][approach][metric_name].append(val)
                            metrics["by_scene_and_difficulty"][scene][difficulty][approach][metric_name].append(val)
                    except (ValueError, TypeError):
                        pass

                # Accumulate all relevant metrics
                if approach in DAG_LIST:
                    accumulate("scheduler_makespan", entry.get("scheduler_makespan"))
                    accumulate("scheduler_timingSuccess_rate", entry.get("scheduler_timingSuccess_rate"))
                if approach in LLM_LIST:
                    accumulate("attempt", entry.get("attempt"))

                accumulate("simulation_makespan", entry.get("simulation_makespan"))
                accumulate("actionSuccess_rate", entry.get("actionSuccess_rate"))
                accumulate("computation_time", entry.get("computation_time"))
                accumulate("simulation_timingSuccess_rate", entry.get("simulation_timingSuccess_rate"))

    # --- Statistics Computation ---
    final_results = {}
    
    # 1. By Difficulty
    final_results["by_difficulty"] = {
        difficulty: {
            approach: compute_stats(metrics_dict, MIN_REQUIRED_SIMULATIONS)
            for approach, metrics_dict in approaches.items()
        }
        for difficulty, approaches in metrics["by_difficulty"].items()
    }
    
    # 2. By Scene Type and Difficulty
    final_results["by_scene_type_and_difficulty"] = {
        scene_type: {
            difficulty: {
                approach: compute_stats(metrics_dict, MIN_REQUIRED_SIMULATIONS)
                for approach, metrics_dict in approaches.items()
            }
            for difficulty, approaches in difficulties.items()
        }
        for scene_type, difficulties in metrics["by_scene_type_and_difficulty"].items()
    }

    # 3. By Scene and Difficulty
    final_results["by_scene_and_difficulty"] = {
        scene: {
            difficulty: {
                approach: compute_stats(metrics_dict, MIN_REQUIRED_SIMULATIONS)
                for approach, metrics_dict in approaches.items()
            }
            for difficulty, approaches in difficulties.items()
        }
        for scene, difficulties in metrics["by_scene_and_difficulty"].items()
    }

    # --- Save Results ---
    output_file = base_dir / "average.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=4)
        log.info(f"Average and variance results saved to '{output_file}'")
    except Exception as e:
        log.error(f"Failed to save results file: {e}")

def main():
    """Main execution function."""
    base_dir = Path(__file__).resolve().parent.parent.parent    
    result_dir = base_dir / "assets" / "results"
    make_average(result_dir)


if __name__ == "__main__":
    main()