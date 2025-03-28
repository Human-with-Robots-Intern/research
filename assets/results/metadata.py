import json
import os

MIN_REQUIRED_SIMULATIONS = 5 

def load_simulation_data(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] 파일 읽기 실패: {file_path} - {e}")
        return None

def build_summary_entry(file_name, data):
    llm_list = [    
        "prog_ai2thor_simulation.json",
        "cap_ai2thor_simulation.json"
    ]
    entry = {
        "approach_name": file_name,
        "scheduler_makespan": data.get("scheduler_makespan"),
        "simulation_makespan": data.get("simulation_makespan"),
        "realWorld_makespan": None,
        "computation_time": data.get("computation_time"),
        "actionSuccess_rate": data.get("success_rate"),
        "timingSuccess_rate": None,
        "attempt": data.get("attempt") if file_name in llm_list else "Not related"
    }
    # llm 방식의 경우, plan 내 "actions" 리스트의 각 액션에서 "Executing_action"의 수를 누적
    if file_name in llm_list:
        executing_action_count = 0
        for plan in data.get("plans", []):
            actions = plan.get("actions", [])
            for action in actions:
                executing_action_count += len(action.get("Executing_action", []))
        entry["executing_action_count"] = executing_action_count
    else:
        # 그 외 방식은 기존대로 각 plan의 subtasks 수를 누적
        total_subtasks = 0
        for plan in data.get("plans", []):
            subtasks = plan.get("subtasks", [])
            total_subtasks += len(subtasks)
        entry["subtask_count"] = total_subtasks

    return entry

def make_summary(base_dir):
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        metadata_dir = os.path.join(folder_path, "metadata")
        approach_dir = os.path.join(folder_path, "approach")
        if not os.path.exists(approach_dir):
            print(f"[Warning] '{approach_dir}' 폴더가 존재하지 않습니다.")
            continue

        simulation_files = [
            f for f in os.listdir(approach_dir)
            if f.endswith("_simulation.json")
        ]

        summary_filename = (
            "summary.json"
            if len(simulation_files) >= MIN_REQUIRED_SIMULATIONS
            else "summary_insuff.json"
        )

        approach_comparisons = []
        for file_name in simulation_files:
            sim_file_path = os.path.join(approach_dir, file_name)
            data = load_simulation_data(sim_file_path)
            if data is None:
                continue
            entry = build_summary_entry(file_name, data)
            approach_comparisons.append(entry)

        # 평균 계산은 average.py에서 처리할 예정이므로 summary에는 각 simulation의 개별 count만 기록
        summary_data = {
            "task": folder,
            "approach_comparisons": approach_comparisons
        }

        os.makedirs(metadata_dir, exist_ok=True)
        summary_file_path = os.path.join(metadata_dir, summary_filename)
        with open(summary_file_path, "w") as f:
            json.dump(summary_data, f, indent=4)
        print(f"Summary 파일이 '{summary_file_path}'에 저장되었습니다.")

def make_metadata(base_dir):
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        metadata_dir = os.path.join(folder_path, "metadata")
        approach_dir = os.path.join(folder_path, "approach")
        source_file_name = "dag_bayesian_simulation.json"
        sim_file_path = os.path.join(approach_dir, source_file_name)
        data = load_simulation_data(sim_file_path)
        if data is None:
            continue
        metadata_data = {
            "metadata": {
                "task": folder,
                "creation_date": data.get("saved_time"),
                "instructions": data["plans"][0].get("plan_name") if data.get("plans") else None,
                "model_version": "gpt-4o"
            },
            "environment_info": {
                "simulator": "AI2-THOR",
                "simulation_version": "2.7.1",
                "scene": data.get("scene_name"),
                "gpu": None,
                "cpu": None,
            }
        }
        metadata_file_path = os.path.join(metadata_dir, "metadata.json")
        with open(metadata_file_path, "w") as f:
            json.dump(metadata_data, f, indent=4)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    make_summary(base_dir)
    make_metadata(base_dir)

if __name__ == "__main__":
    main()
