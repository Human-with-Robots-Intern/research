import json
import re

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
        "computationTime": None,
        "schedulerTotalTime":None,        
        "ai2thorTotalTime": None,
        "realWorldTotalTime": None
    }

    actions = []
    current_action = None
    start_time, end_time = None, None
    execution_status = None
    computation_time = None

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

        # 실행 상태 감지
        elif line.startswith("executionStatus:"):
            execution_status = line.split(":")[1].strip()

        # 총 실행 시간 감지
        elif line.startswith("Total time spent"):
            ai2thor_time = float(line.split(":")[1].strip())

    # 마지막 액션 저장 (루프가 종료된 후 마지막 액션을 추가해야 함)
    if current_action:
        current_action["startTime"] = start_time
        current_action["endTime"] = end_time
        current_action["executionStatus"] = execution_status
        actions.append(current_action)

    json_data["plans"][0]["actions"] = actions
    json_data["computationTime"] = computation_time

    # JSON 파일로 저장
    with open(json_output_path, "w") as f:
        json.dump(json_data, f, indent=4)

    print(f"JSON file saved at {json_output_path}")
