import json
import os


def make_summary():

    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # results/ 하위의 모든 디렉터리를 순회
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        metadata_dir = os.path.join(folder_path, "metadata")
        summary_path = os.path.join(metadata_dir, "summary.json")  
        if os.path.exists(summary_path):
            # 이미 summary.json이 존재하면 건너뜀
            continue
        approach_dir = os.path.join(folder_path, "approach")
        if not os.path.exists(approach_dir):
            print(f"'{approach_dir}' 폴더가 존재하지 않습니다.")
            continue

        simulation_files = [f for f in os.listdir(approach_dir) if f.endswith("_simulation.json")]

        #추후에 5개 실험이 한군데 모이면 3을 5로 바꾸어야함. 지금은 3개짜리만 한다.
        if len(simulation_files) < 3:
            summary_filename = "summary_insuff.json"
        else:
            summary_filename = "summary.json"
        approach_comparisons = []
        for file_name in simulation_files:
            sim_file_path = os.path.join(approach_dir, file_name)

            try:
                with open(sim_file_path, "r") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"파일 읽기 에러 {sim_file_path}: {e}")
                continue

            # 각 시뮬레이션 파일의 데이터 추출
            scheduler_makespan =data.get("scheduler_makespan")
            simulation_makespan = data.get("simulation_makespan")
            computation_time = data.get("computation_time")
            success_rate = data.get("success_rate")
            
            approach_comparisons.append({
                "approach_name": file_name,
                "scheduler_makespan": scheduler_makespan,
                "simulation_makespan": simulation_makespan,
                "realWorld_makespan": None,
                "computation_mime": computation_time,
                "actionSuccess_mate": success_rate,
                "timingSuccess_mate": None
            })
        
        # 최종 JSON 데이터 구성
        json_data = {
            "task": folder,
            "approachComparisons": approach_comparisons
        }

        # metadata 폴더가 없으면 생성 후 summary 파일 작성
        if not os.path.exists(metadata_dir):
            os.makedirs(metadata_dir)
        summary_file_path = os.path.join(metadata_dir, summary_filename)
        
        with open(summary_file_path, "w") as f:
            json.dump(json_data, f, indent=4)
        
def main():

    make_summary()

if __name__ == "__main__":
    main()