from datetime import datetime
import json
from math import inf
import subprocess
import time
from pathlib import Path
from itertools import product

from src.utils.config.constants import SCENE_NAME

def run_with_retries(script: Path, input_str: str, max_retries: int = 10) -> tuple[bool, int]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수), 실패하면 (False, 마지막 시도 횟수)를 반환합니다.
    """
    for attempt in range(1, max_retries + 1):
        print(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(
            ["python", str(script)],
            input=input_str,
            text=True
        )
        if result.returncode == 0:
            return True, attempt
        elif attempt < max_retries:
            print(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 시간 후 재시도
    return False, attempt  # 모든 시도 실패

def process_retry_script(script: Path, instruction: str) -> None:
    """
    재시도가 필요한 스크립트를 실행하고 결과 JSON 파일에 attempt 값을 기록하거나,
    모든 시도 실패 시 더미 데이터를 생성합니다.
    """
    approach = script.stem  # 파일명에서 확장자 제거
    json_path = Path("assets") / "results" / instruction / "approach" / f"{approach}_simulation.json"
    input_str = f"{instruction}\n"

    success, attempt = run_with_retries(script, input_str, max_retries=10)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    if success:
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[Error] JSON 파일 {json_path} 로드 실패: {e}")
            data = {}
        data["attempt"] = attempt
    else:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        default_data = {
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
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = default_data

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def process_normal_script(script: Path, instruction: str, index: int) -> None:
    """
    재시도 대상이 아닌 스크립트를 단순 실행합니다.
    """

    print(f"Running {script}...")
    input_str = f"{index}\n"
    subprocess.run(
        ["python", str(script)],
        input=input_str,
        text=True
    )

def main() -> None:
    scripts = [
        # Path("src/baselines/progprompt/prog_ai2thor.py"),
        # Path("src/baselines/cap/cap_ai2thor.py"),
        # Path("src/dag_bayesian.py"),
        Path("src/baselines/cpm.py"),
        Path("src/baselines/edf/dag_edf.py")
    ]

    # 재시도 대상 (LLM 방식) 스크립트 집합
    llm_scripts = {
        Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py")
    }

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
    scene_list = [
        "FloorPlan1",
        "FloorPlan2",
        "FloorPlan3",
        "FloorPlan4",
        "FloorPlan5",
        "FloorPlan401",
        "FloorPlan402",
        "FloorPlan403",
        "FloorPlan404",
        "FloorPlan405"
    ]
    # scene name 도 arg 로 받도록 파일들을 수정해야함. 
    num_runs_per_instruction = 1

    # itertools.product를 사용하여 세 개의 반복 범위를 하나로 결합
    for i, script, _ in product(range(1, 31), scripts, range(num_runs_per_instruction)):
        instruction = instructions[i]
        print(f"task_name : {instruction}")
        if script in llm_scripts:
            process_retry_script(script, instruction)
        else:
            process_normal_script(script, instruction, i)

if __name__ == "__main__":
    main()
