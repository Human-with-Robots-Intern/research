from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

# --- Mocked Utility Functions ---


def create_module_logger(name: str) -> logging.Logger:
    """Creates a basic logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = create_module_logger(__name__)


def get_instruction_difficulty(
    instruction: str, scene_name: str, checker: "TaskSuccessChecker"
) -> str:
    """
    Determines the difficulty of an instruction based on the number of tasks and critical tasks.
    Returns a string in the format 'tasks_n_constraints_m'.
    """
    parsed_tasks = checker.parse_instruction_to_tasks(instruction)
    n = len(parsed_tasks)

    critical_tasks_for_scene = checker.get_critical_tasks_for_scene(scene_name)
    m = sum(1 for task in parsed_tasks if task in critical_tasks_for_scene)

    return f"tasks_{n}_constraints_{m}"


# --- Core Classes (Combined and Adapted) ---


class TaskSuccessChecker:
    """Checks the success of tasks based on goal conditions in merged state files."""

    def __init__(self, tasks_json_path: Path) -> None:
        """Initializes the TaskSuccessChecker."""
        self.task_conditions = self._define_task_conditions()
        self.all_task_names, self.critical_tasks_by_floorplan = self._load_task_info(
            tasks_json_path
        )
        # Sort by length descending to match longer names first
        self.all_task_names.sort(key=len, reverse=True)

    def _load_task_info(
        self, json_path: Path
    ) -> tuple[list[str], dict[str, list[str]]]:
        """Loads all task names and critical task definitions from the floorplan_tasks.json file."""
        if not json_path.exists():
            logger.error(f"Tasks JSON file not found at: {json_path}")
            return [], {}
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        task_names = set()
        critical_tasks_by_floorplan = {}

        common_critical = data.get("common", {}).get("critical", [])

        for key, value in data.items():
            if isinstance(value, dict):
                # Collect all task names
                for tasks in value.values():
                    if isinstance(tasks, list):
                        task_names.update(tasks)

                # Collect critical tasks
                if key.startswith("FloorPlan"):
                    floorplan_critical = value.get("critical", [])
                    critical_tasks_by_floorplan[key] = (
                        common_critical + floorplan_critical
                    )

        # Add a "common" entry for scenes that might not have a specific floorplan entry
        critical_tasks_by_floorplan["common"] = common_critical

        return list(task_names), critical_tasks_by_floorplan

    def get_critical_tasks_for_scene(self, scene_name: str) -> list[str]:
        """Gets the list of critical tasks for a given scene (FloorPlan)."""
        # scene_name from data is like 'FloorPlan1', 'FloorPlan7', etc.
        return self.critical_tasks_by_floorplan.get(
            scene_name, self.critical_tasks_by_floorplan.get("common", [])
        )

    def _define_task_conditions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Defines success conditions for each task."""
        # This is the more comprehensive list from GCRchecker.py
        return {
            "boil_potato": [
                {
                    "object_type": "Potato",
                    "property": "isCooked",
                    "expected_value": True,
                },
                {
                    "object_type": "Pot",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "boil_water_with_kettle": [
                {
                    "object_type": "Kettle",
                    "property": "parentReceptacles",
                    "expected_value": "StoveBurner",
                },
            ],
            "boil_water_with_pot": [
                {
                    "object_type": "Pot",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "cook_egg": [
                {
                    "object_type": "Egg_Cracked",
                    "property": "isCooked",
                    "expected_value": True,
                },
            ],
            "fill_pot_with_water": [
                {
                    "object_type": "Pot",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "fill_bowl_with_water": [
                {
                    "object_type": "Bowl",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "heat_the_potato_using_microwave": [
                {
                    "object_type": "Potato",
                    "property": "isCooked",
                    "expected_value": True,
                },
            ],
            "make_a_coffee": [
                {
                    "object_type": "Mug",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "prepare_a_water_cup_with_mug": [
                {
                    "object_type": "Mug",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                },
            ],
            "put_a_statue_on_the_table": [
                {
                    "object_type": "Statue",
                    "property": "parentReceptacles",
                    "expected_value": "DiningTable",
                },
            ],
            "put_saltshaker_on_the_table": [
                {
                    "object_type": "SaltShaker",
                    "property": "parentReceptacles",
                    "expected_value": "DiningTable",
                },
            ],
            "put_the_creditcard_on_the_countertop": [
                {
                    "object_type": "CreditCard",
                    "property": "parentReceptacles",
                    "expected_value": "CounterTop",
                },
            ],
            "put_the_pencil_on_countertop": [
                {
                    "object_type": "Pencil",
                    "property": "parentReceptacles",
                    "expected_value": "CounterTop",
                },
            ],
            "throw_away_paper_towel_roll": [
                {
                    "object_type": "PaperTowelRoll",
                    "property": "parentReceptacles",
                    "expected_value": "GarbageCan",
                },
            ],
            "put_the_book_in_cabinet": [
                {
                    "object_type": "Book",
                    "property": "parentReceptacles",
                    "expected_value": "Cabinet",
                },
            ],
            "put_the_wine_bottle_inside_a_cabinet": [
                {
                    "object_type": "WineBottle",
                    "property": "parentReceptacles",
                    "expected_value": "Cabinet",
                },
            ],
            "put_salt_shaker_inside_the_safe": [
                {
                    "object_type": "SaltShaker",
                    "property": "parentReceptacles",
                    "expected_value": "Safe",
                },
            ],
            "put_apple_and_lettuce_in_fridge": [
                {
                    "object_type": "Apple",
                    "property": "parentReceptacles",
                    "expected_value": "Fridge",
                },
                {
                    "object_type": "Lettuce",
                    "property": "parentReceptacles",
                    "expected_value": "Fridge",
                },
            ],
            "heat_the_bread_using_microwave": [
                {
                    "object_type": "Bread",
                    "property": "isCooked",
                    "expected_value": True,
                },
            ],
            "open_the_blinds": [
                {"object_type": "Blinds", "property": "isOpen", "expected_value": True},
            ],
            "set_the_table": [
                {
                    "object_type": "Fork",
                    "property": "parentReceptacles",
                    "expected_value": ["DiningTable", "CounterTop"],
                },
                {
                    "object_type": "ButterKnife",
                    "property": "parentReceptacles",
                    "expected_value": ["DiningTable", "CounterTop"],
                },
            ],
            # Tasks with no defined goal state are considered successful by default
            "wash_all_fork_and_spoon": [],
            "wash_apple_and_lettuce": [],
            "wash_two_ladles": [],
            "wash_a_tomato": [],
            "wash_a_butterknife": [],
            "wash_a_spatula": [],
            "wash_plate_and_cup": [],
        }

    def load_state_from_json(self, file_path: Path) -> List[Dict[str, Any]]:
        """Loads the end_state from a merged state.json file."""
        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("end_state", [])
        except Exception as e:
            logger.error(f"Failed to load or parse state from {file_path}: {e}")
            return []

    def find_objects_by_type(
        self, state: List[Dict[str, Any]], object_type: str
    ) -> List[Dict[str, Any]]:
        """Finds objects of a specific type in the state list."""
        return [obj for obj in state if obj.get("name", "").startswith(object_type)]

    def check_object_condition(
        self, objects: List[Dict[str, Any]], property_name: str, expected_value: Any
    ) -> bool:
        """Checks if any of the given objects meet the specified condition."""
        if not objects:
            return False

        if isinstance(expected_value, list):
            if property_name == "parentReceptacles":
                for obj in objects:
                    receptacles = obj.get(property_name) or []
                    bases = [
                        r.split("|", 1)[0] if isinstance(r, str) else r
                        for r in receptacles
                    ]
                    for exp in expected_value:
                        if any(
                            (isinstance(r, str) and (exp in r or exp == base))
                            for r, base in zip(receptacles, bases)
                        ):
                            return True
                return False
            return any(obj.get(property_name) in expected_value for obj in objects)

        if property_name == "parentReceptacles":
            exp = expected_value
            for obj in objects:
                receptacles = obj.get(property_name) or []
                for r in receptacles:
                    if isinstance(r, str) and (exp in r or r.split("|", 1)[0] == exp):
                        return True
            return False

        return any(obj.get(property_name) == expected_value for obj in objects)

    def check_task_success(
        self, end_state: List[Dict[str, Any]], task_name: str
    ) -> bool:
        """Checks if a single task was successful based on its conditions."""
        if task_name not in self.task_conditions:
            logger.warning(f"Unknown task: {task_name}")
            return False

        conditions = self.task_conditions[task_name]
        if not conditions:
            return True  # No conditions means success by default

        for condition in conditions:
            objects = self.find_objects_by_type(end_state, condition["object_type"])
            if not self.check_object_condition(
                objects, condition["property"], condition["expected_value"]
            ):
                return False
        return True

    def parse_instruction_to_tasks(self, instruction: str) -> List[str]:
        """Parses an instruction string into a list of tasks based on a predefined list."""
        parsed_tasks = []
        # Replace " and " with a unique separator to handle task names with "and"
        # This logic is now based on greedy matching, so simple replacement is not enough.
        # We need to iterate and match from the predefined list.

        # Normalize instruction string by replacing " and " with "_"
        # The directory names seem to use "and" but our parsing logic should handle it.
        # Let's adjust the parsing based on the new greedy approach.
        # The instruction from directory name is like "boil_potato_and_cook_egg"
        # but our task list has "boil_potato", "cook_egg".
        # Let's stick to the greedy parsing which seems more robust.

        remaining_instruction = instruction.replace(" and ", "_and_")

        while remaining_instruction:
            found_match = False
            for task in self.all_task_names:
                # We need to handle underscores in task names vs separators
                task_as_id = task.replace("_", " ")
                task_as_id_in_instruction = task.replace(" ", "_")

                if remaining_instruction.startswith(task_as_id_in_instruction):
                    parsed_tasks.append(task)
                    remaining_instruction = remaining_instruction[
                        len(task_as_id_in_instruction) :
                    ]
                    if remaining_instruction.startswith("_and_"):
                        remaining_instruction = remaining_instruction[len("_and_") :]
                    found_match = True
                    break

            if not found_match:
                # Let's try to parse the original task names which might have spaces
                if remaining_instruction:
                    # This part is tricky because task names have spaces, and the instruction string is concatenated.
                    # The greedy approach with length-sorted task names should work.
                    pass  # Let's stick with the first logic.

        # Let's refine the parsing logic to be simpler and more direct.
        remaining_instruction = instruction.replace(" and ", "_and_")
        parsed_tasks = []
        temp_instruction = remaining_instruction
        while temp_instruction:
            found_match = False
            for task_name in self.all_task_names:
                # a task name in filename format
                task_id = task_name.replace(" ", "_")
                if temp_instruction.startswith(task_id):
                    parsed_tasks.append(task_name)
                    temp_instruction = temp_instruction[len(task_id) :]
                    if temp_instruction.startswith("_and_"):
                        temp_instruction = temp_instruction[len("_and_") :]
                    found_match = True
                    break  # Restart scan from the beginning of the list for the new remaining string
            if not found_match:
                if temp_instruction:
                    logger.warning(
                        f"Could not parse remaining instruction part: '{temp_instruction}' from original: '{instruction}'"
                    )
                break
        return parsed_tasks

    def check_instruction_success(
        self, instruction_dir_path: Path, states_dir: Path
    ) -> List[Dict[str, Any]]:
        """Calculates the success rate for all scenes and approaches for a given instruction."""
        instruction = instruction_dir_path.name.replace(".json", "")
        tasks = self.parse_instruction_to_tasks(instruction)
        instruction_results = []

        for scene_dir in instruction_dir_path.iterdir():
            if not scene_dir.is_dir():
                continue

            for approach_dir in scene_dir.iterdir():
                if not approach_dir.is_dir():
                    continue

                state_path = approach_dir / "state.json"
                result = {
                    "instruction": instruction,
                    "scene_name": scene_dir.name,
                    "approach_name": approach_dir.name,
                    "task_results": {},
                    "overall_success_rate": 0.0,
                    "successful_tasks": 0,
                    "total_tasks": len(tasks),
                    "error": None,
                }

                if not state_path.exists():
                    result["error"] = "State file not found"
                    instruction_results.append(result)
                    continue

                end_state = self.load_state_from_json(state_path)
                if not end_state:
                    result["error"] = "Failed to load end state"
                    instruction_results.append(result)
                    continue

                successful_count = 0
                for task in tasks:
                    success = self.check_task_success(end_state, task)
                    result["task_results"][task] = success
                    if success:
                        successful_count += 1

                result["successful_tasks"] = successful_count
                result["overall_success_rate"] = (
                    (successful_count / len(tasks)) * 100 if tasks else 0.0
                )
                instruction_results.append(result)

        return instruction_results

    def process_all_instructions(self, states_folder: Path) -> None:
        """Processes all instructions in a directory, calculates success rates, and saves a summary."""
        if not states_folder.exists():
            logger.error(f"States directory not found: {states_folder}")
            return

        all_results = []
        logger.info(f"Processing directory: {states_folder.name}")

        for instruction_dir in states_folder.iterdir():
            if instruction_dir.is_dir():
                all_results.extend(
                    self.check_instruction_success(instruction_dir, states_folder)
                )

        summary = {
            "total_results": len(all_results),
            "average_success_rate": (
                sum(r["overall_success_rate"] for r in all_results) / len(all_results)
                if all_results
                else 0.0
            ),
            "results": all_results,
        }

        summary_path = states_folder / "task_success_summary.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Summary for {states_folder.name} saved to: {summary_path}")
        logger.info(f"Average success rate: {summary['average_success_rate']:.1f}%")


class TaskAnalyzer:
    """Analyzes task success rates and goal states from summary files."""

    def __init__(self, checker: "TaskSuccessChecker") -> None:
        """Initializes the TaskAnalyzer."""
        # Use the same conditions as the checker for consistency
        self.task_conditions = checker.task_conditions
        self.checker = checker

    def load_summary_data(self, summary_path: Path) -> Dict[str, Any]:
        """Loads summary data from a JSON file."""
        try:
            with summary_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load summary data from {summary_path}: {e}")
            return {}

    def analyze_difficulty_approach_performance(
        self, summary_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Analyzes performance by difficulty-approach combination."""
        combination_stats: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for result in summary_data.get("results", []):
            instruction = result.get("instruction", "")
            scene_name = result.get("scene_name", "")
            approach_name = result.get("approach_name", "unknown")
            overall_sr = result.get("overall_success_rate", 0.0)

            if not instruction or not scene_name:
                continue

            difficulty = get_instruction_difficulty(
                instruction, scene_name, self.checker
            )

            if difficulty not in combination_stats:
                combination_stats[difficulty] = {}
            if approach_name not in combination_stats[difficulty]:
                combination_stats[difficulty][approach_name] = {
                    "total_instructions": 0,
                    "successful_instructions": 0,
                }

            stats = combination_stats[difficulty][approach_name]
            stats["total_instructions"] += 1
            if overall_sr == 100.0:
                stats["successful_instructions"] += 1

        for approaches in combination_stats.values():
            for stats in approaches.values():
                total = stats["total_instructions"]
                if total > 0:
                    stats["perfect_success_rate"] = (
                        stats["successful_instructions"] / total
                    ) * 100
                else:
                    stats["perfect_success_rate"] = 0.0

        return combination_stats

    def print_difficulty_approach_analysis(
        self, combination_stats: Dict[str, Dict[str, Dict[str, Any]]], title: str
    ) -> None:
        """Prints the difficulty-approach analysis to the console."""
        print(f"\n=== {title}: 난이도-Approach 조합별 GCR 분석 ===")
        print(f"{'난이도':<25} {'Approach':<15} {'총 시도':<15} {'GCR (%)':<12}")
        print("-" * 80)

        # Dynamically find and sort difficulties
        # Sort by n, then by m
        def sort_key(difficulty_str: str) -> tuple[int, int]:
            match = re.match(r"tasks_(\d+)_constraints_(\d+)", difficulty_str)
            if match:
                n, m = map(int, match.groups())
                return n, m
            return (99, 99)  # put unknown/malformed last

        sorted_difficulties = sorted(combination_stats.keys(), key=sort_key)

        for difficulty in sorted_difficulties:
            approaches = combination_stats[difficulty]
            sorted_approaches = sorted(
                approaches.items(),
                key=lambda x: x[1]["perfect_success_rate"],
                reverse=True,
            )

            for approach, stats in sorted_approaches:
                print(
                    f"{difficulty:<25} {approach:<15} {stats['total_instructions']:<15} "
                    f"{stats['perfect_success_rate']:<11.2f}%"
                )

        print("-" * 80)

    def save_difficulty_approach_to_json(
        self, combination_stats: Dict[str, Dict[str, Dict[str, Any]]], output_path: Path
    ) -> dict[str, Any]:
        """Saves the difficulty-approach analysis to a JSON file and returns the sorted data."""

        def sort_key(difficulty_str: str) -> tuple[int, int]:
            match = re.match(r"tasks_(\d+)_constraints_(\d+)", difficulty_str)
            if match:
                n, m = map(int, match.groups())
                return n, m
            return (99, 99)

        sorted_difficulties = sorted(combination_stats.keys(), key=sort_key)

        # Reconstruct the dictionary in sorted order for consistent output
        sorted_stats = {}
        for difficulty in sorted_difficulties:
            approaches = combination_stats[difficulty]
            sorted_approaches = sorted(
                approaches.items(),
                key=lambda x: x[1]["perfect_success_rate"],
                reverse=True,
            )
            sorted_stats[difficulty] = dict(sorted_approaches)

        try:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(sorted_stats, f, indent=2, ensure_ascii=False)
            logger.info(f"GCR analysis JSON saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save GCR analysis to {output_path}: {e}")
        return sorted_stats


def main() -> None:
    """Main function to run the entire GCR analysis pipeline."""
    base_dir = Path(__file__).parent
    tasks_json_path = base_dir.parent.parent.parent / "tasks" / "floorplan_tasks.json"
    target_dirs = ["states60_merged", "states100_merged", "states140_merged"]

    checker = TaskSuccessChecker(tasks_json_path=tasks_json_path)
    analyzer = TaskAnalyzer(checker=checker)

    all_gcr_results = {}

    for dir_name in target_dirs:
        states_folder = base_dir / dir_name
        if not states_folder.is_dir():
            logger.warning(f"Directory {states_folder} not found. Skipping.")
            continue

        # 1. Run checker to generate summary
        checker.process_all_instructions(states_folder)

        # 2. Run analyzer on the generated summary
        summary_path = states_folder / "task_success_summary.json"
        summary_data = analyzer.load_summary_data(summary_path)
        if not summary_data:
            logger.error(f"Failed to load summary for {dir_name}. Skipping analysis.")
            continue

        combination_stats = analyzer.analyze_difficulty_approach_performance(
            summary_data
        )

        # 3. Print and save results
        analyzer.print_difficulty_approach_analysis(combination_stats, title=dir_name)

        # 4. Save analysis results to JSON
        json_path = states_folder / f"gcr_analysis_results_{dir_name}.json"
        sorted_results = analyzer.save_difficulty_approach_to_json(
            combination_stats, json_path
        )
        all_gcr_results[dir_name.replace("_merged", "")] = sorted_results

    # 5. Save the combined dictionary to a final summary file
    final_summary_path = base_dir / "gcr_analysis_summary_all.json"
    try:
        with final_summary_path.open("w", encoding="utf-8") as f:
            json.dump(all_gcr_results, f, indent=2, ensure_ascii=False)
        logger.info(f"Combined GCR analysis summary saved to: {final_summary_path}")
    except Exception as e:
        logger.error(
            f"Failed to save combined GCR summary to {final_summary_path}: {e}"
        )


if __name__ == "__main__":
    main()
