import json
import math
from pathlib import Path

from src.utils.common import create_module_logger

MIN_REQUIRED_SIMULATIONS = 1
log = create_module_logger(module_name=__name__, module_log=True)


def load_summary_data(file_path):
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
            "scheduler_timingSuccess_rate_sum": 0.0,
            "scheduler_timingSuccess_rate_count": 0,
            "simulation_timingSuccess_rate_sum": 0.0,
            "simulation_timingSuccess_rate_count": 0,
            "attempt_values": [],
        }


def accumulate(
    metrics: dict, approach: str, value, sum_key: str, count_key: str
) -> None:
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


def process_summary_file(
    summary_path: Path, metrics: dict, llm_list: set, dag_list: set
) -> None:
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
        accumulate(
            metrics,
            approach,
            entry.get("simulation_makespan"),
            "simulation_makespan_sum",
            "simulation_makespan_count",
        )
        if approach in dag_list:
            accumulate(
                    metrics,
                    approach,
                    entry.get("scheduler_makespan"),
                    "scheduler_makespan_sum",
                    "scheduler_makespan_count",
            )
        accumulate(
            metrics,
            approach,
            entry.get("actionSuccess_rate"),
            "actionSuccess_rate_sum",
            "actionSuccess_rate_count",
        )
        accumulate(
            metrics,
            approach,
            entry.get("computation_time"),
            "computation_time_sum",
            "computation_time_count",
        )
        accumulate(
            metrics,
            approach,
            entry.get("scheduler_timingSuccess_rate"),
            "scheduler_timingSuccess_rate_sum",
            "scheduler_timingSuccess_rate_count",
        )
        accumulate(
            metrics,
            approach,
            entry.get("simulation_timingSuccess_rate"),
            "simulation_timingSuccess_rate_sum",
            "simulation_timingSuccess_rate_count",
        )


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


    # 각 approach별로 평균 계산 (집계된 simulation 수가 MIN_REQUIRED_SIMULATIONS 이상인 경우)
    results = {}
    for approach, vals in metrics.items():
        result = {}
        
        # scheduler_makespan 평균 (DAG 방식만)
        if approach in dag_list:
            if vals["scheduler_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_makespan_average"] = (
                    vals["scheduler_makespan_sum"] / vals["scheduler_makespan_count"]
                )
            else:
                result["scheduler_makespan_average"] = None

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
        
        # scheduler_timingSuccess_rate 평균 (DAG 방식만)
        if approach in dag_list:
            if vals["scheduler_timingSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_timingSuccess_rate_average"] = (
                    vals["scheduler_timingSuccess_rate_sum"] / vals["scheduler_timingSuccess_rate_count"]
                )
            else:
                result["scheduler_timingSuccess_rate_average"] = None
        
        # simulation_timingSuccess_rate 평균
        if vals["simulation_timingSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["simulation_timingSuccess_rate_average"] = (
                vals["simulation_timingSuccess_rate_sum"] / vals["simulation_timingSuccess_rate_count"]
            )
        else:
            result["simulation_timingSuccess_rate_average"] = None

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
    dag_list = {
        "dag_bayesian_simulation.json",
        "cpm_simulation.json",
        "dag_edf_simulation.json",
    }

    # 전체 평균을 위한 메트릭스
    overall_metrics = {}
    # 씬별 평균을 위한 메트릭스
    scene_metrics = {}

    # base_dir 내의 각 하위 폴더(태스크)를 순회
    for task_dir in base_dir.iterdir():
        if not task_dir.is_dir():
            continue

        # 각 씬 디렉토리를 순회
        for scene_dir in task_dir.iterdir():
            if not scene_dir.is_dir():
                continue

            scene_name = scene_dir.name
            metadata_dir = scene_dir / "metadata"
            summary_path = metadata_dir / "summary.json"
            if not summary_path.exists():
                print(f"[Warning] '{summary_path}' 파일이 존재하지 않습니다.")
                summary_path = metadata_dir / "summary_insuff.json"
                if not summary_path.exists():
                    print(f"[Warning] '{summary_path}' 파일도 존재하지 않습니다.")
                    continue

            # 씬별 메트릭스 초기화
            if scene_name not in scene_metrics:
                scene_metrics[scene_name] = {}

            # 씬별 및 전체에 동시에 누적
            process_summary_file(summary_path, scene_metrics[scene_name], llm_list, dag_list)
            process_summary_file(summary_path, overall_metrics, llm_list, dag_list)

    # 씬별 평균 계산 및 저장
    scene_results = {}
    for scene_name, metrics in scene_metrics.items():
        scene_results[scene_name] = calculate_averages(metrics, llm_list, dag_list)

    # 전체 평균 계산
    overall_results = calculate_averages(overall_metrics, llm_list, dag_list)

    # 결과 저장
    output_data = {
        "scene_averages": scene_results,
        "overall_average": overall_results
    }

    output_file = base_dir / "average.json"
    try:
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        print(f"평균 결과가 '{output_file}'에 저장되었습니다.")
    except Exception as e:
        print(f"[Error] 결과 파일 저장 실패: {e}")


def calculate_averages(metrics: dict, llm_list: set, dag_list: set) -> dict:
    """
    주어진 메트릭스에 대해 각 approach별 평균을 계산합니다.
    """
    results = {}
    for approach, vals in metrics.items():
        result = {}
        
        # scheduler_makespan 평균 (DAG 방식만)
        if approach in dag_list:
            if vals["scheduler_makespan_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_makespan_average"] = (
                    vals["scheduler_makespan_sum"] / vals["scheduler_makespan_count"]
                )
            else:
                result["scheduler_makespan_average"] = None

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
        
        # scheduler_timingSuccess_rate 평균 (DAG 방식만)
        if approach in dag_list:
            if vals["scheduler_timingSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
                result["scheduler_timingSuccess_rate_average"] = (
                    vals["scheduler_timingSuccess_rate_sum"] / vals["scheduler_timingSuccess_rate_count"]
                )
            else:
                result["scheduler_timingSuccess_rate_average"] = None
        
        # simulation_timingSuccess_rate 평균
        if vals["simulation_timingSuccess_rate_count"] >= MIN_REQUIRED_SIMULATIONS:
            result["simulation_timingSuccess_rate_average"] = (
                vals["simulation_timingSuccess_rate_sum"] / vals["simulation_timingSuccess_rate_count"]
            )
        else:
            result["simulation_timingSuccess_rate_average"] = None

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


def main():
    base_dir = Path(__file__).resolve().parent
    make_average(base_dir)


if __name__ == "__main__":
    main()
