import json
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
                "executionStatus": None,
                **({"updatedExpectedTime": st.updatedExpectedTime} if hasattr(st, "updatedExpectedTime") else {})
            } for st in result_schedule
        ]
    }]
    return plans


def result_save(task_name, approach_name, result_schedule, computation_time):
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
        "computationTime": computation_time
    }
    
    # 결과 데이터를 approach_name.json 파일로 저장 (JSON 형식)
    approach_folder_path = save_folder_path / "approach"
    approach_folder_path.mkdir(exist_ok=True, parents=True)
    result_file = approach_folder_path / f"{approach_name}.json"
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)
    
    # 추후 필요시 summary_comparison.json, tasks.json, constraints.jpg, metadata.json 등을 생성하는 코드 추가 가능
