import glob
import json
import os
from collections import defaultdict
from pathlib import Path

# 설정
TASKS_ROOT = "/home/dongkyu/pdk_ws/research/assets/tasks"
RESULTS_ROOT = "/home/dongkyu/pdk_ws/research/assets/results/260208_final_sim_exp_result"

# Task Set 후보
TASK_SETS = {
    "5070": "sampled_10_instruction_set_for_final_experiment_251231_5070",
    "pdk": "sampled_10_instruction_set_for_final_experiment_251203",
    "laptop6": "sampled_10_instruction_set_for_final_experiment_251231_laptop6",
    "bluebottle": "sampled_10_instruction_set_for_final_experiment_251231_bluebottle",
    "laptop4": "sampled_10_instruction_set_for_final_experiment_251231_laptop4",
}

# 결과 폴더 매핑
# RESULT_DIRS = {
#     "5070": "5070",
#     "pdk": "pdk",
#     "laptop6": "laptop6",
#     "bluebottle": "bluebottle",
#     "laptop4": "laptop4",
# }


def get_all_result_dirs():
    """RESULTS_ROOT 아래의 모든 디렉토리를 자동으로 찾습니다."""
    base_path = Path(RESULTS_ROOT)
    dirs = {}
    if base_path.exists():
        for p in base_path.iterdir():
            if (
                p.is_dir()
                and not p.name.startswith("__")
                and not p.name.startswith(".")
            ):
                # 폴더 이름을 그대로 키와 값으로 사용
                dirs[p.name] = p.name
    return dirs


RESULT_DIRS = get_all_result_dirs()


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

            # dag_bayesian 계열이 포함되도록 필터링 조건 확장
            # 기존: ["cap_ai2thor_simulation", "cpm", "dag_edf", "progprompt"]
            # 변경: 주요 키워드가 포함되어 있는지 확인 (더 유연하게)

            target_keywords = [
                "cap_ai2thor_simulation",
                "cpm",
                "dag_edf",
                "progprompt",
                "dag_bayesian_DEFAULT",
                "dag_bayesian_NONE_MONITORING",
            ]

            is_target_method = False
            for keyword in target_keywords:
                if keyword in method_dir.name:
                    is_target_method = True
                    break

            if not is_target_method:
                continue

            try:
                # trajectory_log.json 파일 확인
                traj_log = method_dir / "trajectory_log.json"
                if not traj_log.exists():
                    continue

                parts = method_dir.relative_to(state_dir).parts
                # parts: ('tasks_2_constraints_1', '06_task...', 'FloorPlan1', 'dag_bayesian_DEFAULT')

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
    best_pdk_source = "pdk"  # Default value
    if "pdk" in results_data:
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
    else:
        print("\n'pdk' folder not found in results. Skipping source determination for 'pdk'.")

    # Alias 정규화 매핑 (사용자 정의 규칙)
    # Key: 결과 폴더 이름, Value: 통합될 대표 이름 (Task Set Alias와 일치시키는 것이 좋음)
    alias_map = {
        # "5070": "5070",
        "sampled_10_instruction_set_for_final_experiment_251231_5070": "5070",
        # "pdk": "pdk",
        "sampled_10_instruction_set_for_final_experiment_251203": "pdk",
        # "laptop6": "laptop6",
        "sampled_10_instruction_set_for_final_experiment_251231_laptop6": "laptop6",
        # "bluebottle": "bluebottle",
        "sampled_10_instruction_set_for_final_experiment_251231_bluebottle": "bluebottle",
        # "laptop4": "laptop4",
        "sampled_10_instruction_set_for_final_experiment_251231_laptop4": "laptop4",
    }

    # 5. Matrix Printing Function
    DATASET_ORDER = [
        "pdk",
        "sampled_10_instruction_set_for_final_experiment_251203",
        "laptop6",
        "sampled_10_instruction_set_for_final_experiment_251231_laptop6",
        "bluebottle",
        "sampled_10_instruction_set_for_final_experiment_251231_bluebottle",
        "laptop4",
        "sampled_10_instruction_set_for_final_experiment_251231_laptop4",
        "5070",
        "sampled_10_instruction_set_for_final_experiment_251231_5070",
    ]

    def print_matrix(title, data_dict, mappings):
        # 전체 실험에서 발견된 Method, Prior 수집
        all_methods = set()
        all_priors = set()

        for records in data_dict.values():
            for r in records:
                all_methods.add(r["method"])
                all_priors.add(r["prior"])

        # 정렬
        all_methods = sorted(list(all_methods))
        all_priors = sorted(
            list(all_priors), key=lambda x: int(x) if x.isdigit() else 999
        )

        print(f"\n--- {title} ---")
        # print(f"Detected Methods: {all_methods}")
        # print(f"Detected Priors: {all_priors}")

        # 정렬: DATASET_ORDER에 있는 경우 우선, 그 외는 알파벳 순
        def get_order_key(item):
            alias = item[0]
            if alias in DATASET_ORDER:
                return DATASET_ORDER.index(alias)
            return len(DATASET_ORDER) + (1 if alias else 0)

        sorted_mappings = sorted(mappings, key=get_order_key)

        for res_alias, task_set_alias in sorted_mappings:
            print(f"\nDataset: {res_alias} (Source: {task_set_alias})")

            # 헤더 출력
            header = f"{'Prior':<10}"
            for method in all_methods:
                header += f" | {method[:25]:<25}"
            print(header)
            print("-" * len(header))

            executed_records = data_dict[res_alias]

            # Total tasks per dataset
            if task_set_alias and task_set_alias in task_sets_data:
                total_tasks = len(task_sets_data[task_set_alias])
            else:
                total_tasks = 0  # Unknown

            counts = defaultdict(int)
            for r in executed_records:
                counts[(r["prior"], r["method"])] += 1

            for prior in all_priors:
                row = [f"{prior:<10}"]
                for method in all_methods:
                    count = counts[(prior, method)]
                    if total_tasks > 0:
                        status = f"{count}/{total_tasks}"
                        if count == 0:
                            status = "MISSING"
                        elif count < total_tasks:
                            status = f"PARTIAL({count})"
                    else:
                        status = f"{count}/?"

                    row.append(f"{status:<25}")
                print(" | ".join(row))

    # --- 4. Raw Folder Matrix ---

    # Raw Mapping 생성
    raw_mappings = []
    for dirname in results_data.keys():
        # Task Set 추정
        target_ts = None

        # 1. Alias Map을 역으로 이용하거나, 직접 매칭
        # "5070" -> "sampled...5070" (TASK_SETS["5070"])

        if dirname == "pdk":
            target_ts = best_pdk_source
        elif (
            dirname in TASK_SETS
        ):  # dirname이 "5070"이고 TASK_SETS에 "5070" 키가 있다면
            target_ts = dirname
        else:
            # alias_map의 키에 있는지 확인
            for k, v in alias_map.items():
                if k == dirname:
                    # v는 "5070" (short alias). TASK_SETS[v]가 존재하면 그것.
                    if v in TASK_SETS:
                        target_ts = v
                    break

        # 아직 못 찾았다면 Substring 매칭 시도
        if not target_ts:
            for ts_alias in TASK_SETS.keys():
                if dirname in ts_alias or ts_alias in dirname:
                    target_ts = ts_alias
                    break

        if not target_ts:
            # Task Set 폴더명 자체와 매칭 시도
            for ts_alias, ts_dir in TASK_SETS.items():
                if dirname == ts_dir:
                    target_ts = ts_alias
                    break

        raw_mappings.append((dirname, target_ts))

    print_matrix("EXECUTION MATRIX (Per Folder)", results_data, raw_mappings)

    # --- 5. Merged Matrix ---

    # 결과 데이터 통합 (Merging)
    merged_results = defaultdict(list)
    for dirname, records in results_data.items():
        # 매핑 규칙에 없으면 그대로 사용
        target_alias = alias_map.get(dirname, dirname)
        merged_results[target_alias].extend(records)
        if target_alias != dirname:
            print(f"Merging results from '{dirname}' into '{target_alias}'")

    # 통합된 결과를 바탕으로 타겟 매핑 재설정
    merged_mappings = []

    for res_alias in merged_results.keys():
        if res_alias == "pdk":
            merged_mappings.append(("pdk", best_pdk_source))
        elif res_alias in task_sets_data:
            merged_mappings.append((res_alias, res_alias))
        else:
            found = False
            for task_set_alias in task_sets_data.keys():
                if res_alias in task_set_alias or task_set_alias in res_alias:
                    merged_mappings.append((res_alias, task_set_alias))
                    found = True
                    break
            if not found:
                print(
                    f"Warning: No matching Task Set found for result group '{res_alias}'."
                )
                merged_mappings.append((res_alias, None))

    print_matrix("EXECUTION MATRIX (Merged)", merged_results, merged_mappings)


if __name__ == "__main__":
    main()
