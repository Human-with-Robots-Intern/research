import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Optional

import yaml

from src.utils.common import create_module_logger
from src.utils.config.constants import LOG_PATH, RESULT_PATH
from src.utils.io_utils.task_io import list_task_files


def parse_arguments() -> argparse.Namespace:
    """run_all.py 스크립트에 대한 명령행 인자를 파싱합니다."""
    parser = argparse.ArgumentParser(description="모든 실험 실행 스크립트")
    parser.add_argument(
        "--config",
        type=str,
        default="run_all_config.yaml",
        help="사용할 설정 파일 이름 (예: run_all_config.yaml)",
    )
    parser.add_argument(
        "--init_prior_mean",
        type=float,
        default=None,
        help="config 파일의 INIT_PRIOR_MEAN 값을 덮어씁니다.",
    )
    # 추가 오버라이드 옵션들 (config의 기본값을 덮어쓰기 위함)
    parser.add_argument(
        "--show_display",
        action="store_true",
        help="X11 직접 표시 활성화 (VNC보다 우선)",
    )
    parser.add_argument("--ros", action="store_true", help="ROS 활성화")
    parser.add_argument("--simulation", action="store_true", help="시뮬레이션 모드 활성화")
    parser.add_argument(
        "--cloud_rendering",
        action="store_true",
        help="AI2-THOR CloudRendering 모드 활성화 (표시 비활성화)",
    )
    parser.add_argument("--use_vnc", action="store_true", help="noVNC 브라우저 노출 활성화")
    parser.add_argument("--log_level", type=str, default=None, help="로그 레벨 덮어쓰기")
    parser.add_argument(
        "--max_workers",
        type=int,
        default=None,
        help="동시 실행 워커 수 덮어쓰기",
    )
    parser.add_argument(
        "--num_runs_per_instruction",
        type=int,
        default=None,
        help="각 instruction 반복 실행 횟수 덮어쓰기",
    )
    parser.add_argument(
        "--start_idx",
        type=int,
        default=None,
        help="사전정의 모드에서 시작 인덱스 덮어쓰기",
    )
    parser.add_argument(
        "--predefined",
        action="store_true",
        help="사전정의된 번호 기반 instruction 사용 강제",
    )
    parser.add_argument(
        "--approaches",
        type=str,
        default=None,
        help="콤마로 구분된 실행 스크립트 경로 목록",
    )
    parser.add_argument(
        "--scene_types",
        type=str,
        default=None,
        help="콤마로 구분된 scene 타입 목록 (예: kitchen,bathroom)",
    )
    parser.add_argument(
        "--scenes",
        type=str,
        default=None,
        help="콤마로 구분된 scene 이름 목록 (예: FloorPlan1,FloorPlan7)",
    )
    return parser.parse_args()


def load_config(config_name: str) -> dict:
    """Loads configuration from the specified yaml file in the scripts directory."""
    config_path = Path(__file__).parent / config_name
    if not config_path.exists():
        print(f"Error: Configuration file '{config_name}' not found.")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def resolve_wrappers(config: dict) -> tuple[Path, Optional[Path]]:
    """
    주어진 설정에 따라 내부 실행 래퍼와 선택적 표시(VNC) 래퍼를 결정합니다.

    Args:
        config: 실행 설정 딕셔너리

    Returns:
        (wrapper_script, display_wrapper) 튜플. display_wrapper는 사용하지 않으면 None.
    """
    # Inner wrapper: 항상 프로젝트 실행 래퍼 사용
    wrapper_script = Path(__file__).parent / "run_project.sh"

    # Optional display wrapper to expose display over VNC/noVNC
    # 우선순위: show_display > use_vnc > cloud_rendering
    if config.get("show_display", False):
        use_vnc = False
    elif bool(config.get("use_vnc", False)):
        use_vnc = True
    elif config.get("cloud_rendering", False):
        use_vnc = False
    else:
        use_vnc = False

    display_wrapper = Path(__file__).parent / "start_vnc.sh" if use_vnc else None

    return wrapper_script, display_wrapper


def run_with_retries(
    script: Path, input_str: str, scene_name: str, config: dict, max_retries: int = 10
) -> tuple[bool, int]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수), 실패하면 (False, 마지막 시도 횟수)를 반환합니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    for attempt in range(1, max_retries + 1):
        logger.debug(f"Running {script} (Attempt {attempt})...")
        logger.info(f"=" * 80)
        logger.info(
            f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}"
        )
        logger.info(f"=" * 80)

        cmd = [
            str(wrapper_script),
            "python3",
            str(script),
            "--scene",
            scene_name,
            "--reset",
            "--instruction",
            input_str,
        ]
        if config.get("ros"):
            cmd.append("--ros")
        if config.get("simulation"):
            logger.info(f"Simulation mode is enabled")
            cmd.append("--simulation")
        if config.get("cloud_rendering"):
            cmd.append("--cloud-rendering")
        if config.get("log_level"):
            cmd.extend(["--log-level", config["log_level"]])

        result = subprocess.run(cmd, stdout=None, stderr=None, text=True)

        logger.info(f"=" * 80)
        logger.info(
            f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}"
        )
        logger.info(f"=" * 80)

        if result.returncode == 0:
            return True, attempt
        if attempt < max_retries:
            logger.warning(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(config.get("retry_delay_seconds", 2))

    return False, attempt


def find_highest_instruction_folder(base_instruction: str) -> str:
    """
    assets/results/에서 base_instruction으로 시작하는 폴더 중
    가장 높은 숫자로 끝나는 폴더명을 반환합니다.

    Args:
        base_instruction: 기본 instruction 문자열

    Returns:
        가장 높은 번호를 가진 폴더명 (예: "cook egg_3")
    """

    # base_instruction으로 시작하는 폴더들을 찾기
    matching_folders = []
    for folder in RESULT_PATH.iterdir():
        if folder.is_dir() and folder.name.startswith(base_instruction):
            matching_folders.append(folder.name)

    # 각 폴더명에서 마지막 숫자를 추출하여 가장 높은 것 찾기
    highest_num = -1
    best_folder = base_instruction

    for folder_name in matching_folders:
        numbers = re.findall(r"\d+$", folder_name)
        if numbers:
            num = int(numbers[0])
            if num > highest_num:
                highest_num = num
                best_folder = folder_name

    return best_folder


def process_retry_script(
    script: Path,
    instruction: str,
    scene_name: str,
    config: dict,
    log_path: Path,
    wrapper_script: Path,
    display_wrapper: Optional[Path],
) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    approach = script.stem
    input_str = f"{instruction}\n"

    max_retries = config.get("max_retries", 10)

    # wrapper_script / outer_wrapper는 호출부에서 resolve_wrappers로 미리 결정됨

    for attempt in range(1, max_retries + 1):
        logger.debug(f"Running {script} (Attempt {attempt})...")

        logger.info(f"=" * 80)
        logger.info(
            f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}"
        )
        logger.info(f"=" * 80)

        base_cmd = ["python3", str(script)]

        # Build command with optional display (VNC) wrapper
        if display_wrapper is not None:
            cmd = [
                str(display_wrapper),
                str(wrapper_script),
                *base_cmd,
                "--scene",
                scene_name,
                "--reset",
                "--instruction",
                input_str,
            ]
        else:
            cmd = [
                str(wrapper_script),
                *base_cmd,
                "--scene",
                scene_name,
                "--reset",
                "--instruction",
                input_str,
            ]
        if config.get("ros"):
            cmd.append("--ros")
        if config.get("simulation"):
            cmd.append("--simulation")
        if config.get("cloud_rendering"):
            cmd.append("--cloud-rendering")
        if config.get("log_level"):
            cmd.extend(["--log-level", config["log_level"]])
        if log_path:
            cmd.extend(["--log-path", str(log_path)])
        if config.get("init_prior_mean") is not None:
            cmd.extend(["--init_prior_mean", str(config["init_prior_mean"])])
        cmd.extend(["--attempt", str(attempt)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        logger.info(f"=" * 80)
        logger.info(
            f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}"
        )
        logger.info(f"=" * 80)

        if result.returncode == 0:
            # 성공 로그
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"\n--- SUCCESS (Attempt {attempt}) ---\n")
                f.write(result.stdout)
            return

        if attempt < max_retries:
            logger.warning(f"Retrying {script} after failure (Attempt {attempt})...")
            # 실패 로그
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"\n--- FAILURE (Attempt {attempt}) ---\n")
                f.write(f"Return Code: {result.returncode}\n")
                f.write("--- STDOUT ---\n")
                f.write(result.stdout)
                f.write("\n--- STDERR ---\n")
                f.write(result.stderr)
            time.sleep(config.get("retry_delay_seconds", 2))

    # 모든 재시도 실패 후 최종 로그
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n--- FINAL FAILURE (After {max_retries} attempts) ---\n")
        f.write(f"Return Code: {result.returncode}\n")
        f.write("--- STDOUT ---\n")
        f.write(result.stdout)
        f.write("\n--- STDERR ---\n")
        f.write(result.stderr)

    task_name_for_result_folder = instruction
    try:
        choice = int(instruction)
        tasks = list_task_files(scene_name)
        if 1 <= choice <= len(tasks):
            task_name_for_result_folder = Path(tasks[choice - 1]).stem
            logger.info(
                f"Instruction '{instruction}' resolved to task name: '{task_name_for_result_folder}'"
            )
        else:
            logger.warning(
                f"Instruction number {choice} is out of range for scene {scene_name}. Using the number itself as the task name."
            )
    except (ValueError, TypeError):
        pass  # Not a numeric instruction, use as is.

    highest_instruction_folder = find_highest_instruction_folder(
        task_name_for_result_folder
    )
    result_path = (
        RESULT_PATH
        / highest_instruction_folder
        / scene_name
        / "approach"
        / f"{approach}_simulation.json"
    )

    result_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    data = {
        "saved_time": time_str,
        "approach": approach,
        "attempt": max_retries,
        "scene_name": scene_name,
        "plans": [{"plan_name": task_name_for_result_folder}],
        "computation_time": -1,
        "success_rate": 0,
        "scheduler_makespan": None,
        "simulation_makespan": -1,
        "realworld_makespan": None,
    }
    with result_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def process_normal_script(
    script: Path,
    instruction: str,
    scene_name: str,
    config: dict,
    log_path: Path,
    wrapper_script: Path,
    display_wrapper: Optional[Path],
) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction을 command-line 인자로 전달합니다.
    """
    # wrapper_script / outer_wrapper는 호출부에서 resolve_wrappers로 미리 결정됨
    logger.warning(f"Running {script},{scene_name},{instruction}...")

    logger.info(f"=" * 80)
    logger.info(f"Starting {script} with scene={scene_name}, instruction={instruction}")
    logger.info(f"=" * 80)

    logger.info(f"=" * 80)
    for i in range(config.get("instruction_delay_seconds", 30), 0, -5):
        logger.info(f"{i} seconds left before running instruction")
        time.sleep(5)
    logger.info(f"Start!")
    logger.info(f"=" * 80)

    base_cmd = ["python3", str(script)]

    # Build command with optional display (VNC) wrapper
    if display_wrapper is not None:
        cmd = [
            str(display_wrapper),
            str(wrapper_script),
            *base_cmd,
            "--scene",
            scene_name,
            "--reset",
            "--instruction",
            instruction,
        ]
    else:
        cmd = [
            str(wrapper_script),
            *base_cmd,
            "--scene",
            scene_name,
            "--reset",
            "--instruction",
            instruction,
        ]
    if config.get("ros"):
        cmd.append("--ros")
    if config.get("simulation"):
        cmd.append("--simulation")
    if config.get("cloud_rendering"):
        cmd.append("--cloud-rendering")
    if config.get("log_level"):
        cmd.extend(["--log-level", config["log_level"]])
    if log_path:
        cmd.extend(["--log-path", str(log_path)])
    if config.get("init_prior_mean") is not None:
        cmd.extend(["--init_prior_mean", str(config["init_prior_mean"])])

    result = subprocess.run(cmd, capture_output=True, text=True)

    logger.info(f"=" * 80)
    logger.info(f"Finished {script} with return code: {result.returncode}")
    logger.info(f"=" * 80)

    if result.returncode != 0:
        logger.error(f"Script {script} failed with error code: {result.returncode}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n--- FAILURE ---\n")
            f.write(f"Return Code: {result.returncode}\n")
            f.write("--- STDOUT ---\n")
            f.write(result.stdout)
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr)
    else:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n--- SUCCESS ---\n")
            f.write(result.stdout)


def worker(
    scene_name: str,
    approach: Path,
    instruction: str | int,
    run_idx: int,
    config: dict,
    llm_scripts: set[Path],
    start_idx: int,
    file_copy_lock: threading.Lock,
    wrapper_script: Path,
    display_wrapper: Optional[Path],
) -> None:
    """
    단일 instruction 실행을 위한 작업자 함수.
    """
    # Create a unique log file path for this worker
    log_file_name = (
        f"{scene_name}_{Path(approach).stem}_{instruction}_{run_idx + 1}.log"
    )
    log_file_path = LOG_PATH / "worker_logs" / log_file_name
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    if config.get("predefined"):
        if isinstance(instruction, int) and instruction < start_idx:
            return

        with file_copy_lock:
            object_mapping = (
                Path(__file__).parent.parent / "src/ros/ttp_ws/data/object_mapping.json"
            )
            object_positions = (
                Path(__file__).parent.parent
                / "src/ros/ttp_ws/data/object_positions.json"
            )
            if object_mapping.exists():
                shutil.copy2(object_mapping, object_positions)
                logger.info(
                    f"Initialized {object_positions} for instruction {instruction}"
                )
            else:
                logger.warning(f"Source file {object_mapping} does not exist")

    logger.info(f"task_name : {instruction}")
    logger.info(
        f"scene_name : {scene_name}, approach : {approach}, run_num : {run_idx+1}"
    )

    instr_str = str(instruction)
    if approach in llm_scripts:
        process_retry_script(
            approach,
            instr_str,
            scene_name,
            config,
            log_file_path,
            wrapper_script,
            display_wrapper,
        )
    else:
        process_normal_script(
            approach,
            instr_str,
            scene_name,
            config,
            log_file_path,
            wrapper_script,
            display_wrapper,
        )


def load_instructions_from_json(scene_name: str) -> list[str]:
    """
    주어진 scene에 대한 instruction을 JSON 파일에서 로드합니다.
    """
    number = int(scene_name.lstrip("FloorPlan"))
    if number >= 400:
        base_file = "bathroom_scene.json"
    elif number >= 300:
        base_file = "real_world_scene.json"
    else:
        base_file = "kitchen_scene.json"

    instructions = []

    # Load base instructions
    base_path = Path("assets/tasks/nl_instructions") / base_file
    try:
        with base_path.open("r", encoding="utf-8") as f:
            base_data = json.load(f)
            instructions.extend(base_data["instructions"])
    except Exception as e:
        logger.error(f"Failed to load base instructions from {base_path}: {e}")

    # Load scene-specific instructions
    scene_path = Path("assets/tasks/nl_instructions") / f"{scene_name}.json"
    try:
        with scene_path.open("r", encoding="utf-8") as f:
            scene_data = json.load(f)
            instructions.extend(scene_data["instructions"])
    except Exception as e:
        logger.warning(
            f"Failed to load scene-specific instructions from {scene_path}: {e}"
        )

    return instructions


def main() -> None:
    args = parse_arguments()
    config = load_config(args.config)

    # 명령행 인자가 제공된 경우, config 값을 덮어씁니다.
    if args.init_prior_mean is not None:
        config["init_prior_mean"] = args.init_prior_mean

    # 선택적 오버라이드 반영
    if args.ros:
        config["ros"] = True
        config["simulation"] = False
    if args.simulation:
        config["simulation"] = True
        config["ros"] = False
    if args.cloud_rendering:
        config["cloud_rendering"] = True
    # 표시 모드 우선순위 적용: show_display > use_vnc > cloud_rendering
    if args.show_display:
        config["show_display"] = True
        config["use_vnc"] = False
        config["cloud_rendering"] = False
    elif args.use_vnc:
        config["use_vnc"] = True
        config["cloud_rendering"] = False

    # Initialize a global logger for the main script
    global logger
    logger = create_module_logger(
        module_name=__name__, module_log=True, level=config.get("log_level", "DEBUG")
    )

    approaches = [Path(p) for p in config.get("approaches", [])]
    if config.get("llm_scripts", []):
        llm_scripts = {Path(p) for p in config.get("llm_scripts", [])}
    else:
        llm_scripts = set()

    scene_type_config = config.get("scene_type", "kitchen")
    if isinstance(scene_type_config, str):
        scene_types = [scene_type_config]
    else:
        scene_types = scene_type_config

    scene_list = []
    for scene_type in scene_types:
        scene_list.extend(config.get("scene_lists", {}).get(scene_type, []))

    num_runs_per_instruction = config.get("num_runs_per_instruction", 1)
    start_idx = config.get("start_idx", 0)
    max_workers = config.get("max_workers", 1)
    file_copy_lock = threading.Lock()

    # Log current  configuration
    logger.info("Current configuration:")
    logger.info("-" * 40)
    logger.info(f"Log level: {config.get('log_level')}")
    logger.info(f"Scene types: {scene_types}")
    logger.info(f"Scenes to run: {scene_list}")
    logger.info(f"Predefined mode: {config.get('predefined', False)}")
    logger.info(f"ROS enabled: {config.get('ros', False)}")
    logger.info(f"Simulation mode: {config.get('simulation', False)}")
    logger.info(f"Cloud Rendering: {config.get('cloud_rendering', False)}")
    logger.info(f"Max workers: {max_workers}")
    logger.info(f"Approaches: {[str(p) for p in approaches]}")
    # logger.info(f"LLM scripts: {[str(p) for p in llm_scripts]}")
    logger.info(f"Runs per instruction: {num_runs_per_instruction}")
    logger.info(f"Max retries: {config.get('max_retries', 10)}")
    logger.info(f"Retry delay: {config.get('retry_delay_seconds', 2)} seconds")
    logger.info(f"Init Prior Mean: {config.get('init_prior_mean', 'Default (60.0)')}")
    logger.info("-" * 40)

    execute_dict = config.get("execute_dict", {})

    # 래퍼를 한 번만 결정해서 모든 워커에 전달
    wrapper_script, display_wrapper = resolve_wrappers(config)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for scene_name, approach in product(scene_list, approaches):
            instructions = load_instructions_from_json(scene_name)

            instruction_source: list[str] or list[int]
            if config.get("predefined"):
                instruction_source = list(range(1, len(instructions) + 1))
            else:
                instruction_source = instructions

            for instruction, i in product(
                instruction_source, range(num_runs_per_instruction)
            ):
                # If execute_dict is provided, only run instructions present in it
                if execute_dict:
                    # Check if the scene is in the dict and if the instruction is in the list for that scene
                    if (
                        scene_name not in execute_dict
                        or instruction not in execute_dict.get(scene_name, [])
                    ):
                        continue

                futures.append(
                    executor.submit(
                        worker,
                        scene_name,
                        approach,
                        instruction,
                        i,
                        config,
                        llm_scripts if llm_scripts else set(),
                        start_idx,
                        file_copy_lock,
                        wrapper_script,
                        display_wrapper,
                    )
                )

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"A task generated an exception: {e}")
                logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
