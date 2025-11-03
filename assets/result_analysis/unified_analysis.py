import argparse
import json
import logging
import math
import re
import shutil
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


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


# --- Phase 1: Data Preprocessing (Merging States) ---
def merge_states_for_analysis(states_dir: Path) -> Optional[Path]:
    """
    Merges init_state.json and end_state.json files into a single state.json
    for easier analysis.
    """
    merged_dir = states_dir.parent / f"{states_dir.name}_merged"
    log.info(f"Preprocessing data from '{states_dir.name}' into '{merged_dir.name}'...")

    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    merged_dir.mkdir(parents=True)

    copied_count = 0
    for difficulty_dir in states_dir.iterdir():
        if not difficulty_dir.is_dir():
            continue
        for task_dir in difficulty_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for scene_dir in task_dir.iterdir():
                if not scene_dir.is_dir():
                    continue
                for approach_dir in scene_dir.iterdir():
                    if not approach_dir.is_dir():
                        continue

                    init_file = approach_dir / "init_state.json"
                    end_file = approach_dir / "end_state.json"

                    if init_file.exists() and end_file.exists():
                        try:
                            with init_file.open("r") as f:
                                init_data = json.load(f)
                            with end_file.open("r") as f:
                                end_data = json.load(f)

                            merged_data = {
                                "initial_state": init_data,
                                "end_state": end_data,
                            }

                            target_dir = (
                                merged_dir
                                / difficulty_dir.name
                                / task_dir.name
                                / scene_dir.name
                                / approach_dir.name
                            )
                            target_dir.mkdir(parents=True, exist_ok=True)
                            with (target_dir / "state.json").open("w") as f:
                                json.dump(merged_data, f, indent=2)
                            copied_count += 1
                        except Exception as e:
                            log.error(f"Error merging files in {approach_dir}: {e}")

    if copied_count == 0:
        log.error(
            f"No state files were merged for {states_dir.name}. Check directory structure."
        )
        return None

    log.info(
        f"Preprocessing for {states_dir.name} complete. Merged {copied_count} state files."
    )
    return merged_dir


# --- GCR Checker class ---
class TaskSuccessChecker:
    """Checks the success of tasks based on goal conditions."""

    def __init__(self, tasks_json_path: Path):
        self.all_task_names, self.critical_tasks_by_floorplan = self._load_task_info(
            tasks_json_path
        )
        self.all_task_names.sort(key=len, reverse=True)
        self.task_conditions = self._define_task_conditions()

    def _load_task_info(
        self, json_path: Path
    ) -> tuple[list[str], dict[str, list[str]]]:
        if not json_path.exists():
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

    def check_task_success(self, end_state: List[Dict], task_name: str) -> bool:
        conditions = self.task_conditions.get(task_name)
        if conditions is None:
            return False
        if not conditions:
            return True
        for cond in conditions:
            objs = [
                o
                for o in end_state
                if o.get("name", "").startswith(cond["object_type"])
            ]
            if not self._check_condition(
                objs, cond["property"], cond["expected_value"]
            ):
                return False
        return True

    def _check_condition(self, objs: List[Dict], prop: str, val: Any) -> bool:
        if not objs:
            return False
        for obj in objs:
            actual_val = obj.get(prop)
            if prop == "parentReceptacles":
                receptacles = actual_val or []
                expected = [val] if not isinstance(val, list) else val
                if any(any(e in str(r) for e in expected) for r in receptacles):
                    return True
            elif actual_val == val:
                return True
        return False

    def _define_task_conditions(self) -> Dict[str, List[Dict[str, Any]]]:
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
                {"object_type": "Bread", "property": "isCooked", "expected_value": True}
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


# --- Unified Data Collection and Final Calculation ---
def calculate_final_summary(all_trials_data: Dict[tuple, list]) -> Dict[str, Any]:
    """
    Calculates final summary statistics from raw per-trial data, including the
    newly defined strict Success Rate (SR).
    """
    final_summary = defaultdict(lambda: defaultdict(dict))

    for (init_key, diff, approach), trials in all_trials_data.items():
        if not trials:
            continue

        total_trials = len(trials)
        strict_successes = sum(
            1
            for t in trials
            if t.get("tsr", 0.0) >= 0.5 and t.get("gcr_perfect", 0) == 1
        )
        sr = (strict_successes / total_trials) * 100 if total_trials > 0 else 0
        gcr_successes = sum(t.get("gcr_perfect", 0) for t in trials)
        gcr = (gcr_successes / total_trials) * 100 if total_trials > 0 else 0
        tsr_values = [t.get("tsr", 0.0) for t in trials]
        tsr = statistics.mean(tsr_values) * 100 if tsr_values else 0
        makespan_values = [
            t.get("makespan", 0.0) for t in trials if t.get("makespan") is not None
        ]
        makespan = statistics.mean(makespan_values) if makespan_values else 0.0

        final_summary[init_key][diff][approach] = {
            "SR": sr,
            "GCR": gcr,
            "TSR": tsr,
            "Makespan": makespan,
        }
    return final_summary


def print_summary_table(final_data: Dict[str, Any]) -> None:
    """Prints the final merged data in a formatted table."""
    log.info("--- Final Unified Analysis Results ---")
    columns = ["SR", "GCR", "TSR", "Makespan"]
    for init_key, diffs in sorted(final_data.items()):
        print("\n" + "=" * 80)
        print(f" 대분류: {init_key}")
        print("=" * 80)
        print(
            f"{'난이도 (tasks_n_constraints_m)':<30} {'Approach':<20} "
            + "".join([f"{col:<12}" for col in columns])
        )
        print("-" * 80)
        for diff, approaches in sorted(diffs.items()):
            for approach, metrics in sorted(approaches.items()):
                row_data = [
                    (
                        f"{metrics.get(col, 'N/A'):.2f}"
                        if isinstance(metrics.get(col), (int, float))
                        else "N/A"
                    )
                    for col in columns
                ]
                print(
                    f"{diff:<30} {approach:<20} "
                    + "".join([f"{val:<12}" for val in row_data])
                )
        print("-" * 80)


# --- Main Execution ---
def main() -> None:
    """Main function to run the full unified analysis pipeline."""
    parser = argparse.ArgumentParser(
        description="Unified analysis of GCR and performance metrics."
    )
    parser.add_argument(
        "root_dir",
        type=Path,
        help="Root directory containing init_* and states* folders.",
    )
    parser.add_argument(
        "--tasks_json",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tasks/floorplan_tasks.json",
        help="Path to floorplan_tasks.json.",
    )
    args = parser.parse_args()

    if not args.root_dir.is_dir() or not args.tasks_json.exists():
        log.error(f"Root directory or tasks JSON not found.")
        return

    # Phase 1: Preprocessing
    log.info("--- Phase 1: Preprocessing state files ---")
    merged_dirs = {}
    states_dirs = sorted(
        [
            d
            for d in args.root_dir.iterdir()
            if d.is_dir()
            and d.name.startswith("states")
            and not d.name.endswith("_merged")
        ]
    )
    for states_dir in states_dirs:
        merged_dir = merge_states_for_analysis(states_dir)
        if merged_dir:
            merged_dirs[states_dir.name] = merged_dir

    # Phase 2: Pre-calculate GCR
    log.info("--- Phase 2: Pre-calculating GCR data ---")
    gcr_lookup = defaultdict(dict)
    checker = TaskSuccessChecker(args.tasks_json)
    for states_key, merged_dir in merged_dirs.items():
        for difficulty_dir in merged_dir.iterdir():
            if not difficulty_dir.is_dir():
                continue
            for task_dir in difficulty_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                instruction = re.sub(r"^\d{2}_", "", task_dir.name)
                parsed_tasks = checker.parse_instruction_to_tasks(instruction)
                if not parsed_tasks:
                    continue
                for scene_dir in task_dir.iterdir():
                    if not scene_dir.is_dir():
                        continue
                    for approach_dir in scene_dir.iterdir():
                        state_file = approach_dir / "state.json"
                        if not state_file.exists():
                            continue
                        with state_file.open("r") as f:
                            state_data = json.load(f)
                        end_state = state_data.get("end_state", [])
                        n = len(parsed_tasks)
                        successful_tasks = sum(
                            1
                            for t in parsed_tasks
                            if checker.check_task_success(end_state, t)
                        )
                        gcr_perfect = 1 if successful_tasks == n else 0
                        lookup_key = (
                            difficulty_dir.name,
                            task_dir.name,
                            scene_dir.name,
                            approach_dir.name,
                        )
                        gcr_lookup[states_key][lookup_key] = gcr_perfect

    # Phase 3: Unified Data Collection
    log.info("--- Phase 3: Collecting and aligning per-trial data ---")
    all_trials_data = defaultdict(list)
    init_dirs = sorted(
        [
            d
            for d in args.root_dir.iterdir()
            if d.is_dir() and d.name.startswith("init_")
        ]
    )
    for init_dir in init_dirs:
        init_key = init_dir.name
        states_key = init_key.replace("init_", "states")
        for difficulty_dir in init_dir.iterdir():
            if not difficulty_dir.is_dir() or not difficulty_dir.name.startswith(
                "tasks_"
            ):
                continue
            difficulty_key = difficulty_dir.name
            for task_dir in difficulty_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                for scene_dir in task_dir.iterdir():
                    if not scene_dir.is_dir():
                        continue
                    approach_data_dir = scene_dir / "approach"
                    if not approach_data_dir.is_dir():
                        continue
                    for json_file in approach_data_dir.glob("*.json"):
                        approach_name = json_file.stem.replace("_simulation", "")
                        perf_data = json.load(json_file.open("r"))
                        tsr_value = perf_data.get("timing_success_rate_sim")
                        tsr = 1.0 if tsr_value is None else float(tsr_value or 0.0)
                        makespan = float(
                            perf_data.get("simulation_makespan", 0.0) or 0.0
                        )
                        task_name_in_states = re.sub(r"_\d+$", "", task_dir.name)
                        lookup_key = (
                            difficulty_key,
                            task_name_in_states,
                            scene_dir.name,
                            approach_name,
                        )
                        gcr_perfect = gcr_lookup.get(states_key, {}).get(lookup_key, 0)
                        trial_data = {
                            "tsr": tsr,
                            "gcr_perfect": gcr_perfect,
                            "makespan": makespan,
                        }
                        all_trials_data[
                            (init_key, difficulty_key, approach_name)
                        ].append(trial_data)

    # Phase 4: Final Calculation
    log.info("--- Phase 4: Calculating final summary ---")
    final_summary = calculate_final_summary(all_trials_data)

    # Phase 5: Save and Print
    summary_file = args.root_dir / "unified_analysis_summary.json"
    with summary_file.open("w") as f:
        json.dump(final_summary, f, indent=2, sort_keys=True)
    log.info(f"Final summary saved to: {summary_file}")
    print_summary_table(final_summary)

    # Phase 6: Cleanup
    log.info("--- Phase 6: Cleaning up intermediate files ---")
    for merged_dir in merged_dirs.values():
        shutil.rmtree(merged_dir)


if __name__ == "__main__":
    main()
