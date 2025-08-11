import yaml
from datetime import datetime
import json
from math import inf
import subprocess
import time
from pathlib import Path
from itertools import product
import argparse
import sys
import re
import shutil
import concurrent.futures
import threading

from src.utils.common import create_module_logger
from src.utils.config.constants import RESULT_PATH, LOG_PATH
from src.utils.io_utils.task_io import list_task_files


def load_config() -> dict:
    """Loads configuration from scripts/config.yaml."""
    config_path = Path(__file__).parent / "run_all_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config

def run_with_retries(script: Path, input_str: str, scene_name: str, config: dict, max_retries: int = 10) -> tuple[bool, int]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수), 실패하면 (False, 마지막 시도 횟수)를 반환합니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    for attempt in range(1, max_retries + 1):
        logger.debug(f"Running {script} (Attempt {attempt})...")
        
        logger.info(f"=" * 80)
        logger.info(f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}")
        logger.info(f"=" * 80)
        
        cmd = [str(wrapper_script), "python3", str(script), "--scene", scene_name, "--reset", "--instruction", input_str]
        if config.get("ros"):
            cmd.append("--ros")
        if config.get("simulation"):
            cmd.append("--simulation")
        if config.get("log_level"):
            cmd.extend(["--log-level", config["log_level"]])
        
        result = subprocess.run(
            cmd,
            stdout=None,
            stderr=None,
            text=True
        )
        
        logger.info(f"=" * 80)
        logger.info(f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}")
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
        numbers = re.findall(r'\d+$', folder_name)
        if numbers:
            num = int(numbers[0])
            if num > highest_num:
                highest_num = num
                best_folder = folder_name
    
    return best_folder

def process_retry_script(script: Path, instruction: str, scene_name: str, config: dict, log_path: Path) -> None:
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
        
        logger.info(f"=" * 80)
        logger.info(f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}")
        logger.info(f"=" * 80)
        
        cmd = [str(wrapper_script), "python3", str(script), "--scene", scene_name, "--reset", "--instruction", input_str]
        if config.get("ros"):
            cmd.append("--ros")
        if config.get("simulation"):
            cmd.append("--simulation")
        if config.get("log_level"):
            cmd.extend(["--log-level", config["log_level"]])
        if log_path:
            cmd.extend(["--log-path", str(log_path)])
        cmd.extend(["--attempt", str(attempt)])
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        logger.info(f"=" * 80)
        logger.info(f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}")
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
            logger.info(f"Instruction '{instruction}' resolved to task name: '{task_name_for_result_folder}'")
        else:
            logger.warning(f"Instruction number {choice} is out of range for scene {scene_name}. Using the number itself as the task name.")
    except (ValueError, TypeError):
        pass  # Not a numeric instruction, use as is.
        

    highest_instruction_folder = find_highest_instruction_folder(task_name_for_result_folder)
    result_path = RESULT_PATH / highest_instruction_folder / scene_name / "approach" / f"{approach}_simulation.json"
    
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
        "realworld_makespan": None
    }
    with result_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def process_normal_script(script: Path, instruction: str, scene_name: str, config: dict, log_path: Path) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction을 command-line 인자로 전달합니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    logger.warning(f"Running {script},{scene_name},{instruction}...")

    logger.info(f"=" * 80)
    logger.info(f"Starting {script} with scene={scene_name}, instruction={instruction}")
    logger.info(f"=" * 80)
            
    logger.info(f"=" * 80)
    # logger.info(f"Waiting 1 minute before running instruction")
    # time.sleep(30)
    logger.info(f"30 seconds left before running instruction")
    time.sleep(20)
    logger.info(f"10 seconds left before running instruction")
    time.sleep(7)
    logger.info(f"3 seconds left before running instruction")
    time.sleep(3)
    logger.info(f"Start!")
    logger.info(f"=" * 80)

    cmd = [
        str(wrapper_script),
        "python3",
        str(script),
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
    if config.get("log_level"):
        cmd.extend(["--log-level", config["log_level"]])
    if log_path:
        cmd.extend(["--log-path", str(log_path)])


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
) -> None:
    """
    단일 instruction 실행을 위한 작업자 함수.
    """
    # Create a unique log file path for this worker
    log_file_name = f"{scene_name}_{Path(approach).stem}_{instruction}_{run_idx + 1}.log"
    log_file_path = LOG_PATH / "worker_logs" / log_file_name
    log_file_path.parent.mkdir(parents=True, exist_ok=True)


    if config.get("predefined"):
        if isinstance(instruction, int) and instruction < start_idx:
            return

        with file_copy_lock:
            object_mapping = (
                Path(__file__).parent.parent
                / "src/ros/ttp_ws/data/object_mapping.json"
            )
            object_positions = (
                Path(__file__).parent.parent
                / "src/ros/ttp_ws/data/object_positions.json"
            )
            if object_mapping.exists():
                shutil.copy2(object_mapping, object_positions)
                logger.info(f"Initialized {object_positions} for instruction {instruction}")
            else:
                logger.warning(f"Source file {object_mapping} does not exist")
    
    logger.info(f"task_name : {instruction}")
    logger.info(f"scene_name : {scene_name}, approach : {approach}, run_num : {run_idx+1}")

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
        logger.warning(f"Failed to load scene-specific instructions from {scene_path}: {e}")
    
    return instructions

def main() -> None:
    config = load_config()
    
    # Initialize a global logger for the main script
    global logger
    logger = create_module_logger(
        module_name=__name__,
        module_log=True,
        level=config.get("log_level", "DEBUG")
    )

    approaches = [Path(p) for p in config.get("approaches", [])]
    llm_scripts = {Path(p) for p in config.get("llm_scripts", [])}

    scene_type = config.get("scene_type", "kitchen")
    scene_list = config.get("scene_lists", {}).get(scene_type, [])
    
    num_runs_per_instruction = config.get("num_runs_per_instruction", 1)
    start_idx = config.get("start_idx", 0)
    max_workers = config.get("max_workers", 1)
    file_copy_lock = threading.Lock()
    
    # Log current  configuration
    logger.info("Current configuration:")
    logger.info("-" * 40)
    logger.info(f"Log level: {config.get('log_level')}")
    # logger.info(f"Scene type: {scene_type}")
    # logger.info(f"Scenes to run: {scene_list}")
    logger.info(f"Predefined mode: {config.get('predefined', False)}")
    logger.info(f"ROS enabled: {config.get('ros', False)}")
    logger.info(f"Simulation mode: {config.get('simulation', False)}")
    logger.info(f"Max workers: {max_workers}")
    # logger.info(f"Approaches: {[str(p) for p in approaches]}")
    # logger.info(f"LLM scripts: {[str(p) for p in llm_scripts]}")
    # logger.info(f"Runs per instruction: {num_runs_per_instruction}")
    # logger.info(f"Max retries: {config.get('max_retries', 10)}")
    # logger.info(f"Retry delay: {config.get('retry_delay_seconds', 2)} seconds")
    logger.info("-" * 40)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for scene_name, approach in product(scene_list, approaches):
            instructions = load_instructions_from_json(scene_name)
            instruction_source: list[str] | list[int]
            if config.get("predefined"): 
                instruction_source = list(range(1, len(instructions) + 1))
            else:
                instruction_source = instructions

            for instruction, i in product(instruction_source, range(num_runs_per_instruction)):
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


        import traceback
        print("futures: ", futures)
        for future in concurrent.futures.as_completed(futures):
            print("future", future)
            try:
                future.result()
            except Exception as e:
                logger.error(f"A task generated an exception: {e}")
                logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
