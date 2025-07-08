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

from src.utils.common import create_module_logger
from src.utils.config.constants import RESULT_PATH

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
        
        cmd = [str(wrapper_script), "python3", str(script), "--scene", scene_name, "--instruction", input_str]
        if config.get("ros"):
            cmd.append("--ros")
        if config.get("simulation"):
            cmd.append("--simulation")
            
        stdout_dest = subprocess.PIPE if config.get('capture_output') else None
        stderr_dest = subprocess.PIPE if config.get('capture_output') else None
        
        result = subprocess.run(
            cmd,
            stdout=stdout_dest,
            stderr=stderr_dest,
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

def process_retry_script(script: Path, instruction: str, scene_name: str, config: dict) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    approach = script.stem
    input_str = f"{instruction}\n"

    max_retries = config.get("max_retries", 10)
    success, attempt = run_with_retries(script, input_str, scene_name, config, max_retries=max_retries)
    
    highest_instruction_folder = find_highest_instruction_folder(instruction)
    result_path = RESULT_PATH / highest_instruction_folder / scene_name / "approach" / f"{approach}_simulation.json"
    
    if success:
        try:
            with result_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"JSON 파일 {result_path} 로드 실패: {e}")
            data = {}
        data["attempt"] = attempt
        with result_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    else:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        data = {
            "saved_time": time_str,
            "approach": approach,
            "attempt": attempt,
            "scene_name": scene_name,
            "plans": [{"plan_name": instruction}],
            "computation_time": -1,
            "success_rate": 0,
            "scheduler_makespan": None,
            "simulation_makespan": -1,
            "realworld_makespan": None
        }
        with result_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def process_normal_script(script: Path, instruction: str, scene_name: str, config: dict) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction이 1~30 사이의 숫자인 경우 첫 번째 입력 전송을 건너뜁니다.
    """
    wrapper_script = Path(__file__).parent / "run_with_ros_env.sh"
    logger.warning(f"Running {script},{scene_name},{instruction}...")
    
    logger.info(f"=" * 80)
    logger.info(f"Starting {script} with scene={scene_name}, instruction={instruction}")
    logger.info(f"=" * 80)
    
    cmd = [str(wrapper_script), "python3", str(script), "--scene", scene_name]
    if config.get("ros"):
        cmd.append("--ros")
    if config.get("simulation"):
        cmd.append("--simulation")
    
    capture_output = config.get('capture_output', False)
    stdout_dest = subprocess.PIPE if capture_output else None
    stderr_dest = subprocess.PIPE if capture_output else None

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=stdout_dest,
        stderr=stderr_dest,
        text=True,
        bufsize=1
    )
    
    try:
        instruction_num = int(instruction)
        if not (1 <= instruction_num <= 30):
            process.stdin.write("0\n")
            process.stdin.flush()
            time.sleep(0.1)
    except ValueError:
        process.stdin.write("0\n")
        process.stdin.flush()
        time.sleep(0.1)
    
    process.stdin.write(f"{instruction}\n")
    process.stdin.flush()
    
    stderr_output = None
    if capture_output:
        # We can safely call communicate and get output.
        _, stderr_output = process.communicate()
    else:
        # We should just wait for it to complete.
        process.wait()

    if not capture_output:
        logger.info(f"=" * 80)
        logger.info(f"Finished {script} with return code: {process.returncode}")
        logger.info(f"=" * 80)
    
    if process.returncode != 0:
        logger.error(f"Script {script} failed with error code: {process.returncode}")
        if capture_output and stderr_output:
            logger.error(f"Error output: {stderr_output}")

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
    global logger
    logger = create_module_logger(module_name=__name__, module_log=True)
    logger.setLevel(config.get("log_level", "DEBUG"))

    approaches = [Path(p) for p in config.get("approaches", [])]
    llm_scripts = {Path(p) for p in config.get("llm_scripts", [])}

    scene_type = config.get("scene_type", "kitchen")
    scene_list = config.get("scene_lists", {}).get(scene_type, [])
    
    num_runs_per_instruction = config.get("num_runs_per_instruction", 1)

    logger.info(f"Capture output mode: {config.get('capture_output')}")
    if not config.get('capture_output'):
        logger.info("Child process logs will be displayed in real-time in the terminal")
    else:
        logger.info("Child process outputs will be captured (original behavior)")

    for scene_name, approach in product(scene_list, approaches):
        instructions = load_instructions_from_json(scene_name)
        
        if config.get("predefined"): 
            numbers = list(range(1, 21))           
            for instruction, i in product(numbers, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i+1}")
                if approach in llm_scripts:
                    process_retry_script(approach, str(instruction), scene_name, config)
                else:
                    process_normal_script(approach, str(instruction), scene_name, config)
        else:
            for instruction, i in product(instructions, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i+1}")
                if approach in llm_scripts:
                    process_retry_script(approach, instruction, scene_name, config)
                else:
                    process_normal_script(approach, instruction, scene_name, config)

if __name__ == "__main__":
    main()
