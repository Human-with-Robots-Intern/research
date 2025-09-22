import concurrent.futures
import json
import re
import shutil
import subprocess
import threading
import time
import traceback
from datetime import datetime
from itertools import product
from pathlib import Path

import yaml

import src.utils.config.constants as constants
from src.utils.common import create_module_logger
from src.utils.io_utils.task_io import list_task_files

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_PATH = REPO_ROOT / "src" / "utils" / "config" / "constants.py"


def _format_scalar(value: float) -> str:
    """부동소수점 값을 문자열로 포맷팅합니다."""
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):.1f}"
    return f"{value}"


def _format_tag(mean: float) -> str:
    """태그 생성을 위해 mean 값을 문자열로 변환합니다."""
    rounded = round(mean)
    if abs(mean - rounded) < 1e-9:
        mean_str = str(rounded)
    else:
        mean_str = str(mean).replace(".", "_")
    return mean_str


def _replace_assignment(content: str, name: str, expr: str) -> str:
    """파일 내용에서 변수 할당 부분을 찾아 교체합니다."""
    pattern = rf"^(?P<lhs>{name}\s*=\s*).*$"
    replacement = rf"\g<lhs>{expr}"
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"constants.py에서 '{name}' 변수를 찾지 못했습니다.")
    return updated


def prepare_constants(
    baseline_content: str, init_prior_mean: float, gt_interval: float
) -> str:
    """INIT_PRIOR_MEAN과 GT_INTERVAL 값을 수정한 constants.py 파일 내용을 반환합니다."""
    content = _replace_assignment(
        baseline_content, "INIT_PRIOR_MEAN", _format_scalar(init_prior_mean)
    )
    content = _replace_assignment(content, "GT_INTERVAL", _format_scalar(gt_interval))
    return content


def ensure_directories(tag: str | None) -> None:
    """실험 결과와 로그를 저장할 디렉토리를 생성합니다."""
    if not tag:
        return
    (REPO_ROOT / "logs" / tag).mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "assets" / "results" / tag).mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Loads configuration from scripts/config.yaml."""
    config_path = Path(__file__).parent / "run_all_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


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

        logger.info("=" * 80)
        logger.info(
            f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}"
        )
        logger.info("=" * 80)

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
            cmd.append("--simulation")
        if config.get("cloud_rendering"):
            cmd.append("--cloud-rendering")
        if config.get("log_level"):
            cmd.extend(["--log-level", config["log_level"]])

        result = subprocess.run(cmd, stdout=None, stderr=None, text=True)

        logger.info("=" * 80)
        logger.info(
            f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}"
        )
        logger.info("=" * 80)

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
    for folder in constants.RESULT_PATH.iterdir():
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
    script: Path, instruction: str, scene_name: str, config: dict, log_path: Path
) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    approach = script.stem
    input_str = f"{instruction}\n"

    max_retries = config.get("max_retries", 10)

    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    for attempt in range(1, max_retries + 1):
        logger.debug(f"Running {script} (Attempt {attempt})...")

        logger.info("=" * 80)
        logger.info(
            f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}"
        )
        logger.info("=" * 80)

        base_cmd = ["python3", str(script)]
        if config.get("headless"):
            base_cmd = ["xvfb-run", "-a"] + base_cmd

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
        cmd.extend(["--attempt", str(attempt)])

        # Add result path argument
        result_path_for_subprocess = constants.RESULT_PATH
        cmd.extend(["--result-path", str(result_path_for_subprocess)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        logger.info("=" * 80)
        logger.info(
            f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}"
        )
        logger.info("=" * 80)

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
        constants.RESULT_PATH
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
    script: Path, instruction: str, scene_name: str, config: dict, log_path: Path
) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction을 command-line 인자로 전달합니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    logger.warning(f"Running {script},{scene_name},{instruction}...")

    logger.info("=" * 80)
    logger.info(f"Starting {script} with scene={scene_name}, instruction={instruction}")
    logger.info("=" * 80)

    logger.info("=" * 80)
    for i in range(config.get("instruction_delay_seconds", 30), 0, -5):
        logger.info(f"{i} seconds left before running instruction")
        time.sleep(5)
    logger.info("Start!")
    logger.info("=" * 80)

    base_cmd = ["python3", str(script)]
    if config.get("headless"):
        base_cmd = ["xvfb-run", "-a"] + base_cmd

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

    # Add result path argument
    result_path_for_subprocess = constants.RESULT_PATH
    cmd.extend(["--result-path", str(result_path_for_subprocess)])

    result = subprocess.run(cmd, capture_output=True, text=True)

    logger.info("=" * 80)
    logger.info(f"Finished {script} with return code: {result.returncode}")
    logger.info("=" * 80)

    if result.returncode != 0:
        logger.error(f"Script {script} failed with error code: {result.returncode}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n--- FAILURE ---\n")
            f.write(f"Return Code: {result.returncode}\n")
            f.write("--- STDOUT ---\n")
            f.write(result.stdout)
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr)
    else:
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n--- SUCCESS ---\n")
            f.write(result.stdout)


def worker(
    scene_name: str,
    approach: Path,
    instruction: str or int,
    run_idx: int,
    config: dict,
    llm_scripts: set[Path],
    start_idx: int,
    file_copy_lock: threading.Lock,
) -> None:
    """
    단일 instruction 실행을 위한 작업자 함수.
    """
    # Create a unique log file path for this worker
    log_file_name = (
        f"{scene_name}_{Path(approach).stem}_{instruction}_{run_idx + 1}.log"
    )
    log_file_path = constants.LOG_PATH / "worker_logs" / log_file_name
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
        process_retry_script(approach, instr_str, scene_name, config, log_file_path)
    else:
        process_normal_script(approach, instr_str, scene_name, config, log_file_path)


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


def run_all_experiments(config: dict) -> None:
    """단일 구성에 대한 모든 실험을 실행합니다."""
    approaches = [Path(p) for p in config.get("approaches", [])]
    llm_scripts = {Path(p) for p in config.get("llm_scripts", [])}

    scene_types = config.get("scene_types", [])
    if not scene_types:
        logger.error(
            "`scene_types` is not defined or is empty in the config file. Aborting."
        )
        return

    num_runs_per_instruction = config.get("num_runs_per_instruction", 1)
    start_idx = config.get("start_idx", 0)
    max_workers = config.get("max_workers", 1)
    file_copy_lock = threading.Lock()

    # Log current configuration
    logger.info("Current configuration:")
    logger.info("-" * 40)
    logger.info(f"Log level: {config.get('log_level')}")
    logger.info(f"Scene types to run: {scene_types}")
    logger.info(f"Predefined mode: {config.get('predefined', False)}")
    logger.info(f"ROS enabled: {config.get('ros', False)}")
    logger.info(f"Simulation mode: {config.get('simulation', False)}")
    logger.info(f"Cloud Rendering: {config.get('cloud_rendering', False)}")
    logger.info(f"Max workers: {max_workers}")
    logger.info(f"Approaches: {[str(p) for p in approaches]}")
    logger.info(f"LLM scripts: {[str(p) for p in llm_scripts]}")
    logger.info(f"Runs per instruction: {num_runs_per_instruction}")
    logger.info(f"Max retries: {config.get('max_retries', 10)}")
    logger.info(f"Retry delay: {config.get('retry_delay_seconds', 2)} seconds")
    logger.info("-" * 40)

    execute_dict = config.get("execute_dict", {})

    for scene_type in scene_types:
        scene_list = config.get("scene_lists", {}).get(scene_type, [])
        if not scene_list:
            logger.warning(
                f"No scenes found for scene_type '{scene_type}' in config, skipping."
            )
            continue

        logger.info("=" * 80)
        logger.info(f"STARTING SCENE TYPE: {scene_type.upper()}")
        logger.info(f"Scenes: {scene_list}")
        logger.info("=" * 80)

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
                    if (
                        execute_dict
                        and execute_dict.get(scene_name)
                        and instruction not in execute_dict[scene_name]
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
                            llm_scripts,
                            start_idx,
                            file_copy_lock,
                        )
                    )

            # Wait for all futures in the current scene_type to complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"A task generated an exception: {e}")
                    logger.error(traceback.format_exc())

        logger.info("=" * 80)
        logger.info(f"COMPLETED SCENE TYPE: {scene_type.upper()}")
        logger.info("=" * 80)


def main() -> None:
    """스크립트의 메인 진입점. 설정을 로드하고 실행 스윕을 실행합니다."""
    config = load_config()

    # Initialize a global logger for the main script
    global logger
    logger = create_module_logger(
        module_name=__name__, module_log=True, level=config.get("log_level", "DEBUG")
    )

    sweep_config = config.get("sweep_parameters")
    if not sweep_config or not sweep_config.get("means"):
        # 스윕 설정이 없으면 단일 실행
        logger.info("No sweep parameters found in config, running a single experiment.")
        run_all_experiments(config)
        return

    # 파라미터 스윕 실행
    means = sweep_config["means"]
    gt_interval = sweep_config.get("gt_interval", 100.0)
    tag_template = sweep_config.get("tag_template", "prior_mean_{mean}")
    stop_on_error = sweep_config.get("stop_on_error", False)
    dry_run = sweep_config.get("dry_run", False)

    baseline_content = CONSTANTS_PATH.read_text(encoding="utf-8")
    original_log_path = constants.LOG_PATH
    original_result_path = constants.RESULT_PATH

    try:
        for mean in means:
            tag = None
            if tag_template:
                tag = tag_template.format(mean=_format_tag(mean))

            updated_content = prepare_constants(baseline_content, mean, gt_interval)
            CONSTANTS_PATH.write_text(updated_content, encoding="utf-8")
            ensure_directories(tag)

            if tag:
                constants.RESULT_PATH = REPO_ROOT / "assets" / "results" / tag
                constants.LOG_PATH = REPO_ROOT / "logs" / tag
            else:
                # 태그가 없으면 원래 경로 복원
                constants.RESULT_PATH = original_result_path
                constants.LOG_PATH = original_log_path

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"[{now}] INIT_PRIOR_MEAN={mean} GT_INTERVAL={gt_interval} tag={tag or 'default'}"
            )

            if dry_run:
                print(f"  dry-run: Would execute experiments with current settings.")
                continue

            try:
                run_all_experiments(config)
            except Exception as e:
                logger.error(f"Experiment failed for INIT_PRIOR_MEAN={mean}: {e}")
                logger.error(traceback.format_exc())
                if stop_on_error:
                    logger.error("Stopping sweep due to stop_on_error flag in config.")
                    raise

    finally:
        CONSTANTS_PATH.write_text(baseline_content, encoding="utf-8")
        constants.LOG_PATH = original_log_path
        constants.RESULT_PATH = original_result_path
        logger.info("Restored original constants.py and path variables.")


if __name__ == "__main__":
    main()
