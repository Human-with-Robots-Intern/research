import glob
import json
import os
from collections import defaultdict
from pathlib import Path

# 설정
TASKS_ROOT = "/home/dongkyu/pdk_ws/research/assets/tasks"
RESULTS_ROOT = "/home/dongkyu/pdk_ws/research/assets/results/260202_conflict_aware_wait"

# Task Set 후보
TASK_SETS = {
    "5070": "sampled_10_instruction_set_for_final_experiment_251231_5070",
    "pdk": "sampled_10_instruction_set_for_final_experiment_251203",
    "laptop6": "sampled_10_instruction_set_for_final_experiment_251231_laptop6",
    "bluebottle": "sampled_10_instruction_set_for_final_experiment_251231_bluebottle",
    "laptop4": "sampled_10_instruction_set_for_final_experiment_251231_laptop4",
}

# 결과 폴더 매핑
RESULT_DIRS = {
    "5070": "5070",
    "pdk": "pdk",
    "laptop6": "laptop6",
    "bluebottle": "bluebottle",
    "laptop4": "laptop4",
}


def get_tasks_from_dir(task_set_dir):
    """Task Set 폴더에서 (Task_Folder, Task_Name, FloorPlan) 목록을 추출"""
    tasks = []
    base_path = Path(TASKS_ROOT) / task_set_dir

    # 구조: {base_path}/{Category}/{FloorPlan}/{Task}.json
    # 예: tasks_2_constraints_1/FloorPlan1/01_boil_...json

    for json_path in base_path.glob("**/*.json"):
        if json_path.name.startswith("group_"):
            continue  # 메타데이터 제외 가능성

        # 상대 경로로 구조 파악
        rel_path = json_path.relative_to(base_path)
        parts = rel_path.parts

        if len(parts) >= 3:
            category = parts[0]  # tasks_2_constraints_1
            floorplan = parts[1]  # FloorPlan1
            task_name = parts[-1].replace(".json", "")

            # FloorPlan 폴더가 아닌 경우 (구조가 다를 수 있음) 체크
            if "FloorPlan" not in floorplan and "FloorPlan" in category:
                # tasks_2_constraints_1_FloorPlan1 같은 구조일수도 있음.
                # 하지만 일반적인 구조 가정.
                pass

            tasks.append(
                {
                    "category": category,
                    "floorplan": floorplan,
                    "task_name": task_name,
                    "full_path": str(rel_path),
                }
            )
    return tasks


def scan_results(result_dir_name):
    """결과 폴더를 스캔하여 수행된 실험 목록 추출"""
    # 구조 추정: {RESULTS_ROOT}/{result_dir_name}/states{Init}/...
    # 또는 {RESULTS_ROOT}/{result_dir_name}/init_{Init}/...
    # 사용자의 list_dir 결과에 따르면 'states120', 'init_120' 등이 섞여 있음.
    # 하지만 개별 Task 로그는 'states{Prior}' 또는 'init_{Prior}' 아래에 있을 확률 높음.

    executed = []  # list of (init_prior, method, category, floorplan, task_name)
    base_path = Path(RESULTS_ROOT) / result_dir_name

    # 1. 'states*' 폴더 탐색 (예: states120)
    for state_dir in base_path.glob("states*"):
        dir_name = state_dir.name
        if not dir_name.startswith("states"):
            continue
        prior = dir_name.replace("states", "")

        # 내부 탐색: {Category}/{TaskName}/{FloorPlan}/{Method}
        # list_dir 결과: 06_heat.../{FloorPlan}/{Method}
        # Category가 있을 수도 있고 없을 수도 있음.
        # list_dir 결과 예시: states120/tasks_2_constraints_1/06_heat...

        for method_dir in state_dir.glob("**/*"):
            if not method_dir.is_dir():
                continue
            if method_dir.name in [
                "cap_ai2thor_simulation",
                "cpm",
                "dag_edf",
                "progprompt",
            ]:
                # 경로 역추적
                # method_dir: .../states120/tasks_2_constraints_1/06_task.../FloorPlan1/cpm
                try:
                    parts = method_dir.relative_to(state_dir).parts
                    # parts: ('tasks_2_constraints_1', '06_task...', 'FloorPlan1', 'cpm')
                    if len(parts) >= 4:
                        method = parts[-1]
                        floorplan = parts[-2]
                        task_name = parts[-3]
                        category = parts[-4]

                        executed.append(
                            {
                                "prior": prior,
                                "method": method,
                                "category": category,
                                "floorplan": floorplan,
                                "task_name": task_name,
                            }
                        )
                except Exception as e:
                    pass

    return executed


def main():
    # 1. Task Set 로드
    task_sets_data = {}
    for alias, dirname in TASK_SETS.items():
        print(f"Loading Task Set: {alias} ({dirname})...")
        tasks = get_tasks_from_dir(dirname)
        task_sets_data[alias] = tasks
        print(f"  - Found {len(tasks)} tasks.")

    # 2. Result 로드
    results_data = {}
    for alias, dirname in RESULT_DIRS.items():
        print(f"Scanning Results for: {alias} ({dirname})...")
        results = scan_results(dirname)
        results_data[alias] = results
        print(f"  - Found {len(results)} execution records.")

    # 3. 'pdk'의 원본 Task Set 식별
    pdk_results = results_data["pdk"]
    pdk_task_names = set(r["task_name"] for r in pdk_results)

    candidates = ["pdk", "laptop6"]
    match_counts = {k: 0 for k in candidates}

    for candidate in candidates:
        candidate_tasks = set(t["task_name"] for t in task_sets_data[candidate])
        # 교집합 크기 확인
        match_counts[candidate] = len(pdk_task_names.intersection(candidate_tasks))

    print(f"\nTask Set Match for 'pdk': {match_counts}")
    best_pdk_source = max(match_counts, key=match_counts.get)
    print(f"Determined source for 'pdk': {best_pdk_source}")

    # 4. 분석 대상 설정
    # 모든 결과 폴더에 대해 매핑 설정
    # 타겟: 5070 -> 5070
    # 타겟: pdk -> best_pdk_source
    # 나머지: 이름 그대로 매핑 (예: laptop6 -> laptop6)
    
    target_mappings = []
    for alias in RESULT_DIRS.keys():
        if alias == "pdk":
            target_mappings.append(("pdk", best_pdk_source))
        else:
            target_mappings.append((alias, alias))

    # 5. Missing Check (매트릭스 형태로 현황 파악)
    
    # 전체 실험에서 발견된 Method, Prior 수집
    all_methods = ["cap_ai2thor_simulation", "progprompt"]
    all_priors = ["60", "70", "80", "90", "100", "110", "120", "130", "140"] # 명시적 지정

    print("\n--- EXECUTION MATRIX (Prior x Method) ---")
    print(f"Checking only methods: {all_methods}")
    
    for res_alias, task_set_alias in target_mappings:
        print(f"\nDataset: {res_alias} (Source: {task_set_alias})")
        print(
            f"{'Prior':<10} | {'cap_ai2thor':<15} | {'progprompt':<15}"
        )
        print("-" * 50)

        executed_records = results_data[res_alias]

        # Count per (prior, method)
        # Total tasks per dataset
        total_tasks = len(task_sets_data[task_set_alias])

        counts = defaultdict(int)
        for r in executed_records:
            counts[(r["prior"], r["method"])] += 1

        # 모든 발견된 Prior에 대해 출력
        for prior in sorted(list(all_priors), key=lambda x: int(x)):
            row = [f"{prior:<10}"]
            for method in all_methods:
                count = counts[(prior, method)]
                status = f"{count}/{total_tasks}"
                if count == 0:
                    status = "MISSING"
                elif count < total_tasks:
                    status = f"PARTIAL({count})"
                
                row.append(f"{status:<15}")
            print(" | ".join(row))


if __name__ == "__main__":
    main()
