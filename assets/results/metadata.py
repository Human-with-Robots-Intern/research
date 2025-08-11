import json
from pathlib import Path
import sys

# Add the project root to the Python path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.utils.task.difficulty_analyzer import get_task_difficulty


MIN_REQUIRED_SIMULATIONS = 3

def load_result_data(file_path: Path) -> dict:
    """
    주어진 파일 경로에서 JSON 데이터를 읽어 반환.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] 파일 읽기 실패: {file_path} - {e}")
        return {}


def calculate_action_success_rate(plans: list) -> float | None:
    """
    plans 목록에서 전체 action 대비 성공한 action의 비율을 계산합니다.
    action의 성공 여부는 'success' 키의 값으로 판단하며, True, "SUCCESS", "success"를 성공으로 간주합니다.

    Args:
        plans: 'subtasks'를 포함하고, 각 subtask가 'actions' 리스트를 포함하는 plan의 목록.
               각 action은 'success' 키를 가질 수 있습니다.

    Returns:
        성공률을 float으로 반환합니다. action이 없는 경우 None을 반환합니다.
    """
    total_actions = 0
    successful_actions = 0

    if not plans:
        return None

    for subtask in plans:
        total_actions += 1
        success_status = subtask.get("execution_status")
        if success_status in [True, "SUCCESS", "success"]:
            successful_actions += 1

    if total_actions == 0:
        return None
    
    return successful_actions / total_actions


def build_summary_entry(file_name: str, data: dict) -> dict:
    """
    파일명과 JSON 데이터를 바탕으로 summary 항목을 생성합니다.
    llm 방식 파일인 경우에는 executing_action_count를, 그렇지 않으면 subtask_count를 계산합니다.
    """
    llm_files = {"prog_ai2thor_simulation.json", "cap_ai2thor_simulation.json"}
    plans = data.get("plans", [])
    
    entry = {
        "approach_name": file_name,
        "scheduler_makespan": data.get("scheduler_makespan"),
        "simulation_makespan": data.get("simulation_makespan"),
        "realWorld_makespan": None,
        "computation_time": data.get("computation_time"),
        "actionSuccess_rate": calculate_action_success_rate(plans),
        "scheduler_timingSuccess_rate": data.get("timing_success_rate_sched"),  # 시뮬레이션 기준 timing success rate 사용
        "simulation_timingSuccess_rate": data.get("timing_success_rate_sim"),  # 시뮬레이션 기준 timing success rate 사용
        "attempt": data.get("attempt") if file_name in llm_files else "Not related"
    }
    # 20250331에 필요없다고 판단해서 주석 처리.
    # if file_name in llm_files:
    #     entry["executing_action_count"] =  count_executing_actions(plans)
    # else:
    #     entry["subtask_count"] =count_subtasks(plans)
        
    return entry

def process_summary_for_task(task_dir: Path) -> None:
    """
    각 태스크(폴더) 내 approach 폴더의 시뮬레이션 파일들을 읽어 summary를 작성.
    모든 baseline의 output파일이 존재하면 summary.json, 그렇지 않으면 summary_insuff.json으로 저장.
    """
    # task_dir이 {task_name}_{num} 형식이므로, scene_name 디렉토리를 찾아야 함
    scene_dirs = [d for d in task_dir.iterdir() if d.is_dir()]
    if not scene_dirs:
        print(f"[Warning] No scene directories found in '{task_dir}'")
        return

    # 모든 scene 디렉토리에 대해 처리
    for scene_dir in scene_dirs:
        approach_dir = scene_dir / "approach"
        metadata_dir = scene_dir / "metadata"
        
        if not approach_dir.exists():
            print(f"[Warning] '{approach_dir}' 폴더가 존재하지 않습니다.")
            continue

        simulation_files = list(approach_dir.glob("*_simulation.json"))
        if len(simulation_files) >= MIN_REQUIRED_SIMULATIONS:
            summary_filename = "summary.json"
        else:
            summary_filename = "summary_insuff.json"

        approach_comparisons = []
        for sim_file in simulation_files:
            data = load_result_data(sim_file)
            if not data:
                continue
            entry = build_summary_entry(sim_file.name, data)
            approach_comparisons.append(entry)
        
        summary_data = {
            "task": task_dir.name,
            "difficulty": get_task_difficulty(task_dir.name, scene_dir.name),
            "scene": scene_dir.name,
            "approach_comparisons": approach_comparisons
        }
        
        metadata_dir.mkdir(exist_ok=True)
        summary_file_path = metadata_dir / summary_filename
        with summary_file_path.open("w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=4)
        print(f"Summary 파일이 '{summary_file_path}'에 저장되었습니다.")

def process_metadata_for_task(task_dir: Path) -> None:
    """
    각 태스크(폴더) 내 'dag_bayesian_simulation.json' 파일을 기반으로 metadata 파일을 생성.
    """
    # task_dir이 {task_name}_{num} 형식이므로, scene_name 디렉토리를 찾아야 함
    scene_dirs = [d for d in task_dir.iterdir() if d.is_dir()]
    if not scene_dirs:
        print(f"[Warning] No scene directories found in '{task_dir}'")
        return

    # 모든 scene 디렉토리에 대해 처리
    for scene_dir in scene_dirs:
        approach_dir = scene_dir / "approach"
        metadata_dir = scene_dir / "metadata"
        source_file = approach_dir / "dag_bayesian_simulation.json"

        # 파일 존재하지 않으면 approach_dir 내 아무 파일 하나 선택
        if not source_file.exists():
            candidates = list(approach_dir.glob("*.json"))  
            if not candidates:
                print(f"[Warning] No files in {approach_dir}")
                continue
            source_file = candidates[0]
            print(f"[Info] 'dag_bayesian_simulation.json' not found. Using '{source_file.name}' instead.")

        data = load_result_data(source_file)
        if not data:
            continue
        
        # plans가 비어있지 않은 경우 첫 번째 plan에서 plan_name을 추출.
        instructions = data.get("plans", [{}])[0].get("plan_name") if data.get("plans") else None
        
        metadata_data = {
            "metadata": {
                "task": task_dir.name,
                "scene": scene_dir.name,
                "creation_date": data.get("saved_time"),
                "instructions": instructions,
                "model_version": "gpt-4o"
            },
            "environment_info": {
                "simulator": "AI2-THOR",
                "simulation_version": "4.2.0",
                "scene": data.get("scene_name"),
                "gpu": None,
                "cpu": None,
            }
        }
        
        metadata_dir.mkdir(exist_ok=True)
        metadata_file_path = metadata_dir / "metadata.json"
        with metadata_file_path.open("w", encoding="utf-8") as f:
            json.dump(metadata_data, f, indent=4)
        print(f"Metadata 파일이 '{metadata_file_path}'에 저장되었습니다.")

def process_tasks(base_dir: Path) -> None:
    """
    base_dir 내의 각 태스크(폴더)에 대해 summary와 metadata 처리를 수행.
    """
    for task_dir in base_dir.iterdir():
        if task_dir.is_dir():
            process_summary_for_task(task_dir)
            process_metadata_for_task(task_dir)

def main():
    base_dir = Path(__file__).resolve().parent
    process_tasks(base_dir)

if __name__ == "__main__":
    main()
