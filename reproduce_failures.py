import subprocess
import sys
import time

# 실행할 실패 케이스 목록 정의
failure_cases = [
    # 1. tasks_2_constraints_2 / 01 / FloorPlan7
    {
        "case": "tasks_2_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave.json",
        "scene": "FloorPlan7",
    },
    # 2. tasks_3_constraints / 06 / FloorPlan27
    {
        "case": "tasks_3_constraints_1",
        "instruction": "06_heat_the_bread_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    # 3. tasks_3_constraints_2 / 01 / FloorPlan7
    {
        "case": "tasks_3_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json",
        "scene": "FloorPlan7",
    },
    # 4. tasks_3_constraints_2 / 04 / FloorPlan13
    {
        "case": "tasks_3_constraints_2",
        "instruction": "04_heat_the_bread_using_microwave_and_make_a_coffee_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan13",
    },
    # 5. tasks_3_constraints_2 / 08 / FloorPlan7
    {
        "case": "tasks_3_constraints_2",
        "instruction": "08_heat_the_potato_using_microwave_and_make_a_coffee_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan7",
    },
    # 6. tasks_3_constraints_2 / 08 / FloorPlan13
    {
        "case": "tasks_3_constraints_2",
        "instruction": "08_heat_the_potato_using_microwave_and_make_a_coffee_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan13",
    },
]


def run_experiment(case_info):
    cmd = [
        sys.executable,
        "src/dag_bayesian.py",
        "--case",
        case_info["case"],
        "--instruction",
        case_info["instruction"],
        "--scene",
        case_info["scene"],
        "--simulation",  # 시뮬레이션 모드 활성화
        "--init_prior_mean",
        "100",  # 기본값 명시 (필요시 수정)
        "--log-level",
        "DEBUG",  # 상세 로그 확인용
    ]

    print(f"\n==================================================")
    print(f"Running Experiment: {case_info['instruction']} @ {case_info['scene']}")
    print(f"Command: {' '.join(cmd)}")
    print(f"==================================================\n")

    try:
        # 서브프로세스 실행 및 출력 실시간 표시
        subprocess.run(cmd, check=True)
        print(f"\n[SUCCESS] Completed: {case_info['instruction']}")
    except subprocess.CalledProcessError as e:
        print(f"\n[FAILURE] Error running {case_info['instruction']}: {e}")
    except KeyboardInterrupt:
        print("\n[ABORT] Interrupted by user.")
        sys.exit(1)


def main():
    print(f"Starting reproduction of {len(failure_cases)} failure cases...")
    start_time = time.time()

    for i, case_info in enumerate(failure_cases, 1):
        print(f"\nProgress: [{i}/{len(failure_cases)}]")
        run_experiment(case_info)
        # 각 실험 사이에 잠시 대기 (리소스 정리 등)
        time.sleep(2)

    elapsed = time.time() - start_time
    print(f"\nAll experiments completed in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    main()
