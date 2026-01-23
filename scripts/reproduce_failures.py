import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# 실행할 실패 케이스 목록 정의
failure_cases = [
    {
        "case": "tasks_3_constraints_1",
        "instruction": "01_cook_egg_and_wash_a_butterknife_and_wash_plate_and_cup.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "01_cook_egg_and_wash_a_butterknife_and_wash_plate_and_cup.json",
        "scene": "FloorPlan18",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "02_cook_egg_and_wash_a_tomato_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "02_cook_egg_and_wash_a_tomato_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan18",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "02_cook_egg_and_wash_a_tomato_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "03_heat_the_bread_using_microwave_and_wash_a_butterknife_and_wash_plate_and_cup.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "04_heat_the_bread_using_microwave_and_wash_a_spatula_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "04_heat_the_bread_using_microwave_and_wash_a_spatula_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "04_heat_the_bread_using_microwave_and_wash_a_spatula_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "06_heat_the_bread_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan13",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "06_heat_the_bread_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "06_heat_the_bread_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "07_heat_the_potato_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "07_heat_the_potato_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan13",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "07_heat_the_potato_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "07_heat_the_potato_using_microwave_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "08_make_a_coffee_and_put_apple_and_lettuce_in_fridge_and_wash_plate_and_cup.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "09_make_a_coffee_and_wash_a_spatula_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "09_make_a_coffee_and_wash_a_spatula_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "10_make_a_coffee_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "10_make_a_coffee_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_1",
        "instruction": "10_make_a_coffee_and_wash_all_fork_and_spoon_and_wash_apple_and_lettuce.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json",
        "scene": "FloorPlan1",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json",
        "scene": "FloorPlan13",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json",
        "scene": "FloorPlan27",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "06_heat_the_potato_using_microwave_and_cook_egg_and_wash_all_fork_and_spoon.json",
        "scene": "FloorPlan7",
    },
    {
        "case": "tasks_3_constraints_2",
        "instruction": "07_heat_the_potato_using_microwave_and_cook_egg_and_wash_plate_and_cup.json",
        "scene": "FloorPlan1",
    },
]


def run_experiment(case_info):
    # 로그 디렉토리 생성
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--retry_mode", action="store_true")
    argparser.add_argument("--init_prior_mean", type=int, default=130)
    args = argparser.parse_args()

    print(f"init_prior_mean: {args.init_prior_mean}")
    log_dir = (
        Path("logs/reproduce")
        / f"states{args.init_prior_mean}"
        / case_info["case"]
        / case_info["instruction"].replace(".json", "")
        / case_info["scene"]
        / "dag_bayesian"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"run_{args.init_prior_mean}.log"

    # 결과 파일 존재 여부 확인 (end_state.json)
    # assets/results/states130/tasks_3_constraints_1/01_cook_egg_and_wash_a_butterknife_and_wash_plate_and_cup/FloorPlan1/dag_bayesian_DEFAULT/end_state.json
    result_base_path = Path("assets/results/")
    result_dir = (
        result_base_path
        / f"states{args.init_prior_mean}"
        / case_info["case"]
        / case_info["instruction"].replace(".json", "")
        / case_info["scene"]
        / "dag_bayesian"
    )
    end_state_path = result_dir / "end_state.json"
    print(f"end_state_path: {end_state_path}")

    if end_state_path.exists() and not args.retry_mode:
        print(f"\n[SKIP] Result already exists: {end_state_path}")
        return

    if log_file_path.exists():
        # 이미 로그 파일 경로가 있다면 아얘 제거
        log_file_path.unlink()
        print(f"Removed existing log file: {log_file_path}")

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
        str(args.init_prior_mean),
        "--log-level",
        "DEBUG",  # 상세 로그 확인용
        "--log-path",
        str(log_file_path.absolute()),
    ]

    print("\n==================================================")
    print(f"Running Experiment: {case_info['instruction']} @ {case_info['scene']}")
    print(f"Logging to: {log_file_path}")
    print(f"Command: {' '.join(cmd)}")
    print("==================================================\n")

    try:
        # 서브프로세스 실행 및 출력 실시간 표시
        # 로그는 파일로도 저장되고, --log-path 인자를 통해 내부 로거에서도 파일로 저장됨.
        # 여기서는 콘솔 출력을 유지함.
        env = os.environ.copy()
        env["PDK_LOG_FILE"] = str(log_file_path.absolute())
        subprocess.run(cmd, check=True, env=env)
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
