### utils/io_utils/result_saver.py
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple
from networkx import DiGraph

from core.dataclass import CompletedEntry
from utils.common.logger import create_module_logger
from utils.config.constants import RESULT_PATH
from utils.visualizers.visualizer import visualize

def get_now_str(fmt: str = "%Y-%m-%d %H:%M") -> str:
    return datetime.now().strftime(fmt)


def compose_subtasks(
    result_schedule: List[CompletedEntry],
) -> Tuple[List[dict], int, int]:
    subtasks = []
    success_count = 0
    total_count = 0

    for ce in result_schedule:
        execution_status = getattr(ce.subtask, "execution_status", None)
        if execution_status is not None:
            total_count += 1
            if execution_status:
                success_count += 1

        subtask = {
            "subtask_name": ce.subtask.name,
            "start_time_simulation": round(
                getattr(ce.subtask, "start_time_simulation", None), 3
            ),
            "end_time_simulation": round(
                getattr(ce.subtask, "end_time_simulation", None), 3
            ),
            "start_time_scheduled": round(
                getattr(ce.subtask, "start_time_scheduled", None), 3
            ),
            "end_time_scheduled": round(
                getattr(ce.subtask, "end_time_scheduled", None), 3
            ),
            "execution_status": execution_status,
        }
        if hasattr(ce.subtask, "monitored_subtask"):
            subtask["monitored_subtask"] = ce.subtask.monitored_subtask
        subtasks.append(subtask)

    return subtasks, success_count, total_count


def compose_plans(
    result_schedule: List[CompletedEntry], task_name: str
) -> Tuple[List[dict], float, float, float]:
    subtasks, success_count, total_count = compose_subtasks(result_schedule)

    simulation_time = subtasks[-1]["end_time_simulation"] if subtasks else None
    scheduler_makespan = subtasks[-1]["end_time_scheduled"] if subtasks else None
    success_rate = round(success_count / total_count, 3) if total_count > 0 else 0.0

    plans = [{"plan_name": task_name, "subtasks": subtasks}]
    return plans, success_rate, simulation_time, scheduler_makespan

def calculate_timing_success_rate(constraints: DiGraph, plans: List[dict])-> float :
    '''
    constraints 의 모든 edge를 확인해서 plans의 결과를 토대로 timing constraint 준수율을 계산한다.
    '''
    total_timing_constraints = 0
    succeeded_timing_constraints_sim = 0
    succeeded_timing_constraints_sched = 0

    # 모든 edge를 순회하며 timing constraint 검사
    for u, v, data in constraints.edges(data=True):
        total_timing_constraints += 1
        edge_info = data.get("info", {})
        interval = edge_info.get("Interval", 0)  # interval이 없으면 0으로 처리
        is_critical = edge_info.get("IsCritical")

        # plans에서 선행/후행 subtask 찾기
        subtasks = plans[0]["subtasks"]  # 첫 번째 plan의 subtasks 사용
        pred_subtask = next((s for s in subtasks if s["subtask_name"] == u), None)
        succ_subtask = next((s for s in subtasks if s["subtask_name"] == v), None)

        if not pred_subtask or not succ_subtask:
            log.warning(f"pred_subtask or succ_subtask not found: {u} -> {v}")
            continue

        # 선행 subtask의 종료 시간과 후행 subtask의 시작 시간
        pred_end_time_sim = pred_subtask["end_time_simulation"]
        succ_start_time_sim = succ_subtask["start_time_simulation"]
        succ_start_time_sched = succ_subtask["start_time_scheduled"]
        pred_end_time_sched = pred_subtask["end_time_scheduled"]

        if is_critical:
            # Critical edge: 가우시안 90% 범위 내에서 시작해야 함
            # 일단 간단히 ±10% 범위를 사용
            expected_start_sim = pred_end_time_sim + interval
            expected_start_sched = pred_end_time_sched + interval
            tolerance = interval * 0.1  # 10% 허용 오차 #추후에 interval의 std를 확인해서 허용오차를 조정해야함.
            if abs(succ_start_time_sim - expected_start_sim) <= tolerance:
                succeeded_timing_constraints_sim += 1
            if abs(succ_start_time_sched - expected_start_sched) <= tolerance:
                succeeded_timing_constraints_sched += 1
        else:
            # Non-critical edge: interval 이후에 시작하면 됨
            if succ_start_time_sim >= pred_end_time_sim + interval:
                succeeded_timing_constraints_sim += 1
            if succ_start_time_sched >= pred_end_time_sched + interval:
                succeeded_timing_constraints_sched += 1

    timing_success_rate_sim = succeeded_timing_constraints_sim / total_timing_constraints if total_timing_constraints != 0 else None
    timing_success_rate_sched = succeeded_timing_constraints_sched / total_timing_constraints if total_timing_constraints != 0 else None
    return timing_success_rate_sim, timing_success_rate_sched


def result_save(
    task_name: str,
    approach_name: str,
    result_schedule: List[Any],
    computation_time: float,
    scene_name: str,
    constraints: DiGraph,
    log_level: str = "INFO",
):
    global log  
    log = create_module_logger(__name__,module_log=True, level=log_level)
    plans, success_rate, simulation_time, scheduler_makespan = compose_plans(
        result_schedule, task_name
    )

    timing_success_rate_sim, timing_success_rate_sched = calculate_timing_success_rate(constraints, plans)

    result_data = {
        "saved_time": get_now_str(),
        "approach": approach_name,
        "scene_name": scene_name,
        "plans": plans,
        "computation_time": round(computation_time, 5),
        "simulation_makespan": simulation_time,
        "scheduler_makespan": scheduler_makespan,
        "realworld_makespan": None,
        "success_rate": success_rate,
        "timing_success_rate_sim": timing_success_rate_sim,
        "timing_success_rate_sched": timing_success_rate_sched,
    }
    
    # Find the next available number for the task name
    num = 1
    while True:
        output_path = RESULT_PATH / f"{task_name}_{num}" / scene_name 
        file_path = output_path /"approach"/ f"{approach_name}.json"
        if not file_path.exists():
            break
        num += 1
    # Create directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    visualize(approach_name, output_path, constraints, plans)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)


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

    file_path = (
        Path("assets")
        / "results"
        / json_output_path
        / "approach"
        / f"{approach_name}.json"
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)

    print(f"JSON file saved at {file_path}")
