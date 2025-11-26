"""
This script loads the 'average.json' file, processes it into a pandas DataFrame,
and displays key metrics in a tabular format for better readability.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def load_and_flatten_json(file_path: Path) -> pd.DataFrame:
    """
    Loads the average.json file and flattens its nested structure into a DataFrame.

    The resulting DataFrame will have a "long format" where each row represents
    a single metric for a specific combination of grouping criteria.

    Args:
        file_path: The path to the 'average.json' file.

    Returns:
        A pandas DataFrame containing the flattened data.
    """
    if not file_path.exists():
        print(f"Error: File not found at '{file_path}'")
        return pd.DataFrame()

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    all_records: List[Dict[str, Any]] = []

    # The structure is nested. We need to parse it level by level.
    for group_key, group_data in data.items():
        for key1, key1_data in group_data.items():
            # This handles groupings with 2 levels (e.g., by_scene) and 3 levels (e.g., by_scene_and_difficulty)
            if not isinstance(next(iter(key1_data.values())), dict) or not any(
                isinstance(v, dict) for v in key1_data.values()
            ):
                continue  # Should not happen with current structure

            # Check if the next level is difficulty/approach or just approach
            is_three_level = any(
                isinstance(v, dict) and k in ["easy", "medium", "hard"]
                for k, v in key1_data.items()
            )

            if is_three_level:
                for key2, key2_data in key1_data.items():
                    for approach, metrics in key2_data.items():
                        for metric, stats in metrics.items():
                            record = {
                                "group": group_key,
                                "scene_type": key1,
                                "difficulty": key2,
                                "approach": approach,
                                "metric": metric,
                                "average": stats.get("average"),
                                "std": stats.get("std"),
                                "count": stats.get("count"),
                            }
                            all_records.append(record)
            else:
                for approach, metrics in key1_data.items():
                    for metric, stats in metrics.items():
                        record = {
                            "group": group_key,
                            "scene_type": key1,
                            "difficulty": None,  # No second level for this group
                            "approach": approach,
                            "metric": metric,
                            "average": stats.get("average"),
                            "std": stats.get("std"),
                            "count": stats.get("count"),
                        }
                        all_records.append(record)

    return pd.DataFrame(all_records)


def display_key_metrics(df: pd.DataFrame) -> None:
    """
    Filters and displays key metrics in a structured and readable format.

    This function demonstrates how to pivot the data to compare approaches
    for specific metrics.

    Args:
        df: The DataFrame containing all the flattened results.
    """
    if df.empty:
        print("DataFrame is empty. Cannot display metrics.")
        return

    # Filter to only use the desired grouping for this view
    df = df[df["group"] == "by_scene_type_and_difficulty"].copy()
    if df.empty:
        print("No data found for the 'by_scene_type_and_difficulty' group.")
        return

    # --- Setup: Define all possible categories to ensure they appear in the output ---
    scene_types = sorted(df["scene_type"].unique())
    difficulties = ["hard", "medium", "easy"]
    approaches = [
        "cpm_simulation.json",
        "dag_edf_simulation.json",
        "dag_bayesian_simulation.json",
    ]

    # Filter to only include approaches present in the data
    approaches = [a for a in approaches if a in df["approach"].unique()]

    # Create a full multi-index for all combinations
    full_index = pd.MultiIndex.from_product(
        [scene_types, difficulties], names=["scene_type", "difficulty"]
    )

    # Apply categorical types to ensure consistent ordering
    df["difficulty"] = pd.Categorical(
        df["difficulty"], categories=difficulties, ordered=True
    )
    df["approach"] = pd.Categorical(df["approach"], categories=approaches, ordered=True)

    # --- Example 1: Show Simulation Makespan by Scene Type and Difficulty ---
    print("=" * 80)
    print("Metric: Simulation Makespan (Average)")
    print("-" * 80)

    # Filter for the specific group and metric
    makespan_df = df[
        (df["group"] == "by_scene_type_and_difficulty")
        & (df["metric"] == "simulation_makespan")
    ]

    if not makespan_df.empty:
        # Pivot the table for easy comparison
        makespan_pivot = (
            makespan_df.pivot_table(
                index=["scene_type", "difficulty"],
                columns="approach",
                values="average",
                observed=False,
            )
            .reindex(full_index)
            .round(2)
        )
        print(makespan_pivot)
    else:
        print("No data found for 'simulation_makespan'.")

    print("\n" * 2)

    # --- Example 2: Show Timing Success Rate by Scene Type and Difficulty ---
    print("=" * 80)
    print("Metric: Timing Success Rate (Simulation, Average)")
    print("-" * 80)

    # Filter for the specific group and metric
    timing_df = df[
        (df["group"] == "by_scene_type_and_difficulty")
        & (df["metric"] == "timing_success_rate_sim")
    ]

    if not timing_df.empty:
        # Pivot the table for easy comparison
        timing_pivot = (
            timing_df.pivot_table(
                index=["scene_type", "difficulty"],
                columns="approach",
                values="average",
                observed=False,
            )
            .reindex(full_index)
            .round(3)
        )
        print(timing_pivot)
    else:
        print("No data found for 'timing_success_rate_sim'.")

    print("=" * 80)


def main() -> None:
    """Main execution function."""
    base_dir = Path(__file__).resolve().parent
    json_file_path = base_dir / "average.json"

    # Load and process the data
    results_df = load_and_flatten_json(json_file_path)

    # Set pandas display options for better console output
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_columns", 500)
    pd.set_option("display.width", 120)

    # Display the formatted tables
    display_key_metrics(results_df)

    # --- Tip for further analysis ---
    # You can easily save the entire dataset to a CSV file like this:
    # csv_output_path = base_dir / "average_results.csv"
    # results_df.to_csv(csv_output_path, index=False)
    # print(f"\nFull dataset saved to '{csv_output_path}'")


if __name__ == "__main__":
    main()
