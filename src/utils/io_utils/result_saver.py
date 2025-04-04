### utils/io_utils/result_saver.py
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple
from networkx import DiGraph

from core.dataclass import CompletedEntry
from utils.config.constants import RESULT_PATH


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
    succeeded_timing_constraints = 0

    ##TODO##
    # 1. 모든edge를 확인해서 edge 별 선행, 후행, interval, critical 여부를 확인
    # 2. total_timing_constraints = edge의 수
    # 3. plans 에서 edge의 선행 subtask_name과 일치하는 subtask의 endtime + edge_interval 을 확인.
    #   3-a. critical 인 경우 선행 subtask의 endtime + edge_interval +- 가우시간의 90% = 후행 subtask의 start time 이면 succeeded_timing_constraints =+ 1
    #   3-b. non-critical 인 경우 선행 subtask의 endtime + edge_interval <= 후행 subtask의 start time 이면 succeeded_timing_constraints =+ 1
    #   단, interval 이 없으면 interval = 0으로 처리
    ### 

    timing_success_rate = succeeded_timing_constraints / total_timing_constraints if total_timing_constraints != 0 else None
    return timing_success_rate


def result_save(
    task_name: str,
    approach_name: str,
    result_schedule: List[Any],
    computation_time: float,
    scene_name: str,
    constraints: DiGraph,
):
    plans, success_rate, simulation_time, scheduler_makespan = compose_plans(
        result_schedule, task_name
    )

    timing_success_rate = calculate_timing_success_rate(constraints, plans)

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
        "timing_success_rate": timing_success_rate,
    }

    output_path = RESULT_PATH / task_name / "approach"
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"{approach_name}.json"
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
