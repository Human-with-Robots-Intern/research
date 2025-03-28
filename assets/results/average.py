import json
import os
import math

MIN_REQUIRED_SIMULATIONS = 5
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, module_log=True)

def load_summary_data(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] 파일 읽기 실패: {file_path} - {e}")
        return None

def make_average(base_dir):
    # llm_list에 해당하는 approach들은 attempt 평균 및 executing_action_count 평균을 계산함
    llm_list = [
        "prog_ai2thor_simulation.json",
        "cap_ai2thor_simulation.json"
    ]
    # scheduler_makespan을 계산할 approach 목록 (DAG 방식)
    dag_list = [
        "dag_bayesian_simulation.json",
        "cpm_simulation.json",
        "dag_edf_simulation.json"
    ]
    
    # 각 approach별로 집계할 지표의 합계와 카운트를 저장하는 dict 초기화
    metrics = {}

    # base_dir 내 하위 폴더를 순회 (각 폴더마다 metadata/summary.json 파일이 있다고 가정)
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        metadata_dir = os.path.join(folder_path, "metadata")
        summary_path = os.path.join(metadata_dir, "summary.json")
        if not os.path.exists(summary_path):
            print(f"[Warning] '{summary_path}' 파일이 존재하지 않습니다.")
            continue

        data = load_summary_data(summary_path)
        if data is None:
            continue

        # summary.json 내의 approach_comparisons 리스트를 순회
        comparisons = data.get("approach_comparisons", [])
        for entry in comparisons:
            approach = entry.get("approach_name")
            if approach is None:
                continue

            # 해당 approach에 대한 초기화
            if approach not in metrics:
                metrics[approach] = {
                    "simulation_makespan_sum": 0.0,
                    "simulation_makespan_count": 0,
                    "actionSuccess_rate_sum": 0.0,
                    "actionSuccess_rate_count": 0,
                    "computation_time_sum": 0.0,
                    "computation_time_count": 0,
                    "scheduler_makespan_sum": 0.0,
                    "scheduler_makespan_count": 0,
                    # attempt는 별도의 리스트에 숫자만 저장 (집계 방식이 다름)
                    "attempt_values": [],
                    "subtask_count_sum": 0.0,
                    "subtask_count_count": 0,
                    "executing_action_count_sum": 0.0,
                    "executing_action_count_count": 0
                }

            # 내부 함수: 값이 None 또는 무한대(inf)인 경우 제외하고 집계
            def accumulate(value, sum_key, count_key):
                if value is None:
                    return
                try:
                    val = float(value)
                except Exception:
                    return
                if math.isinf(val):
                    return
                metrics[approach][sum_key] += val
                metrics[approach][count_key] += 1

            # 기존 지표 집계
            accumulate(entry.get("simulation_makespan"), "simulation_makespan_sum", "simulation_makespan_count")
            accumulate(entry.get("actionSuccess_rate"), "actionSuccess_rate_sum", "actionSuccess_rate_count")
            accumulate(entry.get("computation_time"), "computation_time_sum", "computation_time_count")
            
            if approach in dag_list:
                accumulate(entry.get("scheduler_makespan"), "scheduler_makespan_sum", "scheduler_makespan_count")
            
            # LLM approach인 경우, attempt가 숫자면 리스트에 추가
            if approach in llm_list:
                attempt_val = entry.get("attempt")
                # "Not related"이거나 None이면 스킵
                if attempt_val is not None and attempt_val != "Not related":
                    try:
                        parsed_val = float(attempt_val)
                        if not math.isinf(parsed_val):
                            metrics[approach]["attempt_values"].append(parsed_val)
                    except ValueError:
                        log.debug(f"ValueErrot: {ValueError}")
                 

            # subtask_count 및 executing_action_count 집계
            if "subtask_count" in entry:
                accumulate(entry.get("subtask_count"), "subtask_count_sum", "subtask_count_count")
            if "executing_action_count" in entry:
                accumulate(entry.get("executing_action_count"), "executing_action_count_sum", "executing_action_count_count")

    # 각 approach별로 평균 계산 (집계된 simulation 수가 MIN_REQUIRED_SIMULATIONS 이상인 경우)
    results = {}
    for approach, vals in metrics.items():
        result = {}

        # simulation_makespan
        if vals["simulation_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["simulation_makespan_average"] = vals["simulation_makespan_sum"] / vals["simulation_makespan_count"]
        else:
            result["simulation_makespan_average"] = None

        # actionSuccess_rate
        if vals["actionSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["actionSuccess_rate_average"] = vals["actionSuccess_rate_sum"] / vals["actionSuccess_rate_count"]
        else:
            result["actionSuccess_rate_average"] = None

        # computation_time
        if vals["computation_time_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["computation_time_average"] = vals["computation_time_sum"] / vals["computation_time_count"]
        else:
            result["computation_time_average"] = None

        # scheduler_makespan (DAG approach에만)
        if approach in dag_list:
            if vals["scheduler_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_makespan_average"] = vals["scheduler_makespan_sum"] / vals["scheduler_makespan_count"]
            else:
                result["scheduler_makespan_average"] = None

        # attempt 평균 (LLM approach에만)
        if approach in llm_list:
            attempt_list = vals["attempt_values"]
            if len(attempt_list) == 0:
                # 모든 attempt가 "Not related"거나 없었음
                result["attempt_average"] = "Not related"
            elif len(attempt_list) < MIN_REQUIRED_SIMULATIONS:
                # MIN_REQUIRED_SIMULATIONS 미만인 경우 None
                result["attempt_average"] = None
            else:
                # 정상적으로 평균 계산
                result["attempt_average"] = sum(attempt_list) / len(attempt_list)

        # subtask_count 평균 (비-LLM approach or 일부 LLM에서 함께 쓸 수도 있음)
        if vals["subtask_count_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["subtask_count_average"] = vals["subtask_count_sum"] / vals["subtask_count_count"]
        else:
            result["subtask_count_average"] = None

        # executing_action_count 평균 (LLM approach에서 사용)
        if vals["executing_action_count_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["executing_action_count_average"] = vals["executing_action_count_sum"] / vals["executing_action_count_count"]
        else:
            result["executing_action_count_average"] = None

        results[approach] = result

    # 결과를 base_dir에 "average.json" 파일로 저장
    output_file = os.path.join(base_dir, "average.json")
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=4)
        print(f"평균 결과가 '{output_file}'에 저장되었습니다.")
    except Exception as e:
        print(f"[Error] 결과 파일 저장 실패: {e}")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    make_average(base_dir)

if __name__ == "__main__":
    main()
