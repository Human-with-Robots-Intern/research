"""
This script diagnoses which simulation runs are missing by comparing the expected
runs defined in a config file against the actual result files. It then generates
a new config file to re-run only the missing simulations.
"""

import json
import re

# Add project root to Python path
import sys
from itertools import product
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.utils.common import create_module_logger

# Initialize logger
log = create_module_logger(module_name=__name__, module_log=True)


def load_config(config_path: Path) -> dict:
    """Loads a YAML configuration file."""
    if not config_path.exists():
        log.error(f"Configuration file not found at: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_instructions_from_json(scene_name: str) -> list[str]:
    """
    Loads instructions for a given scene from the corresponding JSON file(s).
    This logic mirrors the one in `run_all.py` to ensure consistency. It first
    loads a base instruction file (e.g., kitchen_scene.json) and then loads
    a scene-specific file (e.g., FloorPlan1.json) if it exists.
    """
    try:
        number = int(re.search(r"(\d+)$", scene_name).group(1))
    except (AttributeError, ValueError):
        # Default to kitchen if no number is found, or handle as an error
        log.warning(
            f"Could not parse scene number from '{scene_name}'. Defaulting to kitchen logic."
        )
        number = 1

    if number >= 400:
        base_file = "bathroom_scene.json"
    elif number >= 300:
        base_file = "real_world_scene.json"
    else:
        base_file = "kitchen_scene.json"

    instructions = []
    nl_instructions_dir = Path("assets/tasks/nl_instructions")

    # 1. Load base instructions
    base_path = nl_instructions_dir / base_file
    if base_path.exists():
        try:
            with base_path.open("r", encoding="utf-8") as f:
                base_data = json.load(f)
                # Handle nested structures in files like real_world.json
                if "instructions" in base_data:
                    instructions.extend(base_data["instructions"])
                else:
                    for key in base_data:
                        if isinstance(base_data[key], list):
                            instructions.extend(base_data[key])
        except Exception as e:
            log.error(
                f"Failed to load or parse base instructions from {base_path}: {e}"
            )
    else:
        log.warning(f"Base instruction file not found: {base_path}")

    # 2. Load scene-specific instructions and append them
    scene_path = nl_instructions_dir / f"{scene_name}.json"
    if scene_path.exists():
        try:
            with scene_path.open("r", encoding="utf-8") as f:
                scene_data = json.load(f)
                if "instructions" in scene_data:
                    instructions.extend(scene_data["instructions"])
        except Exception as e:
            log.error(
                f"Failed to load or parse scene-specific instructions from {scene_path}: {e}"
            )
    else:
        log.debug(
            f"No scene-specific instruction file found for {scene_name} (this is okay)."
        )

    return instructions


def find_missing_runs(base_config: dict, results_dir: Path) -> dict:
    """
    Identifies missing simulation runs and returns a dictionary for re-running them.
    """
    missing_runs = {}

    approaches = base_config.get("approaches", [])
    scene_types = base_config.get("scene_type", [])
    if isinstance(scene_types, str):
        scene_types = [scene_types]

    scene_list = []
    for scene_type in scene_types:
        scene_list.extend(base_config.get("scene_lists", {}).get(scene_type, []))

    num_runs = base_config.get("num_runs_per_instruction", 1)

    log.info("Checking for missing result files...")

    total_expected = 0
    total_missing = 0

    for scene in scene_list:
        missing_runs[scene] = []
        # This list determines WHICH and HOW MANY instructions to check for a scene.
        instructions_to_check = load_instructions_from_json(scene)
        # This list provides the CANONICAL NAMES used for result folders.
        # It's crucial that this list is sorted to match the implicit order used by the runner.
        task_files_for_naming = sorted(
            list(Path(f"assets/tasks/{scene}").glob("*.json"))
        )

        # In predefined mode, instructions are referenced by number (index).
        if base_config.get("predefined"):
            instruction_source = list(range(1, len(instructions_to_check) + 1))
        else:
            # In non-predefined mode, the instruction string itself is used.
            instruction_source = instructions_to_check

        total_expected_for_scene = len(instruction_source) * len(approaches) * num_runs
        total_expected += total_expected_for_scene

        for instruction, approach_path in product(instruction_source, approaches):
            # Resolve the name used for the result folder.
            if isinstance(instruction, int):
                # Predefined mode: use the N-th file stem from the scene's task directory.
                # The index `instruction - 1` maps the 1-based instruction number
                # to the 0-based list of sorted task files.
                if not (0 < instruction <= len(task_files_for_naming)):
                    log.warning(
                        f"Instruction index {instruction} is out of bounds for scene '{scene}' "
                        f"which has {len(task_files_for_naming)} task files. This check will be skipped."
                    )
                    continue
                instr_name = task_files_for_naming[instruction - 1].stem
            else:
                # Non-predefined mode: the instruction string from nl_instructions is the name.
                instr_name = instruction

            approach_stem = Path(approach_path).stem

            # Count existing valid runs by globbing for folders with the correct name pattern.
            found_runs = 0
            for folder in results_dir.glob(f"{instr_name}_*"):
                if not folder.is_dir():
                    continue
                result_file = (
                    folder / scene / "approach" / f"{approach_stem}_simulation.json"
                )
                if result_file.exists():
                    found_runs += 1

            # If the number of found runs is less than required, it's missing.
            if found_runs < num_runs:
                num_missing_for_this = num_runs - found_runs
                # Use the original instruction (number or string) for the rerun config.
                if instruction not in missing_runs[scene]:
                    missing_runs[scene].append(instruction)
                # Count the total number of individual missing simulation files.
                total_missing += num_missing_for_this

    log.info("-" * 40)
    log.info(f"Total expected runs: {total_expected}")
    log.info(f"Total missing runs: {total_missing}")

    # Clean up scenes with no missing runs
    return {scene: instr for scene, instr in missing_runs.items() if instr}


def main():
    """Main execution function."""
    scripts_dir = Path(__file__).parent
    base_config_path = scripts_dir / "run_all_config.yaml"
    results_dir = Path("assets/results/init_140")  # Assuming this is the target dir

    # 1. Load the base configuration
    base_config = load_config(base_config_path)
    if not base_config:
        return

    # 2. Find all missing runs
    missing_runs_dict = find_missing_runs(base_config, results_dir)

    if not missing_runs_dict:
        log.info("All expected result files are present. No re-run needed.")
        return

    # 3. Create a new configuration for re-running
    rerun_config = base_config.copy()
    rerun_config["execute_dict"] = missing_runs_dict

    # Ensure num_runs is 1 if not specified, to avoid folder name mismatches
    if "num_runs_per_instruction" not in rerun_config:
        rerun_config["num_runs_per_instruction"] = 1

    rerun_config_path = scripts_dir / "rerun_missing_config.yaml"
    with open(rerun_config_path, "w", encoding="utf-8") as f:
        yaml.dump(rerun_config, f, default_flow_style=False, sort_keys=False)

    log.info("-" * 40)
    log.info(f"Successfully created re-run config: '{rerun_config_path}'")
    log.info("This file contains only the tasks for the missing runs.")
    log.info("\nTo re-run the missing simulations, execute the following command:")
    log.info(f"python scripts/run_all.py --config {rerun_config_path.name}")


if __name__ == "__main__":
    main()
