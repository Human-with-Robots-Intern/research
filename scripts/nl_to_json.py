import argparse
import json
import re
from typing import Dict, Iterable, List

from src.utils.common import create_module_logger
from src.utils.config.constants import ASSETS_PATH
from src.utils.task.task_generator import TaskGenerator
from src.utils.task.task_util import TaskUtil

logger = create_module_logger(__name__, module_log=True)


def load_instructions() -> Dict:
    """Load all instructions from the generated criteria-based JSON file.
    Returns:
        The entire data structure from the JSON file.
    """
    instruction_file = (
        ASSETS_PATH / "tasks" / "decomposed_final_revision_metadata_251203_realworld.json"
    )
    try:    
        with open(instruction_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Instruction file not found: {instruction_file}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse {instruction_file}: {e}")
        raise


def filter_cases(
    all_case_keys: Iterable[str], task_counts: List[int], constraint_counts: List[int]
) -> List[str]:
    """Filter case keys based on user-provided task and constraint counts."""
    if not task_counts and not constraint_counts:
        return sorted(list(all_case_keys))  # No filter, return all

    filtered_keys = []
    for key in all_case_keys:
        match = re.match(r"tasks_(\d+)_constraints_(\d+)", key)
        if not match:
            continue
        num_t, num_c = map(int, match.groups())

        # If filters are provided, the key must match them
        task_match = (not task_counts) or (num_t in task_counts)
        constraint_match = (not constraint_counts) or (num_c in constraint_counts)

        if task_match and constraint_match:
            filtered_keys.append(key)

    return sorted(filtered_keys)


def main() -> None:
    """Process instructions from the criteria-based JSON file to generate structured task data."""
    argparser = argparse.ArgumentParser(
        description="Generate structured tasks from generated_instructions_by_criteria.json.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    argparser.add_argument(
        "--task-counts",
        type=int,
        nargs="*",
        default=[2, 3, 4],
        help="A list of task counts to process (e.g., 2 3). Processes all if not provided.",
    )
    argparser.add_argument(
        "--constraint-counts",
        type=int,
        nargs="*",
        default=[0, 1, 2],
        help="A list of constraint counts to process (e.g., 0 1). Processes all if not provided.",
    )
    args = argparser.parse_args()

    # --- Load Data ---
    instruction_data = load_instructions()
    all_cases = instruction_data.get("instructions_by_case", {})
    cases_to_process = filter_cases(
        all_cases.keys(), args.task_counts, args.constraint_counts
    )

    KITCHEN_SCENES = [
        "FloorPlan1",
        "FloorPlan7",
        "FloorPlan13",
        "FloorPlan18",
        "FloorPlan27",
    ]
    REALWORLD_SCENES = [
        "FloorPlan301",
    ]
    SCENE_NAME_LIST = REALWORLD_SCENES

    # --- Main Processing Loop ---
    for case_key in cases_to_process:
        logger.info(f"### Processing Case: {case_key.upper()} ###")
        case_data = all_cases[case_key]
        common_instructions = case_data.get("common", [])

        for scene_name in SCENE_NAME_LIST:
            logger.info(f"--- Processing scene: {scene_name} ---")
            scene_instructions = case_data.get(scene_name, [])
            combined_instructions = list(
                dict.fromkeys(scene_instructions + common_instructions)
            )

            if not combined_instructions:
                logger.warning(
                    f"No instructions found for scene {scene_name} in case {case_key}"
                )
                continue

            output_dir = (
                ASSETS_PATH
                / "tasks"
                / "decomposed_final_revision_metadata_251203_realworld"
                / case_key
                / scene_name
            )
            output_dir.mkdir(parents=True, exist_ok=True)

            # --- Identify existing instructions and determine starting index ---
            existing_instructions = set()
            last_idx = 0
            for f in output_dir.glob("*.json"):
                # "01_heat_the_bread.json" -> "heat the bread"
                base_name = re.sub(r"^\d+_", "", f.stem).replace("_", " ")
                existing_instructions.add(base_name)

                match = re.match(r"(\d+)_", f.name)
                if match:
                    last_idx = max(last_idx, int(match.group(1)))

            # --- Filter for only new instructions ---
            new_instructions = [
                inst
                for inst in combined_instructions
                if inst not in existing_instructions
            ]

            if not new_instructions:
                logger.info(
                    f"No new instructions to add for scene {scene_name}. All {len(existing_instructions)} files are up-to-date."
                )
                continue

            logger.info(
                f"Found {len(new_instructions)} new instructions to process for scene {scene_name}."
            )

            # --- Process and save only the new instructions ---
            for idx, instruction in enumerate(new_instructions, start=last_idx + 1):
                logger.info(
                    f"Processing instruction {idx - last_idx}/{len(new_instructions)} (file index {idx}): {instruction}"
                )
                result = TaskGenerator(is_rag=False, is_test=True).generate_task(
                    instruction, scene_name
                )

                output_file_name = instruction.replace(" ", "_").replace("'", "")
                output_file = output_dir / f"{idx:02d}_{output_file_name}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                logger.info(f"Saved result to {output_file}")

                # For logging/debugging: build tasks and constraints to verify the result
                try:
                    subtasks, constraints, _ = TaskUtil.build_tasks_and_constraints(
                        task_data=result,
                        scene_file_name=f"{scene_name}_physics_environment.json",
                        enable_decomposition=True,
                    )
                    logger.debug(f"Subtasks: {subtasks}")
                    logger.debug(f"Constraints: {constraints}")
                except Exception as e:
                    logger.error(
                        f"Error during TaskUtil validation for '{instruction}': {e}"
                    )

                logger.info("-" * 20)

            logger.info(f"Finished processing scene: {scene_name}")
            logger.info("=" * 40)

        logger.info(f"### Finished Case: {case_key.upper()} ###\n")


if __name__ == "__main__":
    main()
