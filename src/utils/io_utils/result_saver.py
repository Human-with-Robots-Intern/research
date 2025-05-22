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

from utils.common.logger import create_module_logger
from utils.config.constants import RESULT_PATH
from utils.visualizers.visualizer import visualize

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
) -> float:
    """
    constraints 의 모든 edge를 확인해서 plans의 결과를 토대로 timing constraint 준수율을 계산한다.
    """
    total_timing_constraints = 0
    succeeded_timing_constraints_sim_cnt = 0
    succeeded_timing_constraints_sched_cnt = 0
    detail_log = {}

    # 모든 edge를 순회하며 timing constraint 검사
    for u, v, data in constraints.edges(data=True):
        timing_success_flag = False
        total_timing_constraints += 1
        edge_info = data.get("info", {})

        interval = edge_info.get("Interval", 0)  # interval이 없으면 0으로 처리
        is_critical = edge_info.get("IsCritical")
        # plans에서 선행/후행 subtask 찾기
        pred_entry = next((ce for ce in result_schedule if ce.subtask.name == u), None)
        succ_entry = next((ce for ce in result_schedule if ce.subtask.name == v), None)
        if not pred_entry or not succ_entry:
            log.warning(f"pred_subtask or succ_subtask not found: {u} -> {v}")
            continue
        # 선행 subtask의 종료 시간과 후행 subtask의 시작 시간
        pred_end_time_sim = pred_entry.sim_end_time
        succ_start_time_sim = succ_entry.sim_start_time
        succ_start_time_sched = succ_entry.schedule_start_time
        pred_end_time_sched = pred_entry.schedule_end_time
        schedule_nav_time = (
            succ_entry.schedule_nav_time
        )  # navigation time이 없으면 0으로 처리
        sim_nav_time = succ_entry.sim_nav_time
        if is_critical:
            # Critical edge: 가우시안 90% 범위 내에서 시작해야 함
            # 일단 간단히 ±10% 범위를 사용
            expected_start_sim = pred_end_time_sim + interval - sim_nav_time
            expected_start_sched = pred_end_time_sched + interval - schedule_nav_time
            tolerance = (
                0.2 + interval * 0.1
            )  # 10% 허용 오차 #추후에 interval의 std를 확인해서 허용오차를 조정해야함.
            if abs(succ_start_time_sim - expected_start_sim) <= tolerance:
                timing_success_flag = True
                succeeded_timing_constraints_sim_cnt += 1
            if abs(succ_start_time_sched - expected_start_sched) <= tolerance:
                succeeded_timing_constraints_sched_cnt += 1
        else:
            # Non-critical edge: interval 이후에 시작하면 됨
            if succ_start_time_sim >= pred_end_time_sim + interval:
                timing_success_flag = True
                succeeded_timing_constraints_sim_cnt += 1
            if succ_start_time_sched >= pred_end_time_sched + interval:
                succeeded_timing_constraints_sched_cnt += 1
        # 제약 시작 작업 끝 작업, 원본 제약 기준 (interval, is_critical)
        # 실제 스케쥴 결과 : pred_end_time_sched -> succ_start_time_sched,
        log.info(f"Original Timing Constraint : {u} -> {v} ({interval}, {is_critical})")
        log.info(
            f"Schedule Result [{timing_success_flag}] - {pred_entry.subtask.name} ({pred_end_time_sched}) -> {succ_entry.subtask.name} ({succ_start_time_sched})s\n\n"
        )
        detail_log[f"{u} -> {v}"] = {}
        detail_log[f"{u} -> {v}"][
            "Original Timing Constraint"
        ] = f"({interval}, {is_critical})"
        detail_log[f"{u} -> {v}"][
            "Schedule Result"
        ] = f"[{timing_success_flag}] : ({pred_end_time_sched}) -> ({succ_start_time_sched})s"

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

    result_data = {
        "saved_time": get_now_str(),
        "approach": approach_name,
        "scene_name": scene_name,
        "plans": serialized_plans,
        "computation_time": round(computation_time, 5),
        "simulation_makespan": round(simulation_makespan, 2),
        "scheduler_makespan": round(scheduler_makespan, 2),
        "realworld_makespan": None,
        "success_rate": round(success_rate, 2),
        "timing_success_rate_sim": round(timing_success_rate_sim, 2),
        "timing_success_rate_sched": round(timing_success_rate_sched, 2),
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
