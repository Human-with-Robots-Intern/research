### utils/io_utils/result_saver.py
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from networkx import DiGraph

if TYPE_CHECKING:
    from src.models.dataclass import CompletedEntry

from src.utils.common.logger import create_module_logger
from src.utils.config.constants import EPSILON, RESULT_PATH, TIMING_TOLERANCE
from src.utils.visualizers.visualizer import visualize

log = create_module_logger(__name__, module_log=True, level=logging.INFO)


def get_now_str(fmt: str = "%Y-%m-%d %H:%M") -> str:
    return datetime.now().strftime(fmt)


def compose_subtasks(
    result_schedule: List[CompletedEntry],
) -> Tuple[List[dict], int, int]:
    success_count = 0
    total_count = 0

    for ce in result_schedule:
        execution_status = getattr(ce, "execution_status", None)
        if execution_status is not None:
            total_count += 1
            if execution_status:
                success_count += 1

    return success_count, total_count


def compose_plans(
    result_schedule: List[CompletedEntry], task_name: str
) -> Tuple[float, float, float]:
    success_count, total_count = compose_subtasks(result_schedule)

    simulation_makespan = result_schedule[-1].sim_end_time if result_schedule else None
    scheduler_makespan = (
        result_schedule[-1].schedule_end_time if result_schedule else None
    )
    success_rate = round(success_count / total_count, 3) if total_count > 0 else 0.0

    return success_rate, simulation_makespan, scheduler_makespan


def calculate_timing_success_rate(
    constraints: DiGraph, result_schedule: List[CompletedEntry]
) -> Tuple[float | None, float | None, Dict[str, Any]]:
    """
    Calculates the success rate of timing constraints based on simulation and schedule results.

    Args:
        constraints: A DiGraph representing the constraints between subtasks.
        result_schedule: A list of CompletedEntry objects containing execution results.

    Returns:
        A tuple containing:
        - The timing success rate for the simulation (float | None).
        - The timing success rate for the schedule (float | None).
        - A dictionary with detailed logging information.
    """
    total_timing_constraints = 0
    succeeded_timing_constraints_sim_cnt = 0
    succeeded_timing_constraints_sched_cnt = 0
    detail_log = {}

    # Create a mapping from task names to completed entries for efficient lookup
    entry_map = {ce.subtask.name: ce for ce in result_schedule}

    for u, v, data in constraints.edges(data=True):
        timing_success_flag = False

        if u.lower().startswith("monitoring") or v.lower().startswith("monitoring"):
            log.debug(f"Skipping monitoring task edge: {u} -> {v}")
            continue

        

        pred_entry = entry_map.get(u)
        succ_entry = entry_map.get(v)

        if not pred_entry or not succ_entry:
            log.warning(f"Predecessor or successor task not found in results: {u} -> {v}")
            continue
        
        total_timing_constraints += 1
        # log.info(f"total_timing_constraints increased: {total_timing_constraints}")
        edge_info = data.get("info", {})
        interval = edge_info.get("Interval", 0)
        is_critical = edge_info.get("IsCritical", False)

        # --- Check timing constraints for simulation results ---
        pred_end_time_sim = pred_entry.sim_end_time
        succ_start_time_sim = succ_entry.sim_start_time
        sim_nav_time = succ_entry.sim_nav_time if succ_entry.sim_nav_time is not None else 0.0
        tolerance = 0.1 + interval * TIMING_TOLERANCE
        
        actual_diff_sim = (succ_start_time_sim + sim_nav_time) - pred_end_time_sim

        sim_constraint_met = False
        if is_critical:
            if interval == 0:
                succeeded_timing_constraints_sim_cnt += 1  # Intended logic
                sim_constraint_met = True
            else:
                if abs(interval - actual_diff_sim) <= tolerance:
                    succeeded_timing_constraints_sim_cnt += 1
                    sim_constraint_met = True
        else:  # Non-critical
            if (interval - actual_diff_sim) <= tolerance:
                succeeded_timing_constraints_sim_cnt += 1
                sim_constraint_met = True
        
        timing_success_flag = sim_constraint_met

        # --- Check timing constraints for schedule results ---
        pred_end_time_sched = pred_entry.schedule_end_time
        succ_start_time_sched = succ_entry.schedule_start_time
        schedule_nav_time = succ_entry.schedule_nav_time if succ_entry.schedule_nav_time is not None else 0.0
        
        actual_diff_sched = (succ_start_time_sched + schedule_nav_time) - pred_end_time_sched

        if is_critical:
            if interval == 0:
                succeeded_timing_constraints_sched_cnt += 1
            else:
                if abs(interval - actual_diff_sched) <= tolerance:
                    succeeded_timing_constraints_sched_cnt += 1
        else:  # Non-critical
            if (interval - actual_diff_sched) <= tolerance:
                succeeded_timing_constraints_sched_cnt += 1

        # --- Logging ---
        log.info(f"Original Timing Constraint : {u} -> {v} ({interval}, {is_critical})")
        log.info(
            f"Schedule Result [{timing_success_flag}] - {pred_entry.subtask.name} ({pred_end_time_sched+schedule_nav_time}) -> {succ_entry.subtask.name} ({succ_start_time_sched})s\n\n"
        )
        detail_log[f"{u} -> {v}"] = {
            "Original Timing Constraint": f"({interval}, {is_critical})",
            "Schedule Result": f"[{timing_success_flag}] : ({pred_end_time_sched}) -> ({succ_start_time_sched}s-{-schedule_nav_time}s)"
        }

    timing_success_rate_sim = (
        succeeded_timing_constraints_sim_cnt / total_timing_constraints
        if total_timing_constraints != 0
        else None
    )
    timing_success_rate_sched = (
        succeeded_timing_constraints_sched_cnt / total_timing_constraints
        if total_timing_constraints != 0
        else None
    )
    return timing_success_rate_sim, timing_success_rate_sched, detail_log


def serialize_completed_entries(result_schedule: List[CompletedEntry]) -> List[dict]:
    """
    Convert CompletedEntry objects to JSON-serializable format
    """
    serialized_entries = []
    for entry in result_schedule:
        serialized_entry = {
            "subtask_name": entry.subtask.name,
            "start_time_simulation": round(entry.sim_start_time, 2),
            "end_time_simulation": round(entry.sim_end_time, 2),
            "start_time_scheduled": round(entry.schedule_start_time, 2),
            "end_time_scheduled": round(entry.schedule_end_time, 2),
            "execution_status": entry.execution_status,
        }
        if hasattr(entry, "primitive_action_log"):
            serialized_entry["primitive_action_log"] = [
                {
                    "action": log["action"],
                    "duration": round(log["duration"], 2)
                } for log in entry.primitive_action_log
            ]
        serialized_entries.append(serialized_entry)
    return serialized_entries


def result_save(
    task_name: str,
    approach_name: str,
    result_schedule: List[Any],
    computation_time: float,
    scene_name: str,
    constraints: DiGraph,
    initial_plan_data: List[Dict],
    log_level: str = "INFO",
):
    global log

    success_rate, simulation_makespan, scheduler_makespan = compose_plans(
        result_schedule, task_name
    )

    timing_success_rate_sim, timing_success_rate_sched, detail_log = (
        calculate_timing_success_rate(constraints, result_schedule)
    )

    # Serialize the result schedule
    serialized_plans = serialize_completed_entries(result_schedule)

    total_primitive_actions = sum(
        len(entry.subtask.execution.primitive_actions)
        for entry in result_schedule
        if (
            hasattr(entry, "subtask")
            and hasattr(entry.subtask, "execution")
            and entry.subtask.execution is not None
            and hasattr(entry.subtask.execution, "primitive_actions")
            and entry.subtask.execution.primitive_actions is not None
        )
    )
    
    realworld_makespan = None
    if "ros" in approach_name:
        realworld_makespan = round(simulation_makespan, 2)

    result_data = {
        "saved_time": get_now_str(),
        "approach": approach_name,
        "scene_name": scene_name,
        "plans": serialized_plans,
        "computation_time": round(computation_time, 5),
        "simulation_makespan": round(simulation_makespan, 2),
        "scheduler_makespan": round(scheduler_makespan, 2),
        "total_primitive_actions": total_primitive_actions,
        "realworld_makespan": realworld_makespan,
        "success_rate": round(success_rate, 2),
        "timing_success_rate_sim": None if timing_success_rate_sim is None else round(timing_success_rate_sim, 2),
        "timing_success_rate_sched": None if timing_success_rate_sched is None else round(timing_success_rate_sched, 2),
        "detail_log": detail_log,
    }

    # Find the next available number for the task name
    num = 1
    while True:
        output_path = RESULT_PATH / f"{task_name}_{num}" / scene_name
        approach_path = output_path / "approach"
        file_path = approach_path / f"{approach_name}.json"
        if not file_path.exists():
            break
        num += 1
    # Create directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    approach_path.mkdir(parents=True, exist_ok=True)

    visualize(
        approach_name,
        output_path,
        constraints,
        result_schedule,
        initial_plan_data,
        scene_name,
    )
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)

    print(f"JSON file saved at {file_path}")


def parse_llm_log(lines: List[str]) -> Tuple[List[dict], float, int, int]:
    actions = []
    current_action = None
    start_time, end_time = None, None
    execution_status = None
    last_end_time = 0
    total_count = 0
    success_count = 0

    for line in lines:
        line = line.strip()

        if line.startswith("Executing action:"):
            if current_action:
                current_action.update(
                    {
                        "start_time": start_time,
                        "end_time": end_time,
                        "execution_status": execution_status,
                    }
                )
                actions.append(current_action)

            action = re.findall(r"\['(.*?)'\]", line)
            if action:
                action = action[0].split("', '")
                current_action = {"Executing_action": action}
                start_time, end_time, execution_status = None, None, None
            else:
                current_action = None

        elif line.startswith("start_time:"):
            start_time = float(line.split(":")[1].strip())

        elif line.startswith("end_time:"):
            end_time = float(line.split(":")[1].strip())
            last_end_time = max(last_end_time, end_time)

        elif line.startswith("execution_status:"):
            status = line.split(":")[1].strip()
            if status == "True":
                execution_status = True
                success_count += 1
            elif status == "False":
                execution_status = False
            total_count += 1

    if current_action:
        current_action.update(
            {
                "start_time": start_time,
                "end_time": end_time,
                "execution_status": execution_status,
            }
        )
        actions.append(current_action)

    return actions, last_end_time, success_count, total_count


def result_save_llm(
    approach_name: str,
    user_input: str,
    result_txt: str,
    json_output_path: str,
    computation_time: float,
    scene_name: str,
):
    with open(result_txt, "r", encoding="utf-8") as f:
        lines = f.readlines()
    actions, last_end_time, success_count, total_count = parse_llm_log(lines)

    result_data = {
        "saved_time": get_now_str(),
        "approach": approach_name,
        "scene_name": scene_name,
        "plans": [{"plan_name": user_input, "actions": actions}],
        "computation_time": computation_time,
        "success_rate": (
            round(success_count / total_count, 3) if total_count > 0 else None
        ),
        "timing_success_rate": None,
        "scheduler_makespan": None,
        "simulation_makespan": last_end_time,
        "realworld_makespan": None,
    }

    # Find the next available number for the task name
    num = 1
    while True:
        output_path = RESULT_PATH / f"{user_input}_{num}" / scene_name
        approach_path = output_path / "approach"
        file_path = approach_path / f"{approach_name}.json"
        if not file_path.exists():
            break
        num += 1
    # Create directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    approach_path.mkdir(parents=True, exist_ok=True)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)
    print(f"JSON file saved at {file_path}")
    print(f"result_path:{file_path}")
