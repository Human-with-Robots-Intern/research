import os
import json
import subprocess
import time
from datetime import datetime
from math import inf
from pathlib import Path

from src.utils.result_saver import result_save_llm
from src.utils.constants import SCENE_NAME


def run_with_retries(script, input_str, max_retries=10):
    """
    주어진 스크립트를 input_str을 인자로 실행하며, 실패 시 최대 max_retries번 재시도한다.
    
    Args:
        script (str): 실행할 스크립트의 경로.
        input_str (str): 스크립트에 전달할 입력 문자열.
        max_retries (int): 최대 재시도 횟수.
    
    Returns:
        tuple: (성공여부(bool), 시도 횟수(int))
    """
    for attempt in range(1, max_retries + 1):
        print(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(["python", script], input=input_str, text=True)
        if result.returncode == 0:
            return True, attempt
        elif attempt < max_retries:
            print(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 후 재시도
    return False, attempt


def process_retry_script(script, instruction):
    """
    재시도 대상 스크립트를 실행하고, 성공 여부에 따라 결과 JSON 파일을 저장한다.
    
    Args:
        script (str): 실행할 스크립트의 경로.
        instruction (str): 해당 태스크의 명령어 문자열.
    """
    approach = os.path.splitext(os.path.basename(script))[0]
    json_path = Path(f"assets/results/{instruction}/approach/{approach}_simulation.json")
    input_str = f"{instruction}\n"
    
    success, attempt = run_with_retries(script, input_str, max_retries=10)
    
    # 결과 파일 저장을 위한 상위 디렉토리 생성
    json_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 성공 시 실제 출력 데이터가 있다면 이를 활용할 수 있으나, 현재는 간단히 attempt 정보만 기록
    if success:
        data = {"attempt": attempt}
    else:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        data = {
            "saved_time": time_str,
            "approach": approach,
            "attempt": attempt,
            "scene_name": SCENE_NAME,
            "plans": [{"plan_name": instruction}],
            "computation_time": inf,
            "success_rate": 0,
            "scheduler_makespan": None,
            "simulation_makespan": inf,
            "realworld_makespan": None
        }
    
    with open(json_path, "w") as f:
        json.dump(data, f, indent=4)


def process_non_retry_script(script, iteration):
    """
    재시도 로직이 필요 없는 스크립트를 실행한다.
    
    Args:
        script (str): 실행할 스크립트의 경로.
        iteration (int): 입력 인자로 전달할 정수값.
    """
    print(f"Running {script}...")
    input_str = f"{iteration}\n"
    subprocess.run(["python", script], input=input_str, text=True)


def main():
    # 실행할 스크립트 목록
    scripts = [
        "src/baselines/progprompt/prog_ai2thor.py",
        "src/baselines/cap/cap_ai2thor.py",
        "src/dag_bayesian.py",
        "src/baselines/cpm.py",
        "src/baselines/edf/dag_edf.py"
    ]
    
    # 재시도 로직을 적용할 스크립트들
    retry_scripts = {
        "src/baselines/progprompt/prog_ai2thor.py",
        "src/baselines/cap/cap_ai2thor.py"
    }
    
    # 태스크별 명령어 (instruction)
    instructions = {
        1: "wash_egg_and_cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_cutlery_and_wash_dishes_and_wash_vegetables_and_organize_the_vegetables",
        2: "boil_potato_and_make_coffee_and_wash_lettuce_and_tomato_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel",
        3: "boil_potato_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_vegetables",
        4: "cook_egg_fry_and_make_coffee_and_heat_potato_using_microwave_and_wash_cutlery_and_wash_dishes",
        5: "boil_potato_and_wash_vegetables_and_put_creditcard_on_shelf_and_wash_dishes_and_wash_cutlery",
        6: "wash_egg_and_cook_egg_fry_and_wash_vegetables_and_wash_cutlery_and_wash_dishes_and_throw_away_paper_towel_and_put_creditcard_on_shelf",
        7: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_wash_cutlery_and_wash_dishes_and_throw_away_paper_towel_and_put_creditcard_on_shelf",
        8: "cook_egg_fry_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_vegetables_and_heat_bread_using_microwave_and_make_coffee",
        9: "cook_egg_fry_and_make_coffee_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_cutlery_and_wash_dishes_and_wash_vegetables_and_organize_the_vegetables",
        10: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_heat_potato_using_microwave_and_wash_vegetables_and_wash_cutlery_and_wash_dishes",
        11: "cook_egg_fry_and_heat_potato_in_microwave_and_wash_plates",
        12: "cook_egg_fry_and_throw_away_paper_towel_and_wash_vegetables",
        13: "boil_potato_and_brew_coffee",
        14: "heat_the_potato_and_make_coffee_and_wash_plates_and_put_book_on_shelf",
        15: "heat_bread_using_microwave_and_wash_tomato_and_potato_and_dispose_of_paper_towel",
        16: "wash_and_heat_potato_and_wash_cutlery_and_dispose_of_paper_towel",
        17: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee",
        18: "make_coffee_and_wash_vegetables_and_wash_cutlery",
        19: "boil_potato_and_make_coffee_and_wash_vegetables",
        20: "cook_egg_fry_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_vegetables",
        21: "prepare_vegetables_for_lunch_and_cook_egg_fry",
        22: "boil_potato_and_heat_bread_using_microwave_and_make_coffee",
        23: "make_coffee_and_wash_plates_and_store_tomato_in_fridge",
        24: "cook_egg_fry_and_wash_plates_and_put_creditcard_on_shelf",
        25: "prepare_fried_egg_and_prepare_coffee_and_set_the_table_for_lunch",
        26: "cook_egg_fry_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel",
        27: "heat_potato_using_microwave_and_wash_two_plates_and_place_book_on_shelf",
        28: "organize_the_vegetables_and_wash_dishes",
        29: "store_vegetables_and_book_dispose_of_paper_towel",
        30: "cook_egg_fry_and_make_coffee_and_wash_dishes"
    }
    
    num_runs_per_instruction = 1

    # i 값은 1부터 27까지 3씩 증가하는 범위를 역순으로 순회
    for i in reversed(range(1, 31, 3)):
        instruction = instructions[i]
        print(f"Task: {instruction}")
        for script in scripts:
            for _ in range(num_runs_per_instruction):
                if script in retry_scripts:
                    process_retry_script(script, instruction)
                else:
                    process_non_retry_script(script, i)


if __name__ == "__main__":
    main()
