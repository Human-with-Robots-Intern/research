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

# --- Orders ---
# Fixed order for approaches and inits as requested
APPROACH_ORDER: list[str] = [
    "dag_bayesian_DEFAULT",
    "dag_bayesian_GREEDY",
    "dag_bayesian_NONE_MONITORING",
    "dag_bayesian_NONE_URGENCY",
    "dag_bayesian_NONE_REMAINING_WORK",
    "dag_edf",
    "cpm",
]
INIT_ORDER: list[str] = ["init_60", "init_100", "init_140"]

APPROACH_LABELS: dict[str, str] = {
    "dag_bayesian_DEFAULT": "Ours (Default)",
    "dag_bayesian_GREEDY": "Ours (Greedy)",
    "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
    "dag_bayesian_NONE_URGENCY": "Ours (w/o Urg.)",
    "dag_bayesian_NONE_REMAINING_WORK": "Ours (w/o Rem.)",
    "dag_edf": "EDF",
    "cpm": "CPM",
}


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
def _task_case_sort_key(task_case: str) -> tuple[int, int, str]:
    """
    Returns a sort key for task_case strings like 'tasks_2_constraints_1'.
    Primary key: number after 'tasks_'. Secondary key: number after 'constraints_'.
    Falls back to large numbers and the original string if parsing fails.
    """
    match = re.search(r"tasks_(\d+)_constraints_(\d+)", task_case)
    if match:
        tasks_num = int(match.group(1))
        constraints_num = int(match.group(2))
        return tasks_num, constraints_num, task_case
    return 10**9, 10**9, task_case


def _reorder_task_cases(final_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reorders task_case entries under each (init, approach) by the numeric
    values parsed from the 'tasks_X_constraints_Y' pattern.
    """
    ordered: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for init_key, approaches in final_data.items():
        ordered[init_key] = {}
        for approach, task_cases in approaches.items():
            sorted_task_keys = sorted(task_cases.keys(), key=_task_case_sort_key)
            ordered[init_key][approach] = {k: task_cases[k] for k in sorted_task_keys}
    return ordered


def _transform_summary_to_approach_view(init_first: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms summary structure from:
      init -> approach -> task_case -> {gcr, tsr, sr, makespan}
    to:
      approach -> task_case -> {
          init -> {gcr, tsr, sr, makespan}
      }

    Task case order follows numeric sort by tasks then constraints.
    Approach and init follow the specified fixed orders.
    """
    approach_view: Dict[str, Any] = {}

    # Collect available approaches from data, preserve requested order
    available_approaches = {
        approach
        for init_key, approaches in init_first.items()
        for approach in approaches.keys()
    }
    ordered_approaches = [a for a in APPROACH_ORDER if a in available_approaches]

    # Build approach-first view
    for approach in ordered_approaches:
        # Union of all task_cases under this approach across inits
        task_case_keys = set()
        for init_key in INIT_ORDER:
            approach_map = init_first.get(init_key, {}).get(approach, {})
            task_case_keys.update(approach_map.keys())
        sorted_task_cases = sorted(task_case_keys, key=_task_case_sort_key)

        approach_view[approach] = {}
        for task_case in sorted_task_cases:
            # Collect per-init metrics; makespan is NOT shared, keep per init
            per_init_metrics: Dict[str, Dict[str, float]] = {}
            for init_key in INIT_ORDER:
                approach_map = init_first.get(init_key, {}).get(approach, {})
                metrics = approach_map.get(task_case)
                if metrics is None:
                    continue
                per_init_metrics[init_key] = {
                    "gcr": float(metrics.get("gcr", 0.0)),
                    "tsr": float(metrics.get("tsr", 0.0)),
                    "sr": float(metrics.get("sr", 0.0)),
                    "makespan": float(metrics.get("makespan", 0.0)),
                }

            # Insert with init order preserved
            ordered_per_init = {
                init_key: per_init_metrics[init_key]
                for init_key in INIT_ORDER
                if init_key in per_init_metrics
            }
            approach_view[approach][task_case] = {"init": ordered_per_init}

    return approach_view


def _format_task_case_label(task_case: str) -> str:
    """
    Converts a task_case string like 'tasks_2_constraints_1' to 'T2 C1'.
    Falls back to the original string if the expected pattern is not found.
    """
    match = re.search(r"tasks_(\d+)_constraints_(\d+)", task_case)
    if match:
        return f"T{match.group(1)} C{match.group(2)}"
    return task_case


def _fmt_num(value: Any) -> str:
    """
    Formats numeric values to two decimals; returns '---' if not a number.
    """
    return f"{float(value):.2f}" if isinstance(value, (int, float)) else "---"


def _fmt_ms(value: Any) -> str:
    """
    Formats makespan in math mode with two decimals; returns '---' if not a number.
    """
    return f"${float(value):.2f}$" if isinstance(value, (int, float)) else "---"


def generate_overleaf_table(final_data: Dict[str, Any], output_path: Path) -> None:
    """
    Generates an Overleaf-friendly LaTeX table snippet as a text file.
    Structure per row:
      [multirow(approach label)] & [T{X} C{Y}] &
      [init_60 GCR] & [init_60 TSR] & [init_60 SR] & [init_60 MS] &
      [init_100 GCR] & [init_100 TSR] & [init_100 SR] & [init_100 MS] &
      [init_140 GCR] & [init_140 TSR] & [init_140 SR] & [init_140 MS] \\\\
    A \\midrule line separates approaches.
    """
    lines: list[str] = []
    for approach in APPROACH_ORDER:
        if approach not in final_data:
            continue
        task_cases = final_data[approach]
        sorted_task_cases = sorted(task_cases.keys(), key=_task_case_sort_key)
        if not sorted_task_cases:
            continue
        label = APPROACH_LABELS.get(approach, approach)
        row_span = len(sorted_task_cases)
        first_row = True
        for task_case in sorted_task_cases:
            entry = task_cases[task_case]
            init_metrics: Dict[str, Dict[str, float]] = entry.get("init", {})
            parts: list[str] = []
            if first_row:
                parts.append(f"\\multirow[t]{{{row_span}}}{{*}}{{\\textbf{{{label}}}}}")
                first_row = False
            else:
                parts.append("")  # empty cell for subsequent rows
            parts.append(_format_task_case_label(task_case))
            # Append per-init blocks
            for init_key in INIT_ORDER:
                m = init_metrics.get(init_key)
                if m:
                    parts.extend(
                        [
                            _fmt_num(m.get("gcr")),
                            _fmt_num(m.get("tsr")),
                            _fmt_num(m.get("sr")),
                            _fmt_ms(m.get("makespan")),
                        ]
                    )
                else:
                    parts.extend(["---", "---", "---", "---"])
            line = " & ".join(parts) + " \\\\"
            lines.append(line)
        lines.append("\\midrule")
    output_path.write_text("\n".join(lines))


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

        # Re-structure: init -> approach -> task_case(diff)
        # Keep insertion order of metrics as: gcr, tsr, sr, makespan
        final_summary[init_key][approach][diff] = {
            "gcr": gcr,
            "tsr": tsr,
            "sr": sr,
            "makespan": makespan,
        }
    return final_summary


def print_summary_table(final_data: Dict[str, Any]) -> None:
    """Prints the final merged data (approach-first view) in a formatted table."""
    log.info("--- Final Unified Analysis Results (Approach-first) ---")
    # For approach-first view, build dynamic columns:
    # [task_case] + for each init in INIT_ORDER: (GCR, TSR, SR, MS)
    for approach in APPROACH_ORDER:
        if approach not in final_data:
            continue
        task_cases = final_data[approach]
        print("\n" + "=" * 80)
        print(f" 접근법: {approach}")
        print("=" * 80)
        header_cols = ["난이도 (tasks_n_constraints_m)"]
        for init_key in INIT_ORDER:
            header_cols.extend(
                [
                    f"{init_key}-GCR",
                    f"{init_key}-TSR",
                    f"{init_key}-SR",
                    f"{init_key}-MS",
                ]
            )
        print(" ".join([f"{h:<18}" for h in header_cols]))
        print("-" * 80)
        for diff in sorted(task_cases.keys(), key=_task_case_sort_key):
            entry = task_cases[diff]
            init_metrics: Dict[str, Dict[str, float]] = entry.get("init", {})
            row_parts = [f"{diff:<30}"]
            for init_key in INIT_ORDER:
                m = init_metrics.get(init_key)
                if m:
                    row_parts.append(f"{m.get('gcr', 0.0):<10.2f}")
                    row_parts.append(f"{m.get('tsr', 0.0):<10.2f}")
                    row_parts.append(f"{m.get('sr', 0.0):<10.2f}")
                else:
                    row_parts.extend([f"{'N/A':<10}", f"{'N/A':<10}", f"{'N/A':<10}"])
                # makespan per init (if exists)
                ms_val = m.get("makespan", 0.0) if m else "N/A"
                if isinstance(ms_val, (int, float)):
                    row_parts.append(f"{ms_val:<10.2f}")
                else:
                    row_parts.append(f"{'N/A':<10}")
            print(" ".join(row_parts))
        print("-" * 80)


# --- Main Execution ---
def main() -> None:
    """Main function to run the full unified analysis pipeline."""
    parser = argparse.ArgumentParser(
        description="Unified analysis of GCR and performance metrics."
    )
    parser.add_argument(
        "--root_dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results" / "1104",
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
    init_first_summary = calculate_final_summary(all_trials_data)
    # Reorder task cases as requested: by tasks number, then constraints number (within init-first)
    init_first_summary = _reorder_task_cases(init_first_summary)
    # Convert to approach-first view with required ordering and aggregation
    final_summary = _transform_summary_to_approach_view(init_first_summary)

    # Phase 5: Save and Print
    summary_file = args.root_dir / "unified_analysis_summary.json"
    with summary_file.open("w") as f:
        # Do not sort keys to preserve insertion order of metrics and nesting
        json.dump(final_summary, f, indent=2)
    log.info(f"Final summary saved to: {summary_file}")
    print_summary_table(final_summary)
    # Generate Overleaf-friendly table
    overleaf_file = args.root_dir / "unified_analysis_overleaf.txt"
    generate_overleaf_table(final_summary, overleaf_file)
    log.info(f"Overleaf table saved to: {overleaf_file}")

    # Phase 6: Cleanup
    log.info("--- Phase 6: Cleaning up intermediate files ---")
    for merged_dir in merged_dirs.values():
        shutil.rmtree(merged_dir)


if __name__ == "__main__":
    main()
