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
from utils.config.constants import RESULT_PATH

def parse_args():
    parser = argparse.ArgumentParser(description='Run all scripts with specified log level')
    parser.add_argument('--log-level', type=str, default='DEBUG',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    help='Set the logging level (default: DEBUG)')
    parser.add_argument('--predefined','-p', type=bool, default=False,
                    help='Use predefined numbered instructions (default: False)')
    parser.add_argument('--scene_type', type=str, default='bathroom',
                        choices=['kitchen', 'bathroom'],
                        help='Set the scene type to run (default: kitchen)')
    parser.add_argument('--capture-output', action='store_true',
                        help='Capture subprocess output instead of showing in terminal (default: False)')
    return parser.parse_args()

def run_with_retries(script: Path, input_str: str, scene_name: str, max_retries: int = 10, capture_output: bool = False) -> tuple[bool, int, str]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수, 결과 파일 경로), 실패하면 (False, 마지막 시도 횟수, None)를 반환합니다.
    """
    for attempt in range(1, max_retries + 1):
        logger.debug(f"Running {script} (Attempt {attempt})...")
        
        if capture_output:
            # 기존 방식: 출력 캡처
            result = subprocess.run(
                ["python", str(script), "--scene", scene_name, "--instruction", input_str],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # stdout에서 결과 파일 경로 파싱
                output_lines = result.stdout.strip().split('\n')
                result_path_line = [line for line in output_lines if line.startswith("result_path:")]
                if result_path_line:
                    result_path = result_path_line[0].split(":")[1].strip()
                    return True, attempt
                else:

                    return False, attempt
        else:
            # 새로운 방식: 실시간 출력 표시
            logger.info(f"=" * 80)
            logger.info(f"Starting {script} (Attempt {attempt}) with scene={scene_name}, instruction={input_str.strip()}")
            logger.info(f"=" * 80)
            
            result = subprocess.run(
                ["python", str(script), "--scene", scene_name, "--instruction", input_str],
                stdout=None,  # 부모 프로세스의 stdout 사용
                stderr=None,  # 부모 프로세스의 stderr 사용
                text=True
            )
            
            logger.info(f"=" * 80)
            logger.info(f"Finished {script} (Attempt {attempt}) with return code: {result.returncode}")
            logger.info(f"=" * 80)
            
            if result.returncode == 0:
                # 성공한 경우, 결과 파일 경로를 추정하거나 기본값 사용
                # 실제 구현에서는 스크립트가 파일을 저장하는 패턴에 따라 조정 필요

                return True, attempt

        if attempt < max_retries:
            logger.warning(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 시간 후 재시도
    
    return False, attempt, None  # 모든 시도 실패

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

def process_retry_script(script: Path, instruction: str, scene_name: str, capture_output: bool = False) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    approach = script.stem  # 파일명에서 확장자 제거
    input_str = f"{instruction}\n"

    success, attempt = run_with_retries(script, input_str, scene_name, max_retries=10, capture_output=capture_output)
    
    # 가장 높은 번호를 가진 instruction 폴더 찾기
    highest_instruction_folder = find_highest_instruction_folder(instruction)
    result_path = Path("assets") / "results" / highest_instruction_folder / scene_name / "approach" / f"{approach}_simulation.json"
    json_path = Path(result_path)
    
    if success:
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"JSON 파일 {json_path} 로드 실패: {e}")
            data = {}
        data["attempt"] = attempt
        # 수정된 데이터를 파일에 저장
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    else:
        # 실패 시 더미 데이터 생성
        json_path = Path("assets") / "results" / highest_instruction_folder / scene_name / "approach" / f"{approach}_simulation.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        data = {
            "saved_time": time_str,
            "approach": approach,
            "attempt": attempt,
            "scene_name": scene_name,
            "plans": [{"plan_name": instruction}],
            "computation_time": -1,  # inf 대신 -1 사용
            "success_rate": 0,
            "scheduler_makespan": None,
            "simulation_makespan": -1,  # inf 대신 -1 사용
            "realworld_makespan": None
        }
        # 더미 데이터를 파일에 저장
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def process_normal_script(script: Path, instruction: str, scene_name: str, capture_output: bool = False) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction이 1~30 사이의 숫자인 경우 첫 번째 입력 전송을 건너뜁니다.
    """
    logger.warning(f"Running {script},{scene_name},{instruction}...")
    
    if capture_output:
        # 기존 방식: 출력 캡처
        process = subprocess.Popen(
            ["python", str(script), "--scene", scene_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )
    else:
        # 새로운 방식: 실시간 출력 표시
        logger.info(f"=" * 80)
        logger.info(f"Starting {script} with scene={scene_name}, instruction={instruction}")
        logger.info(f"=" * 80)
        
        process = subprocess.Popen(
            ["python", str(script), "--scene", scene_name],
            stdin=subprocess.PIPE,
            stdout=None,  # 부모 프로세스의 stdout 사용
            stderr=None,  # 부모 프로세스의 stderr 사용
            text=True,
            bufsize=1  # Line buffered
        )
    
    # instruction이 1~30 사이의 숫자가 아닌 경우에만 첫 번째 입력 전송
    try:
        instruction_num = int(instruction)
        if not (1 <= instruction_num <= 30):
            process.stdin.write("0\n")
            process.stdin.flush()
            time.sleep(0.1)  # 입력 사이에 짧은 대기 시간 추가
    except ValueError:
        # instruction이 숫자가 아닌 경우 첫 번째 입력 전송
        process.stdin.write("0\n")
        process.stdin.flush()
        time.sleep(0.1)  # 입력 사이에 짧은 대기 시간 추가
    
    # 두 번째 입력 전송 (instruction)
    process.stdin.write(f"{instruction}\n")
    process.stdin.flush()
    
    # 프로세스 종료 대기
    process.wait()
    
    if not capture_output:
        logger.info(f"=" * 80)
        logger.info(f"Finished {script} with return code: {process.returncode}")
        logger.info(f"=" * 80)
    
    # 에러 코드 출력
    if process.returncode != 0:
        logger.error(f"Script {script} failed with error code: {process.returncode}")
        # stderr 내용도 출력 (capture_output이 True인 경우에만)
        if capture_output and process.stderr:
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.error(f"Error output: {stderr_output}")

def load_instructions_from_json(scene_name: str) -> list[str]:
    """
    주어진 scene에 대한 instruction을 JSON 파일에서 로드합니다.
    """
    number = int(scene_name.lstrip("FloorPlan"))
    if number >= 400:
        base_file = "bathroom_scene.json"
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
        logger.error(f"Failed to load scene-specific instructions from {scene_path}: {e}")
    
    return instructions

def main() -> None:
    args = parse_args()
    global logger
    logger = create_module_logger(module_name=__name__, module_log=True)
    logger.setLevel(args.log_level)

    approaches = [
        # Path("src/dag_bayesian.py"),
        # Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py"),
        # Path("src/baselines/edf/dag_edf.py"),
        # Path("src/baselines/cpm.py"),
    ]

    # 재시도 대상 (LLM 방식) 스크립트 집합
    llm_scripts = {
        Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py")
    }

    if args.scene_type == "kitchen":
        scene_list = [
            "FloorPlan1",
            "FloorPlan7",
            "FloorPlan13",
            "FloorPlan18",
            "FloorPlan27",
        ]
    else:  # bathroom
        scene_list = [
            "FloorPlan419",
            "FloorPlan422",
            "FloorPlan426",
            "FloorPlan427",
        ]
    num_runs_per_instruction = 1

    logger.info(f"Capture output mode: {args.capture_output}")
    if not args.capture_output:
        logger.info("Child process logs will be displayed in real-time in the terminal")
    else:
        logger.info("Child process outputs will be captured (original behavior)")

    # itertools.product를 사용하여 네 개의 반복 범위를 하나로 결합
    for scene_name, approach in product(scene_list, approaches):
        # Load instructions from JSON files
        instructions = load_instructions_from_json(scene_name)

        # predefine instruction을 사용하려면 활성화
        

        if args.predefined: 
            numbers = list(range(1, 21))           
            for instruction, i in product(numbers, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i+1}")
                if approach in llm_scripts:
                    process_retry_script(approach, str(instruction), scene_name, capture_output=args.capture_output)
                else:
                    process_normal_script(approach, str(instruction), scene_name, capture_output=args.capture_output)
        else:
            for instruction, i in product(instructions, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i+1}")
                if approach in llm_scripts:
                    process_retry_script(approach, instruction, scene_name, capture_output=args.capture_output)
                else:
                    process_normal_script(approach, instruction, scene_name, capture_output=args.capture_output)

if __name__ == "__main__":
    main()
