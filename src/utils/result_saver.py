import json
import os
import re
from datetime import datetime
from pathlib import Path

from .constants import RESULT_PATH
from datetime import datetime


def compose_plans(result_schedule, task_name, simulationTime=None):
    """
    result_schedule(서브태스크 객체 리스트)을 받아 plans 데이터를 구성합니다.

    각 서브태스크 객체는 Subtask 클래스의 인스턴스로, 생성자에서
    self.name으로 이름이 할당되어 있으므로, st.name을 통해 subtaskName을 받아옵니다.

    현재 Subtask 클래스에는 startTime, endTime 속성이 없으므로 None으로 저장합니다.
    또한, monitored_subtask 속성이 있다면 포함하도록 처리합니다.
    """
    success_count = 0
    total_count = 0
    subtasks = []
    for st in result_schedule:  
        execution_status = getattr(st, "execution_status", None) # Subtask 객체에 is_subtask_success 속성이 있는 경우에만 저장
        if execution_status is not None:
            total_count += 1
            if execution_status:
                success_count += 1  
        subtask = {
            "subtask_name": st.name,
            "start_time_simulation": round(st.start_time_simulation, 2) if hasattr(st, "start_time_simulation") else None,
            "end_time_simulation": round(st.end_time_simulation, 2) if hasattr(st, "end_time_simulation") else None,
            "start_time_scheduled": round(st.start_time_scheduled, 2) if hasattr(st, "start_time_scheduled") else None,
            "end_time_scheduled": round(st.end_time_scheduled, 2) if hasattr(st, "end_time_scheduled")else None,
            "execution_status": execution_status,
            **({"monitored_subtask": st.monitored_subtask} if hasattr(st, "monitored_subtask") else {})
        }
        subtasks.append(subtask)

    if simulationTime==None and st.end_time_simulation != None :
        simulationTime = subtasks[-1]["end_time_simulation"]
    if st.end_time_scheduled != None:
        schedulerMakespan = st.end_time_scheduled


    success_rate=round(success_count/total_count, 2) if total_count != 0 else None
    plans = [{
        "plan_name": task_name,
        "subtasks": subtasks,
        
    }]
    return plans, success_rate, simulationTime, schedulerMakespan


def result_save(task_name, approach_name, result_schedule, computation_time, scene_name,simulationTime= None):
    """    
    Parameters:
        task_name (str): 태스크 이름
        approach_name (str): 적용한 접근 방식 (예, "dag_bayesian")
        result_schedule (list): Subtask 객체들이 담긴 결과 일정 리스트
        computation_time (float): 전체 계산 소요 시간
        simulation_time (float): 시뮬레이션종료까지 걸린 시간 ("마지막 end_time_scheduled") 로 대체 될 수도 있는 파라미터
    """

    plans, success_rate, simulationTime, schedulerMakespan = compose_plans(result_schedule, task_name, simulationTime)
 
    save_folder_path = Path(RESULT_PATH) / task_name
    save_folder_path.mkdir(exist_ok=True, parents=True)

    # 저장할 결과 데이터 구성
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    result_data = {
        "saved_time": time_str,
        "approach": approach_name,
        "scene_name":scene_name,
        "plans": plans,
        "computation_time": round(computation_time, 5),
        "simulation_makespan": round(simulationTime, 2) if simulationTime else None,
        "scheduler_makespan": round(schedulerMakespan, 2) if schedulerMakespan else None,
        "realworld_makespan": None,
        "success_rate": round(success_rate, 2) if success_rate else None,
        "timing_success_rate": None ,
    }

    # 결과 데이터를 approach_name.json 파일로 저장 (JSON 형식)
    approach_folder_path = save_folder_path / "approach"
    approach_folder_path.mkdir(exist_ok=True, parents=True)
    result_file = approach_folder_path / f"{approach_name}.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)

    # 추후 필요시 summary_comparison.json, tasks.json, constraints.jpg, metadata.json 등을 생성하는 코드 추가 가능

def result_save_llm(approach_name, user_input, result_txt, json_output_path, computation_time, scene_name):
    
    with open(result_txt, "r") as f:
        lines = f.readlines()
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    json_data = {
        "saved_time": time_str,
        "approach": approach_name,
        "scene_name":scene_name,
        "plans": [
            {
                "plan_name": user_input,
                "actions": [],
                "execution_status": None
            }
        ],
        "computation_time": computation_time,
        "success_rate": None,
        "timing_success_rate": None,
        "scheduler_makespan":None,
        "simulation_makespan": None,
        "realworld_makespan": None
    }

    actions = []
    current_action = None
    start_time, end_time = None, None
    execution_status = None
    last_end_time = 0
    total_count = 0
    success_count = 0
    for line in lines:
        line = line.strip()

        # 액션 감지
        if line.startswith("Executing action:"):
            # 이전 액션 저장 (start_time, end_time, execution_status 포함)
            if current_action:
                current_action["start_time"] = start_time
                current_action["end_time"] = end_time
                current_action["execution_status"] = execution_status                
                actions.append(current_action)

            # 새로운 액션 감지
            action = re.findall(r"\['(.*?)'\]", line)
            if action:
                action = action[0].split("', '")  # 문자열을 리스트로 변환
                current_action = {"Executing_action": action, "start_time": None, "end_time": None, "execution_status": None}
                execution_status = None  # 새 액션이 시작되었으므로 초기화
            else:
                current_action = None

        # 시작 시간 감지
        elif line.startswith("start_time:"):
            start_time = float(line.split(":")[1].strip())

        # 종료 시간 감지
        elif line.startswith("end_time:"):
            end_time = float(line.split(":")[1].strip())
            last_end_time = max(last_end_time, end_time)

        # 실행 상태 감지
        elif line.startswith("execution_status:"):
            execution_status = line.split(":")[1].strip()
            if execution_status == "True":
                execution_status = True
                success_count += 1
            elif execution_status =="False": 
                execution_status = False
            total_count += 1    
             
            

        # 총 실행 시간 감지
        elif line.startswith("Total time spent"):
            simulationMakespan = float(line.split(":")[1].strip())

    # 마지막 액션 저장 (루프가 종료된 후 마지막 액션을 추가해야 함)
    if current_action:
        current_action["start_time"] = start_time
        current_action["end_time"] = end_time
        current_action["execution_status"] = execution_status
        actions.append(current_action)

    json_data["plans"][0]["actions"] = actions
    json_data["plans"][0].pop("execution_status", None) #마지막 execution_status는 날리기 위함
    json_data["simulation_makespan"] = last_end_time
    json_data["success_rate"] = round(success_count/total_count, 2) if total_count != 0 else None

    # JSON 파일로 저장
    filename=f"{approach_name}.json"
    new_json_output_path = os.path.join( "assets", "results",json_output_path, "approach", filename)
    os.makedirs(os.path.dirname(new_json_output_path), exist_ok=True)
    with open(new_json_output_path, "w") as f:
        json.dump(json_data, f, indent=4)
        

    print(f"JSON file saved at {new_json_output_path}")
