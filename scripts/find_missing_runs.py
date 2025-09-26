"""
This script diagnoses which simulation runs are missing by comparing the expected
runs defined in a config file against the actual result files. It then generates
a new config file to re-run only the missing simulations.
"""

import json
from itertools import product
from pathlib import Path

import yaml

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
    Loads instructions for a given scene from the corresponding JSON file.
    """
    number_match = re.search(r"\d+$", scene_name)
    if not number_match:
        base_file = "kitchen_scene.json"  # Default or handle error
    else:
        number = int(number_match.group())
        if number >= 400:
            base_file = "bathroom_scene.json"
        elif number >= 300:
            base_file = "real_world_scene.json"
        else:
            base_file = "kitchen_scene.json"

    instructions = []
    base_path = Path("assets/tasks/nl_instructions") / base_file
    try:
        with base_path.open("r", encoding="utf-8") as f:
            base_data = json.load(f)
            instructions.extend(base_data["instructions"])
    except Exception as e:
        log.error(f"Failed to load base instructions from {base_path}: {e}")
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
        instructions = load_instructions_from_json(scene)

        # In predefined mode, instructions are referenced by number
        if base_config.get("predefined"):
            instruction_source = list(range(1, len(instructions) + 1))
        else:
            instruction_source = instructions

        for instruction, approach_path, run_idx in product(
            instruction_source, approaches, range(num_runs)
        ):
            total_expected += 1

            # Resolve instruction name if it's an index
            if isinstance(instruction, int):
                instr_name = Path(instructions[instruction - 1]).stem
            else:
                instr_name = instruction

            # Normalize for folder naming conventions (e.g., spaces, special chars)
            # This logic should mirror how result folders are named in `run_all.py`.
            # A simple replacement is a good start.
            folder_name = f"{instr_name}_{run_idx + 1}"

            approach_stem = Path(approach_path).stem
            result_file = (
                results_dir
                / folder_name
                / scene
                / "approach"
                / f"{approach_stem}_simulation.json"
            )

            if not result_file.exists():
                log.warning(
                    f"Missing result for: Scene='{scene}', Approach='{approach_stem}', Instruction='{instr_name}' (Run {run_idx+1})"
                )
                if instruction not in missing_runs[scene]:
                    missing_runs[scene].append(instruction)
                total_missing += 1

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
    import re

    main()
