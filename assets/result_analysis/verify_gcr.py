import argparse
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


# --- Logger Setup ---
def create_module_logger(name: str) -> logging.Logger:
    """Creates and configures a logger."""
    logger = logging.getLogger(name)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = create_module_logger(__name__)


class DetailedTaskSuccessChecker:
    """
    Checks the success of tasks based on goal conditions and provides detailed
    feedback on failures.
    """

    def __init__(self, tasks_json_path: Path):
        """
        Initializes the checker by loading task information and conditions.

        Args:
            tasks_json_path: Path to the JSON file defining tasks.
        """
        self.all_task_names, self.critical_tasks_by_floorplan = self._load_task_info(
            tasks_json_path
        )
        self.all_task_names.sort(key=len, reverse=True)
        self.task_conditions = self._define_task_conditions()

    def _load_task_info(
        self, json_path: Path
    ) -> tuple[list[str], dict[str, list[str]]]:
        if not json_path.exists():
            log.error(f"Tasks JSON file not found at: {json_path}")
            return [], {}
        with json_path.open("r") as f:
            data = json.load(f)
        task_names = {
            t
            for v in data.values()
            if isinstance(v, dict)
            for tasks in v.values()
            if isinstance(tasks, list)
            for t in tasks
        }
        critical_tasks = {
            fp: data.get("common", {}).get("critical", []) + v.get("critical", [])
            for fp, v in data.items()
            if fp.startswith("FloorPlan")
        }
        return list(task_names), critical_tasks

    def parse_instruction_to_tasks(self, instruction: str) -> List[str]:
        """
        Parses a string-based instruction into a list of known task names.

        Args:
            instruction: The instruction string (e.g., from a directory name).

        Returns:
            A list of parsed task names.
        """
        remaining = instruction
        parsed = []
        while remaining:
            found = False
            for task in self.all_task_names:
                task_id = task.replace(" ", "_").replace(" and ", "_and_")
                if remaining.startswith(task_id):
                    parsed.append(task)
                    remaining = remaining[len(task_id) :].lstrip("_and_")
                    found = True
                    break
            if not found:
                if remaining:
                    log.warning(f"Unparsable instruction part: '{remaining}'")
                break
        return parsed

    def check_task_success_detailed(
        self, end_state: List[Dict], task_name: str
    ) -> Tuple[bool, List[str]]:
        """
        Checks if a task succeeded and returns detailed reasons for failure.

        Args:
            end_state: The final state of objects from the simulation.
            task_name: The name of the task to check.

        Returns:
            A tuple containing:
            - bool: True if the task was successful, False otherwise.
            - list[str]: A list of reasons for failure. Empty if successful.
        """
        conditions = self.task_conditions.get(task_name)
        if conditions is None:
            return False, [f"Task '{task_name}' has no conditions defined."]
        if not conditions:
            return True, []

        failures = []
        all_conditions_met = True
        for cond in conditions:
            objs = [
                o
                for o in end_state
                if o.get("name", "").startswith(cond["object_type"])
            ]
            success, reason = self._check_condition_detailed(
                objs,
                cond["property"],
                cond["expected_value"],
                cond["object_type"],
            )
            if not success:
                all_conditions_met = False
                failures.append(reason)

        return all_conditions_met, failures

    def _check_condition_detailed(
        self, objs: List[Dict], prop: str, val: Any, obj_type: str
    ) -> Tuple[bool, str]:
        """
        Checks a single condition against a list of objects and provides a
        detailed failure reason.

        Args:
            objs: A list of candidate objects from the end state.
            prop: The property to check (e.g., "isCooked").
            val: The expected value of the property.
            obj_type: The type of object being checked (for logging).

        Returns:
            A tuple containing:
            - bool: True if the condition is met, False otherwise.
            - str: A detailed reason for failure. Empty if successful.
        """
        if not objs:
            return False, f"Object type '{obj_type}' not found in end state."

        for obj in objs:
            actual_val = obj.get(prop)
            if prop == "parentReceptacles":
                receptacles = actual_val or []
                expected = [val] if not isinstance(val, list) else val
                if any(any(e in str(r) for e in expected) for r in receptacles):
                    return True, ""
            elif actual_val == val:
                return True, ""

        actual_values = [obj.get(prop, "N/A") for obj in objs]
        return (
            False,
            f"Condition failed for '{obj_type}': "
            f"Property '{prop}' was expected to be '{val}', "
            f"but found value(s): {actual_values}.",
        )

    def _define_task_conditions(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Defines the success conditions for each known task.

        This is a direct copy from `unified_analysis.py` to ensure consistency.

        Returns:
            A dictionary mapping task names to their success conditions.
        """
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
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "boil_water_with_pot": [
                {
                    "object_type": "Pot",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "cook_egg": [
                {
                    "object_type": "Egg_Cracked",
                    "property": "isCooked",
                    "expected_value": True,
                }
            ],
            "fill_pot_with_water": [
                {
                    "object_type": "Pot",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "fill_bowl_with_water": [
                {
                    "object_type": "Bowl",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "heat_the_potato_using_microwave": [
                {
                    "object_type": "Potato",
                    "property": "isCooked",
                    "expected_value": True,
                }
            ],
            "make_a_coffee": [
                {
                    "object_type": "Mug",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "prepare_a_water_cup_with_mug": [
                {
                    "object_type": "Mug",
                    "property": "isFilledWithLiquid",
                    "expected_value": True,
                }
            ],
            "put_a_statue_on_the_table": [
                {
                    "object_type": "Statue",
                    "property": "parentReceptacles",
                    "expected_value": "DiningTable",
                }
            ],
            "put_saltshaker_on_the_table": [
                {
                    "object_type": "SaltShaker",
                    "property": "parentReceptacles",
                    "expected_value": "DiningTable",
                }
            ],
            "put_the_creditcard_on_the_countertop": [
                {
                    "object_type": "CreditCard",
                    "property": "parentReceptacles",
                    "expected_value": "CounterTop",
                }
            ],
            "put_the_pencil_on_countertop": [
                {
                    "object_type": "Pencil",
                    "property": "parentReceptacles",
                    "expected_value": "CounterTop",
                }
            ],
            "throw_away_paper_towel_roll": [
                {
                    "object_type": "PaperTowelRoll",
                    "property": "parentReceptacles",
                    "expected_value": "GarbageCan",
                }
            ],
            "put_the_book_in_cabinet": [
                {
                    "object_type": "Book",
                    "property": "parentReceptacles",
                    "expected_value": "Cabinet",
                }
            ],
            "put_the_wine_bottle_inside_a_cabinet": [
                {
                    "object_type": "WineBottle",
                    "property": "parentReceptacles",
                    "expected_value": "Cabinet",
                }
            ],
            "put_salt_shaker_inside_the_safe": [
                {
                    "object_type": "SaltShaker",
                    "property": "parentReceptacles",
                    "expected_value": "Safe",
                }
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
                    "property": "parentReceptacles",
                    "expected_value": "CounterTop",
                }
            ],
            "open_the_blinds": [
                {"object_type": "Blinds", "property": "isOpen", "expected_value": True}
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
            "wash_all_fork_and_spoon": [],
            "wash_apple_and_lettuce": [],
            "wash_two_ladles": [],
            "wash_a_tomato": [],
            "wash_a_butterknife": [],
            "wash_a_spatula": [],
            "wash_plate_and_cup": [],
        }


def analyze_failures(
    root_dir: Path, checker: "DetailedTaskSuccessChecker"
) -> Dict[str, Any]:
    """
    Analyzes all end_state.json files in a directory to find failure patterns.

    Args:
        root_dir: The root directory containing the experimental results.
        checker: An instance of DetailedTaskSuccessChecker.

    Returns:
        A dictionary containing aggregated failure statistics.
    """
    failure_stats = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: {"count": 0, "scenes": set()}))
    )

    log.info(f"Scanning for 'end_state.json' files under '{root_dir}'...")
    end_state_files = list(root_dir.rglob("states*/**/end_state.json"))

    if not end_state_files:
        log.warning(
            f"No 'end_state.json' files found in subdirectories of 'states*' under {root_dir}."
        )
        return {}

    log.info(f"Found {len(end_state_files)} files to analyze.")

    for state_file in end_state_files:
        try:
            # Path is expected to be like: .../states.../{difficulty}/{instruction_dir}/{scene}/{approach}/end_state.json
            parts = state_file.resolve().parts
            approach = parts[-2]
            scene = parts[-3]
            instruction_dir = parts[-4]

            instruction = re.sub(r"^\d{2}_", "", instruction_dir)

            with state_file.open("r") as f:
                end_state = json.load(f)

            parsed_tasks = checker.parse_instruction_to_tasks(instruction)
            if not parsed_tasks:
                continue

            for task in parsed_tasks:
                is_success, failures = checker.check_task_success_detailed(
                    end_state, task
                )
                if not is_success:
                    for reason in failures:
                        stats_entry = failure_stats[task][reason][approach]
                        stats_entry["count"] += 1
                        stats_entry["scenes"].add(scene)
        except (IndexError, json.JSONDecodeError) as e:
            log.error(f"Could not process file {state_file}: {e}")
            continue

    return failure_stats


def print_failure_report(failure_stats: Dict[str, Any]) -> None:
    """Prints a formatted report of all GCR failures, grouped by task."""
    log.info("--- GCR Failure Analysis Report (Task-Centric) ---")
    if not failure_stats:
        log.info("No failures found.")
        return

    APPROACH_ORDER: list[str] = [
        "dag_bayesian_DEFAULT",
        "dag_bayesian_GREEDY",
        "dag_bayesian_NONE_MONITORING",
        "dag_bayesian_NONE_URGENCY",
        "dag_bayesian_NONE_REMAINING_WORK",
        "dag_edf",
        "cpm",
    ]

    # Sort tasks alphabetically
    for task, reasons in sorted(failure_stats.items()):
        print("\n" + "=" * 80)
        print(f" Task: {task}")
        print("=" * 80)

        # Sort reasons by the total number of failures across all approaches
        def reason_sort_key(reason_item: Tuple[str, Dict[str, Any]]) -> int:
            _reason, approaches_data = reason_item
            return -sum(stats["count"] for stats in approaches_data.values())

        sorted_reasons = sorted(reasons.items(), key=reason_sort_key)

        for reason, approaches in sorted_reasons:
            total_count = sum(stats["count"] for stats in approaches.values())
            print(f"\n  - Failure Reason: {reason} (Total Occurrences: {total_count})")

            # Sort approaches by the predefined order
            sorted_approaches = sorted(
                approaches.items(),
                key=lambda item: (
                    (
                        APPROACH_ORDER.index(item[0])
                        if item[0] in APPROACH_ORDER
                        else len(APPROACH_ORDER)
                    ),
                    item[0],
                ),
            )

            for approach, stats in sorted_approaches:
                print(f"    - Approach: {approach}")
                print(f"      - Count: {stats['count']}")
                sorted_scenes = sorted(list(stats["scenes"]))
                print(f"      - Scenes: {', '.join(sorted_scenes)}")


def main() -> None:
    """Main function to run the GCR failure analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze GCR failures across an entire experiment directory."
    )
    parser.add_argument(
        "--root_dir",
        type=Path,
        required=True,
        help="Root directory of the experiment results (e.g., './assets/results/1104').",
    )
    parser.add_argument(
        "--tasks_json",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tasks/floorplan_tasks.json",
        help="Path to floorplan_tasks.json.",
    )
    args = parser.parse_args()

    if not args.root_dir.is_dir():
        log.error(f"Root directory not found: {args.root_dir}")
        return

    checker = DetailedTaskSuccessChecker(args.tasks_json)
    failure_data = analyze_failures(args.root_dir, checker)
    print_failure_report(failure_data)


if __name__ == "__main__":
    main()
