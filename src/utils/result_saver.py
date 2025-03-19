import json
import os
import re
from pathlib import Path
from .constants import RESULT_PATH


def compose_plans(result_schedule, approach_name):
    """
    result_schedule(서브태스크 객체 리스트)을 받아 plans 데이터를 구성합니다.
    
    각 서브태스크 객체는 Subtask 클래스의 인스턴스로, 생성자에서
    self.name으로 이름이 할당되어 있으므로, st.name을 통해 subtaskName을 받아옵니다.
    
    현재 Subtask 클래스에는 startTime, endTime 속성이 없으므로 None으로 저장합니다.
    또한, updatedExpectedTime 속성이 있다면 포함하도록 처리합니다.
    """
    plans = [{
        "planName": approach_name,
        "subtasks": [
            {
                "subtaskName": st.name,
                "startTime": round(st.start_time, 2) if st.start_time else None,
                "endTime": round(st.end_time, 2) if st.end_time else None,
                "executionStatus": getattr(st, "is_subtask_success", None),    # Subtask 객체에 is_subtask_success 속성이 있는 경우에만 저장
                **({"updatedExpectedTime": st.updatedExpectedTime} if hasattr(st, "updatedExpectedTime") else {})
            } for st in result_schedule
        ]
    }]

    return plans


def result_save(task_name, approach_name, result_schedule, computation_time, simulationTime= None):
    """
    결과 데이터를 지정된 폴더 구조에 JSON 파일(result_save.pt)로 저장합니다.
    
    Parameters:
        task_name (str): 태스크 이름
        approach_name (str): 적용한 접근 방식 (예, "dag_bayesian")
        result_schedule (list): Subtask 객체들이 담긴 결과 일정 리스트
        computation_time (float): 전체 계산 소요 시간
    """

    plans = compose_plans(result_schedule,approach_name)
 
    save_folder_path = Path(RESULT_PATH) / task_name
    save_folder_path.mkdir(exist_ok=True, parents=True)
    
    # 저장할 결과 데이터 구성
    result_data = {
        "approach": approach_name,
        "plans": plans,
        "computationTime": computation_time,
        "simulationMakespan": simulationTime,
    }
    
    # 결과 데이터를 approach_name.json 파일로 저장 (JSON 형식)
    approach_folder_path = save_folder_path / "approach"
    approach_folder_path.mkdir(exist_ok=True, parents=True)
    result_file = approach_folder_path / f"{approach_name}.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)
    
    # 추후 필요시 summary_comparison.json, tasks.json, constraints.jpg, metadata.json 등을 생성하는 코드 추가 가능

def result_save_llm(approach, result_txt, json_output_path, computation_time):
    with open(result_txt, "r") as f:
        lines = f.readlines()

    json_data = {
        "approach": f"{approach}",
        "plans": [
            {
                "planName": f"{approach}",
                "actions": [],
                "executionStatus": None
            }
        ],
        "computationTime": computation_time,
        "schedulerTotalTime":None,
        "simulationMakespan": None,
        "realWorldTotalTime": None
    }

    actions = []
    current_action = None
    start_time, end_time = None, None
    execution_status = None
    last_end_time = 0

    for line in lines:
        line = line.strip()

        # 액션 감지
        if line.startswith("Executing action:"):
            # 이전 액션 저장 (start_time, end_time, executionStatus 포함)
            if current_action:
                current_action["startTime"] = start_time
                current_action["endTime"] = end_time
                current_action["executionStatus"] = execution_status                
                actions.append(current_action)

            # 새로운 액션 감지
            action = re.findall(r"\['(.*?)'\]", line)
            if action:
                action = action[0].split("', '")  # 문자열을 리스트로 변환
                current_action = {"Executing action": action, "startTime": None, "endTime": None, "executionStatus": None}
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
        elif line.startswith("executionStatus:"):
            execution_status = line.split(":")[1].strip()

        # 총 실행 시간 감지
        elif line.startswith("Total time spent"):
            simulationMakespan = float(line.split(":")[1].strip())

    # 마지막 액션 저장 (루프가 종료된 후 마지막 액션을 추가해야 함)
    if current_action:
        current_action["startTime"] = start_time
        current_action["endTime"] = end_time
        current_action["executionStatus"] = execution_status
        actions.append(current_action)

    json_data["plans"][0]["actions"] = actions
    json_data["plans"][0].pop("executionStatus", None) #마지막 executionStatus는 날리기 위함
    json_data["simulationMakespan"] = last_end_time

    # JSON 파일로 저장
    filename=f"{approach}.json"
    new_json_output_path = os.path.join( "assets", "results", json_output_path, filename)
    os.makedirs(os.path.dirname(new_json_output_path), exist_ok=True)
    with open(new_json_output_path, "w") as f:
        json.dump(json_data, f, indent=4)
        

    print(f"JSON file saved at {new_json_output_path}")
