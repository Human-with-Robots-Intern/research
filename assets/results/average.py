import json
import math
from pathlib import Path
from utils.util import create_module_logger

MIN_REQUIRED_SIMULATIONS = 5
log = create_module_logger(module_name=__name__, module_log=True)

def load_summary_data(file_path: Path) -> dict:
    """
    주어진 파일 경로에서 JSON 데이터를 읽어 반환합니다.
    실패 시 None을 반환합니다.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
        print(f"[Error] 파일 읽기 실패: {file_path} - {e}")
        return None

def initialize_metrics(metrics: dict, approach: str) -> None:
    """
    approach별로 누적할 지표 dict를 초기화합니다.
    """
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
            "attempt_values": [],
        }

def accumulate(metrics: dict, approach: str, value, sum_key: str, count_key: str) -> None:
    """
    값이 None이거나 무한대(inf)가 아닌 경우, 해당 approach의 metrics에서
    sum 및 count를 업데이트합니다.
    """
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

def process_summary_file(summary_path: Path, metrics: dict, llm_list: set, dag_list: set) -> None:
    """
    summary.json 파일 내의 각 approach에 대해 지표를 누적합니다.
    """
    data = load_summary_data(summary_path)
    if data is None:
        return

    comparisons = data.get("approach_comparisons", [])
    for entry in comparisons:
        approach = entry.get("approach_name")
        if approach is None:
            continue

        initialize_metrics(metrics, approach)

        # 기본 지표 누적
        accumulate(metrics, approach, entry.get("simulation_makespan"),
                   "simulation_makespan_sum", "simulation_makespan_count")
        accumulate(metrics, approach, entry.get("actionSuccess_rate"),
                   "actionSuccess_rate_sum", "actionSuccess_rate_count")
        accumulate(metrics, approach, entry.get("computation_time"),
                   "computation_time_sum", "computation_time_count")
        
        if approach in dag_list:
            accumulate(metrics, approach, entry.get("scheduler_makespan"),
                       "scheduler_makespan_sum", "scheduler_makespan_count")
        
        # LLM approach의 경우 attempt 값 처리
        if approach in llm_list:
            attempt_val = entry.get("attempt")
            if attempt_val is not None and attempt_val != "Not related":
                try:
                    parsed_val = float(attempt_val)
                    if not math.isinf(parsed_val):
                        metrics[approach]["attempt_values"].append(parsed_val)
                except ValueError:
                    log.debug("ValueError encountered while parsing attempt value")
        
        # subtask_count 및 executing_action_count 누적
        if "subtask_count" in entry:
            accumulate(metrics, approach, entry.get("subtask_count"),
                       "subtask_count_sum", "subtask_count_count")
        if "executing_action_count" in entry:
            accumulate(metrics, approach, entry.get("executing_action_count"),
                       "executing_action_count_sum", "executing_action_count_count")

def compute_averages(metrics: dict, llm_list: set, dag_list: set) -> dict:
    """
    누적된 지표들을 기반으로 각 approach별 평균값을 계산합니다.
    """
    results = {}
    for approach, vals in metrics.items():
        result = {}

        # simulation_makespan 평균
        if vals["simulation_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["simulation_makespan_average"] = (
                vals["simulation_makespan_sum"] / vals["simulation_makespan_count"]
            )
        else:
            result["simulation_makespan_average"] = None

        # actionSuccess_rate 평균
        if vals["actionSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["actionSuccess_rate_average"] = (
                vals["actionSuccess_rate_sum"] / vals["actionSuccess_rate_count"]
            )
        else:
            result["actionSuccess_rate_average"] = None

        # computation_time 평균
        if vals["computation_time_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["computation_time_average"] = (
                vals["computation_time_sum"] / vals["computation_time_count"]
            )
        else:
            result["computation_time_average"] = None

        # scheduler_makespan 평균 (DAG 방식만)
        if approach in dag_list:
            if vals["scheduler_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_makespan_average"] = (
                    vals["scheduler_makespan_sum"] / vals["scheduler_makespan_count"]
                )
            else:
                result["scheduler_makespan_average"] = None

        # attempt 평균 (LLM 방식만)
        if approach in llm_list:
            attempt_list = vals["attempt_values"]
            if len(attempt_list) == 0:
                result["attempt_average"] = "Not related"
            elif len(attempt_list) < MIN_REQUIRED_SIMULATIONS:
                result["attempt_average"] = None
            else:
                result["attempt_average"] = sum(attempt_list) / len(attempt_list)

        results[approach] = result

    return results

def make_average(base_dir: Path) -> None:
    llm_list = {"prog_ai2thor_simulation.json", "cap_ai2thor_simulation.json"}
    dag_list = {"dag_bayesian_simulation.json", "cpm_simulation.json", "dag_edf_simulation.json"}

    metrics = {}
    # base_dir 내의 각 하위 폴더(태스크)를 순회
    for folder in base_dir.iterdir():
        if not folder.is_dir():
            continue

        metadata_dir = folder / "metadata"
        summary_path = metadata_dir / "summary.json"
        if not summary_path.exists():
            print(f"[Warning] '{summary_path}' 파일이 존재하지 않습니다.")
            continue

        process_summary_file(summary_path, metrics, llm_list, dag_list)
    
    results = compute_averages(metrics, llm_list, dag_list)

    output_file = base_dir / "average.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)
        print(f"평균 결과가 '{output_file}'에 저장되었습니다.")
    except Exception as e:
        print(f"[Error] 결과 파일 저장 실패: {e}")


def main():
    base_dir = Path(__file__).resolve().parent
    make_average(base_dir)


if __name__ == "__main__":
    main()
