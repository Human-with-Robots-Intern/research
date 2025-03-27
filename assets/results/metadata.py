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
    return {
        "approach_name": file_name,
        "scheduler_makespan": data.get("scheduler_makespan"),
        "simulation_makespan": data.get("simulation_makespan"),
        "realWorld_makespan": None,
        "computation_time": data.get("computation_time"),
        "actionSuccess_rate": data.get("success_rate"),
        "timingSuccess_rate": None,

    }

def make_summary(base_dir):
    

    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        metadata_dir = os.path.join(folder_path, "metadata")
        summary_path = os.path.join(metadata_dir, "summary.json")
        # if os.path.exists(summary_path):
        #     continue  # 이미 summary.json이 존재하면 건너뜀

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

        summary_data = {
            "task": folder,
            "approach_comparisons": approach_comparisons
        }

        os.makedirs(metadata_dir, exist_ok=True)
        summary_file_path = os.path.join(metadata_dir, summary_filename)
        with open(summary_file_path, "w") as f:
            json.dump(summary_data, f, indent=4)

def make_metadata(base_dir):
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        metadata_dir = os.path.join(folder_path, "metadata")
        metadata_file_path = os.path.join(metadata_dir, "metadata.json")
        approach_dir = os.path.join(folder_path, "approach")
        source_file_name = "dag_bayesian_simulation.json"
        
        sim_file_path = os.path.join(approach_dir, source_file_name)

        data = load_simulation_data(sim_file_path)
        metadata_data = {
            "metadata": {
                "task": folder,
                "creation_date": data.get("saved_time"),
                "instructions":data["plans"][0].get("plan_name"),
                "model_version":"gpt-4o"
            },
            "environment_info":{
                "simulator": "AI2-THOR",
                "simulation_version":"2.7.1",
                "scene":data.get("scene_name"),
                # HW spec
                "gpu":None,
                "cpu":None,
            }

        }
        
        summary_file_path = os.path.join(metadata_dir, "metadata.json")
        with open(summary_file_path, "w") as f:
            json.dump(metadata_data, f, indent=4)

            
    pass

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    make_summary(base_dir)
    make_metadata(base_dir)

if __name__ == "__main__":
    main()
