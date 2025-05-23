from datetime import datetime
import json
from math import inf
import subprocess
import time
from pathlib import Path
from itertools import product
import argparse

from src.utils.common import create_module_logger

def parse_args():
    parser = argparse.ArgumentParser(description='Run all scripts with specified log level')
    parser.add_argument('--log-level', type=str, default='WARNING',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    help='Set the logging level (default: WARNING)')
    parser.add_argument('--predefined', type=bool, default=False,
                    help='Use predefined numbered instructions (default: False)')
    return parser.parse_args()

def run_with_retries(script: Path, input_str: str, scene_name: str, max_retries: int = 10) -> tuple[bool, int]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수), 실패하면 (False, 마지막 시도 횟수)를 반환합니다.
    """
    for attempt in range(1, max_retries + 1):
        log.debug(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(
            ["python", str(script), "--scene", scene_name],
            input=input_str,
            text=True
        )
        if result.returncode == 0:
            return True, attempt
        elif attempt < max_retries:
            log.warning(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 시간 후 재시도
    return False, attempt  # 모든 시도 실패

def process_retry_script(script: Path, instruction: str, scene_name: str) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    approach = script.stem  # 파일명에서 확장자 제거
    json_path = Path("assets") / "results" / instruction / "approach" / f"{approach}_simulation.json"
    input_str = f"{instruction}\n"

    success, attempt = run_with_retries(script, input_str, scene_name, max_retries=10)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    if success:
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"JSON 파일 {json_path} 로드 실패: {e}")
            data = {}
        data["attempt"] = attempt
    else:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        default_data = {
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
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = default_data

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def process_normal_script(script: Path, instruction: str, scene_name: str) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    instruction이 1~30 사이의 숫자인 경우 첫 번째 입력 전송을 건너뜁니다.
    """
    log.warning(f"Running {script},{scene_name},{instruction}...")
    
    # 첫 번째 입력 (0)을 주고 프로세스 시작
    process = subprocess.Popen(
        ["python", str(script), "--scene", scene_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
    
    # 에러 코드 출력
    if process.returncode != 0:
        log.error(f"Script {script} failed with error code: {process.returncode}")
        # stderr 내용도 출력
        stderr_output = process.stderr.read()
        if stderr_output:
            log.error(f"Error output: {stderr_output}")

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
        log.error(f"Failed to load base instructions from {base_path}: {e}")
    
    # Load scene-specific instructions
    scene_path = Path("assets/tasks/nl_instructions") / f"{scene_name}.json"
    try:
        with scene_path.open("r", encoding="utf-8") as f:
            scene_data = json.load(f)
            instructions.extend(scene_data["instructions"])
    except Exception as e:
        log.error(f"Failed to load scene-specific instructions from {scene_path}: {e}")
    
    return instructions

def main() -> None:
    args = parse_args()
    global log
    log = create_module_logger(module_name=__name__, module_log=True)
    log.setLevel(args.log_level)

    approaches = [
        # Path("src/dag_bayesian.py"),
        # Path("src/baselines/progprompt/prog_ai2thor.py"),
        # Path("src/baselines/cap/cap_ai2thor.py"),   
        # Path("src/baselines/edf/dag_edf.py"),
        Path("src/baselines/cpm.py"),
    ]

    # 재시도 대상 (LLM 방식) 스크립트 집합
    llm_scripts = {
        Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py")
    }

    scene_list = [
        "FloorPlan1",
        # "FloorPlan7",
        # "FloorPlan13",
        # "FloorPlan18",
        # "FloorPlan27",
        # "FloorPlan401",
        # "FloorPlan419",
        # "FloorPlan422",
        # "FloorPlan426",
        # "FloorPlan427"
    ]
    num_runs_per_instruction = 1

    # itertools.product를 사용하여 네 개의 반복 범위를 하나로 결합
    for scene_name, approach in product(scene_list, approaches):
        # Load instructions from JSON files
        instructions = load_instructions_from_json(scene_name)

        # predefine instruction을 사용하려면 활성화
        

        if args.predefined: 
            numbers = list(range(1, 31))           
            for instruction, i in product(numbers, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i}")
                if approach in llm_scripts:
                    process_retry_script(approach, instruction, scene_name)
                else:
                    process_normal_script(approach, instruction, scene_name)
        else:
            for instruction, i in product(instructions, range(num_runs_per_instruction)):
                print(f"task_name : {instruction}")
                print(f"scene_name : {scene_name}, approach : {approach}, run_num : {i}")
                if approach in llm_scripts:
                    process_retry_script(approach, instruction, scene_name)
                else:
                    process_normal_script(approach, instruction, scene_name)

if __name__ == "__main__":
    main()
