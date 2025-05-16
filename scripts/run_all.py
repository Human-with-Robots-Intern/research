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

def main() -> None:
    args = parse_args()
    global log
    log = create_module_logger(module_name=__name__, module_log=True)
    log.setLevel(args.log_level)

    approaches = [
        # Path("src/dag_bayesian.py"),
        # Path("src/baselines/progprompt/prog_ai2thor.py"),
        # Path("src/baselines/cap/cap_ai2thor.py"),   
        Path("src/baselines/edf/dag_edf.py"),
        Path("src/baselines/cpm.py"),

    ]

    # 재시도 대상 (LLM 방식) 스크립트 집합
    llm_scripts = {
        Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py")
    }

    
    #나중엔 각 scene 별로 instruction 목록이 생길것이다. 
    kitchen_scene_instructions = [
    "heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and prepare_a_water_cup_with_mug",
    "heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    "make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    "heat_the_bread_using_microwave and make_a_coffee and wash_apple_and_lettuce and set_the_table and put_saltshaker_on_the_table",
    "heat_the_bread_using_microwave and make_a_coffee and put_apple_and_lettuce_in_fridge and set_the_table and put_saltshaker_on_the_table",
    "boil_potato and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and prepare_a_water_cup_with_mug",
    "boil_potato and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    "boil_potato and make_a_coffee and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table"
    "cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    "cook_egg and make_a_coffee and wash_apple_and_lettuce and set_the_table and put_saltshaker_on_the_table",
    "cook_egg and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    "cook_egg and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    "fill_pot_with_water and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    "fill_pot_with_water and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and prepare_a_water_cup_with_mug",# "cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    "fill_pot_with_water and heat_the_potato_using_microwave and wash_apple_and_lettuce and prepare_a_water_cup_with_mug and put_saltshaker_on_the_table",
    "fill_pot_with_water and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    "boil_potato and cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and set_the_table",
    "boil_potato and cook_egg and make_a_coffee and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    "cook_egg and fill_pot_with_water and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon",
    ]
    bathroom_scene_instructions=[
    "wet_the_handtowel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    "wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    "wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and close_shower_curtain",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth",
    "fill_bathtub_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth",
    "fill_bathtub_with_water and wet_the_towel_with_water and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    "clean_the_toilet and wet_the_handtowel_with_water and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    "clean_the_toilet and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and close_shower_curtain",
    "clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    "clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and turn_on_the_light",
    "clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and close_shower_curtain"
    "fill_bathtub_with_water and clean_the_toilet and wet_the_handtowel_with_water and turn_on_the_candle and close_shower_curtain",
    "fill_bathtub_with_water and clean_the_toilet and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth",
    "fill_bathtub_with_water and clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light",
    "fill_bathtub_with_water and clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and close_shower_curtain",
    "fill_bathtub_with_water and clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and throw_away_cloth"
    ]
    FloorPlan1_instructions=[
    "heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and throw_away_paper_towel_roll and put_the_wine_bottle_inside_a_cabinet",
    "make_a_coffee and throw_away_paper_towel_roll and put_the_creditcard_on_the_countertop and put_the_book_in_cabinet and set_the_table",
    "heat_the_bread_using_microwave and make_a_coffee and put_the_creditcard_on_the_countertop and put_the_book_in_cabinet and set_the_table",
    "make_a_coffee and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and put_the_creditcard_on_the_countertop and put_the_book_in_cabinet",
    "heat_the_potato_using_microwave and wash_all_fork_and_spoon and put_the_wine_bottle_inside_a_cabinet and put_the_creditcard_on_the_countertop and put_the_book_in_cabinet",
    "boil_water_with_kettle and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_the_book_in_cabinet",
    "boil_water_with_kettle and make_a_coffee and throw_away_paper_towel_roll and put_the_creditcard_on_the_countertop and put_the_book_in_cabinet",
    "boil_water_with_kettle and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and put_the_wine_bottle_inside_a_cabinet and put_the_creditcard_on_the_countertop",
    "cook_egg and heat_the_potato_using_microwave and prepare_a_water_cup_with_mug and throw_away_paper_towel_roll and put_the_book_in_cabinet",
    "boil_potato and make_a_coffee and wash_all_fork_and_spoon and put_the_wine_bottle_inside_a_cabinet and put_the_creditcard_on_the_countertop",
    "cook_egg and boil_water_with_kettle and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and throw_away_paper_towel_roll",
    "cook_egg and boil_water_with_kettle and heat_the_bread_using_microwave and put_the_wine_bottle_inside_a_cabinet and set_the_table",
    "boil_potato and boil_water_with_kettle and heat_the_bread_using_microwave and wash_apple_and_lettuce and put_the_book_in_cabinet",
    "boil_potato and boil_water_with_kettle and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and put_the_wine_bottle_inside_a_cabinet",
    "boil_potato and cook_egg and boil_water_with_kettle and put_the_book_in_cabinet and set_the_table",
    ]
    FloorPlan7_instructions=[

    "make_a_coffee and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_a_statue_on_the_table",
    "heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_the_wine_bottle_inside_a_cabinet and put_a_statue_on_the_table",
    "make_a_coffee and wash_apple_and_lettuce and set_the_table and put_the_wine_bottle_inside_a_cabinet and put_a_statue_on_the_table",
    "heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "heat_the_bread_using_microwave and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    "boil_water_with_kettle and heat_the_bread_using_microwave and wash_apple_and_lettuce and put_the_wine_bottle_inside_a_cabinet and put_a_statue_on_the_table",
    "boil_water_with_kettle and make_a_coffee and wash_apple_and_lettuce and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "boil_water_with_kettle and heat_the_potato_using_microwave and wash_apple_and_lettuce and put_the_wine_bottle_inside_a_cabinet and put_a_statue_on_the_table",
    "fill_pot_with_water and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and put_the_wine_bottle_inside_a_cabinet and put_a_statue_on_the_table",
    "cook_egg and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_a_statue_on_the_table",
    "boil_potato and boil_water_with_kettle and heat_the_bread_using_microwave and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "boil_potato and boil_water_with_kettle and heat_the_bread_using_microwave and wash_apple_and_lettuce and put_a_statue_on_the_table",
    "boil_potato and boil_water_with_kettle and make_a_coffee and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "cook_egg and boil_water_with_kettle and make_a_coffee and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "fill_pot_with_water and boil_water_with_kettle and heat_the_bread_using_microwave and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    ]
    FloorPlan13_instructions=[
    "heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and put_the_pencil_on_somewhere",
    "make_a_coffee and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and throw_away_paper_towel_roll",
    "heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_the_pencil_on_somewhere",
    "heat_the_bread_using_microwave and make_a_coffee and put_apple_and_lettuce_in_fridge and throw_away_paper_towel_roll and put_the_pencil_on_somewhere",
    "make_a_coffee and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_the_pencil_on_somewhere",
    "boil_potato and make_a_coffee and wash_all_fork_and_spoon and throw_away_paper_towel_roll and put_the_pencil_on_somewhere",
    "cook_egg and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_the_pencil_on_somewhere",
    "cook_egg and make_a_coffee and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and throw_away_paper_towel_roll",
    "fill_pot_with_water and heat_the_bread_using_microwave and wash_all_fork_and_spoon and throw_away_paper_towel_roll and put_the_pencil_on_somewhere",
    "fill_pot_with_water and make_a_coffee and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and throw_away_paper_towel_roll",
    "cook_egg and fill_pot_with_water and heat_the_bread_using_microwave and wash_all_fork_and_spoon and set_the_table",
    "boil_potato and cook_egg and make_a_coffee and put_apple_and_lettuce_in_fridge and throw_away_paper_towel_roll",
    "cook_egg and fill_pot_with_water and make_a_coffee and set_the_table and throw_away_paper_towel_roll",
    "cook_egg and fill_pot_with_water and make_a_coffee and wash_all_fork_and_spoon and throw_away_paper_towel_roll",
    "cook_egg and fill_pot_with_water and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and put_the_pencil_on_somewhere",
    ]
    FloorPlan18_instructions=[
    "heat_the_bread_using_microwave and wash_all_fork_and_spoon and set_the_table and throw_away_paper_towel_roll and roll_down_the_blinds",
    "make_a_coffee and put_apple_and_lettuce_in_fridge and set_the_table and throw_away_paper_towel_roll and put_salt_shaker_inside_the_safe",
    "make_a_coffee and put_apple_and_lettuce_in_fridge and set_the_table and throw_away_paper_towel_roll and roll_down_the_blinds",
    "heat_the_potato_using_microwave and wash_all_fork_and_spoon and set_the_table and throw_away_paper_towel_roll and put_salt_shaker_inside_the_safe",
    "make_a_coffee and heat_the_potato_using_microwave and set_the_table and throw_away_paper_towel_roll and roll_down_the_blinds",
    "boil_water_with_kettle and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and roll_down_the_blinds",
    "boil_water_with_kettle and make_a_coffee and put_apple_and_lettuce_in_fridge and throw_away_paper_towel_roll and roll_down_the_blinds",
    "boil_water_with_kettle and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_salt_shaker_inside_the_safe",
    "fill_pot_with_water and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and set_the_table and throw_away_paper_towel_roll",
    "cook_egg and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and throw_away_paper_towel_roll and put_salt_shaker_inside_the_safe",
    "boil_potato and boil_water_with_kettle and make_a_coffee and roll_down_the_blinds and put_salt_shaker_inside_the_safe",
    "boil_potato and boil_water_with_kettle and heat_the_bread_using_microwave and wash_all_fork_and_spoon and put_salt_shaker_inside_the_safe",
    "cook_egg and fill_pot_with_water and heat_the_bread_using_microwave and set_the_table and roll_down_the_blinds",
    "cook_egg and boil_water_with_kettle and heat_the_potato_using_microwave and throw_away_paper_towel_roll and put_salt_shaker_inside_the_safe",
    "boil_potato and cook_egg and boil_water_with_kettle and wash_all_fork_and_spoon and roll_down_the_blinds",
    ]
    FloorPlan27_instructions=[
    "heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and wash_two_ladles",
    "heat_the_bread_using_microwave and make_a_coffee and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and wash_two_ladles",
    "make_a_coffee and wash_apple_and_lettuce and set_the_table and wash_two_ladles and put_the_wine_bottle_inside_a_cabinet",
    "make_a_coffee and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and wash_two_ladles",
    "boil_potato and heat_the_bread_using_microwave and wash_all_fork_and_spoon and set_the_table and wash_two_ladles",
    "cook_egg and make_a_coffee and wash_all_fork_and_spoon and wash_two_ladles and put_the_wine_bottle_inside_a_cabinet",
    "fill_pot_with_water and make_a_coffee and set_the_table and wash_two_ladles and put_the_wine_bottle_inside_a_cabinet",
    "fill_pot_with_water and make_a_coffee and wash_apple_and_lettuce and wash_two_ladles and put_the_wine_bottle_inside_a_cabinet",
    "cook_egg and make_a_coffee and wash_all_fork_and_spoon and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "boil_potato and cook_egg and heat_the_bread_using_microwave and set_the_table and put_the_wine_bottle_inside_a_cabinet",
    "boil_potato and cook_egg and heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_two_ladles",
    "cook_egg and fill_pot_with_water and make_a_coffee and set_the_table and wash_two_ladles",
    "cook_egg and fill_pot_with_water and heat_the_potato_using_microwave and wash_apple_and_lettuce and set_the_table",
    "cook_egg and fill_pot_with_water and heat_the_potato_using_microwave and wash_two_ladles and put_the_wine_bottle_inside_a_cabinet"
    ]
    FloorPlan401_instructions=[
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and put_soap_bar_on_a_side_table",
    "wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and close_shower_curtain and put_soap_bar_on_a_side_table",
    "wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and close_shower_curtain and put_soap_bar_on_a_side_table",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and put_soap_bar_on_a_side_table",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and throw_away_cloth and close_shower_curtain and put_soap_bar_on_a_side_table",
    "fill_bathtub_with_water and wet_the_towel_with_water and turn_on_the_candle and throw_away_cloth and put_soap_bar_on_a_side_table",
    "clean_the_sink_with_dish_sponge and wet_the_handtowel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_cloth",
    "clean_the_sink_with_dish_sponge and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    "clean_the_sink_with_dish_sponge and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and put_soap_bar_on_a_side_table",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_candle and throw_away_cloth",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and close_shower_curtain and put_soap_bar_on_a_side_table",
    "fill_bathtub_with_water and clean_the_sink_with_dish_sponge and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_soap_bar_on_a_side_table",
    "clean_the_toilet_with_scrub_brush and clean_the_sink_with_dish_sponge and wet_the_towel_with_water and close_shower_curtain and put_soap_bar_on_a_side_table",
    "clean_the_toilet_with_scrub_brush and clean_the_sink_with_dish_sponge and wet_the_towel_with_water and throw_away_cloth and put_soap_bar_on_a_side_table",
    ]
    FloorPlan419_instructions=[
    "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth and put_tissue_box_inside_the_drawer",
    "wet_the_handtowel_with_water and turn_on_the_light and throw_away_cloth and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and put_tissue_box_inside_the_drawer",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and close_shower_curtain",
    "fill_bathtub_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and put_tissue_box_inside_the_drawer",
    "clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_candle and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and put_tissue_box_inside_the_drawer",
    "clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and close_shower_curtain",
    "clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and turn_on_the_candle and throw_away_cloth and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_light and close_shower_curtain",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_candle and close_shower_curtain",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and turn_on_the_candle and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_tissue_box_inside_the_drawer"
    ]
    FloorPlan422_instructions=[
    "wet_the_handtowel_with_water and turn_on_the_candle and turn_on_the_light and put_soap_bar_in_a_cabinet and put_tissue_box_inside_the_drawer",
    "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth and put_soap_bar_in_a_cabinet",
    "wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and put_soap_bar_in_a_cabinet and throw_away_empty_toilet_paper_on_the_counter_top",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_empty_toilet_paper_on_the_counter_top",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and put_soap_bar_in_a_cabinet",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and turn_on_the_light and put_tissue_box_inside_the_drawer and throw_away_empty_toilet_paper_on_the_counter_top",
    "fill_bathtub_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and turn_on_the_light",
    "clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_light and close_shower_curtain and put_soap_bar_in_a_cabinet",
    "clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and throw_away_cloth and close_shower_curtain and throw_away_empty_toilet_paper_on_the_counter_top",
    "clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and put_soap_bar_in_a_cabinet and put_tissue_box_inside_the_drawer and throw_away_empty_toilet_paper_on_the_counter_top",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and throw_away_cloth and close_shower_curtain",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and turn_on_the_light and put_soap_bar_in_a_cabinet",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_light and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_empty_toilet_paper_on_the_counter_top",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and close_shower_curtain and put_soap_bar_in_a_cabinet",
    ]
    FloorPlan426_instructions=[
    "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and close_shower_curtain and throw_away_empty_toilet_paper_on_the_counter_top",
    "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_soap_bar_in_a_cabinet and put_tissue_box_inside_the_drawer and throw_away_empty_toilet_paper_on_the_counter_top",
    "wet_the_towel_with_water and turn_on_the_light and throw_away_cloth and close_shower_curtain and put_soap_bar_in_a_cabinet",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and turn_on_the_light and close_shower_curtain and throw_away_empty_toilet_paper_on_the_counter_top",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and turn_on_the_light and throw_away_cloth and put_soap_bar_in_a_cabinet"
    "fill_bathtub_with_water and wet_the_towel_with_water and throw_away_cloth and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_empty_toilet_paper_on_the_counter_top",
    "clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and throw_away_cloth and put_soap_bar_in_a_cabinet and put_tissue_box_inside_the_drawer",
    "clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and close_shower_curtain and put_tissue_box_inside_the_drawer",
    "clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and put_tissue_box_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and turn_on_the_light and throw_away_empty_toilet_paper_on_the_counter_top",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and turn_on_the_candle and throw_away_cloth",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and turn_on_the_candle and throw_away_empty_toilet_paper_on_the_counter_top",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and close_shower_curtain",
    ]
    FloorPlan427_instructions=[
    "wet_the_handtowel_with_water and throw_away_cloth and close_shower_curtain and put_a_soap_bar_on_the_sink and put_the_candle_inside_the_drawer",
    "wet_the_handtowel_with_water and turn_on_the_light and throw_away_cloth and put_tissue_box_inside_a_drawer and put_a_soap_bar_on_the_sink",
    "wet_the_towel_with_water and turn_on_the_light and throw_away_cloth and put_a_soap_bar_on_the_sink and put_the_candle_inside_the_drawer",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_a_soap_bar_on_the_sink and put_the_candle_inside_the_drawer",
    "wet_the_handtowel_with_water and wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and put_the_candle_inside_the_drawer",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and close_shower_curtain and put_a_soap_bar_on_the_sink",
    "fill_bathtub_with_water and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and close_shower_curtain",
    "clean_the_sink_with_dish_sponge and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and close_shower_curtain",
    "clean_the_sink_with_dish_sponge and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_tissue_box_inside_a_drawer and put_the_candle_inside_the_drawer",
    "clean_the_sink_with_dish_sponge and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_tissue_box_inside_a_drawer",
    "fill_bathtub_with_water and clean_the_toilet_with_scrub_brush and wet_the_towel_with_water and put_tissue_box_inside_a_drawer and put_the_candle_inside_the_drawer",
    "fill_bathtub_with_water and clean_the_sink_with_dish_sponge and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and put_a_soap_bar_on_the_sink",
    "fill_bathtub_with_water and clean_the_sink_with_dish_sponge and wet_the_towel_with_water and turn_on_the_light and put_a_soap_bar_on_the_sink",
    "clean_the_toilet_with_scrub_brush and clean_the_sink_with_dish_sponge and wet_the_handtowel_with_water and close_shower_curtain and put_tissue_box_inside_a_drawer",
    ]
    
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

        number = int(scene_name.lstrip("FloorPlan"))
        if number >= 400:
            common_instructions = bathroom_scene_instructions
        else:
            common_instructions = kitchen_scene_instructions
        
        # Get scene-specific instructions using globals()
        scene_specific_instructions = globals().get(f"{scene_name}_instructions", [])
        
        # Combine base instructions with scene-specific instructions
        instructions = common_instructions + scene_specific_instructions

        # predefine instruction을 사용하려면  활성화
        numbers = list(range(1, 31))

        if numbers:            
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
