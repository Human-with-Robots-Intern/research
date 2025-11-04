import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def restructure_init_dirs(base_dir: Path, output_dir: Path):
    """
    Consolidates numbered (init) directories into a single directory per task.
    e.g., '01_task.json/' and '08_task.json/' contents are moved into 'task.json/'.
    """
    print(f"--- Step 1: Consolidating INIT directories for {base_dir.name} ---")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    numbered_dirs_map = defaultdict(list)
    pattern = re.compile(r"^(\d{2})_(.*\.json)$")

    for item in base_dir.iterdir():
        if item.is_dir():
            match = pattern.match(item.name)
            if match:
                prefix, base_name = match.groups()
                numbered_dirs_map[base_name].append(item)

    print(f"Found {len(numbered_dirs_map)} unique tasks with numbered directories.")

    for base_name, source_dirs in numbered_dirs_map.items():
        target_task_dir = output_dir / base_name
        target_task_dir.mkdir(exist_ok=True)

        for source_dir in source_dirs:
            for floor_plan_dir in source_dir.iterdir():
                if floor_plan_dir.is_dir():
                    shutil.copytree(
                        floor_plan_dir,
                        target_task_dir / floor_plan_dir.name,
                        dirs_exist_ok=True,
                    )

    print(f"Consolidation complete. Cleaned INIT directories are in: {output_dir}")


def merge_init_and_end(
    init_cleaned_dir: Path, end_source_dir: Path, final_output_dir: Path
):
    """
    Merges the cleaned init directories with the unnumbered (end) directories.
    """
    print(f"--- Step 2: Merging CLEANED INIT and END for {end_source_dir.name} ---")
    if final_output_dir.exists():
        shutil.rmtree(final_output_dir)
    final_output_dir.mkdir(parents=True)

    # Find unnumbered (end) dirs
    end_dirs = {}
    for item in end_source_dir.iterdir():
        if (
            item.is_dir()
            and not re.match(r"^\d{2}_", item.name)
            and item.name.endswith(".json")
        ):
            end_dirs[item.name] = item

    print(
        f"Found {len(list(init_cleaned_dir.iterdir()))} cleaned init tasks and {len(end_dirs)} end tasks."
    )

    for init_task_dir in init_cleaned_dir.iterdir():
        if not init_task_dir.is_dir():
            continue

        task_name = init_task_dir.name
        end_task_dir = end_dirs.get(task_name)

        if not end_task_dir:
            print(
                f"Warning: No matching END directory for INIT task '{task_name}'. Skipping."
            )
            continue

        # Now, iterate through FloorPlans and approaches
        for init_floor_plan in init_task_dir.iterdir():
            if not init_floor_plan.is_dir():
                continue

            end_floor_plan = end_task_dir / init_floor_plan.name
            if not end_floor_plan.exists():
                continue

            for init_approach in init_floor_plan.iterdir():
                if not init_approach.is_dir():
                    continue

                end_approach = end_floor_plan / init_approach.name
                if not end_approach.exists():
                    continue

                init_state_file = init_approach / "init_state.json"
                end_state_file = end_approach / "end_state.json"

                if init_state_file.exists() and end_state_file.exists():
                    try:
                        with open(init_state_file, "r") as f:
                            init_data = json.load(f)
                        with open(end_state_file, "r") as f:
                            end_data = json.load(f)

                        merged_data = {
                            "initial_state": init_data,
                            "end_state": end_data,
                        }

                        # Create final path and save
                        target_dir = (
                            final_output_dir
                            / task_name
                            / init_floor_plan.name
                            / init_approach.name
                        )
                        target_dir.mkdir(parents=True, exist_ok=True)
                        with open(target_dir / "state.json", "w") as f:
                            json.dump(merged_data, f, indent=4)
                    except Exception as e:
                        print(
                            f"Error merging files for {task_name}/{init_floor_plan.name}/{init_approach.name}: {e}"
                        )

    print(f"Final merge complete. Output is in: {final_output_dir}")


def main():
    """Main function to run the full restructure and merge pipeline."""
    root_path = Path("/home/dongkyu/pdk_ws/research/assets/results")
    dirs_to_process = ["states60", "states100", "states140"]

    for dir_name in dirs_to_process:
        base_dir = root_path / dir_name
        init_cleaned_dir = root_path / f"{dir_name}_init_cleaned"
        final_merged_dir = root_path / f"{dir_name}_merged"

        if not base_dir.exists():
            print(f"Source directory {base_dir} not found. Skipping.")
            continue

        # Step 1: Consolidate init directories
        restructure_init_dirs(base_dir, init_cleaned_dir)

        # Step 2: Merge the cleaned init dirs with end dirs
        merge_init_and_end(init_cleaned_dir, base_dir, final_merged_dir)

        # Optional: Clean up the intermediate directory
        print(f"Cleaning up intermediate directory: {init_cleaned_dir}")
        shutil.rmtree(init_cleaned_dir)

        print("\n")

    print("All processing complete.")


if __name__ == "__main__":
    main()
