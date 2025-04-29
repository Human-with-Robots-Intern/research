from datetime import datetime
import json
from math import inf
import subprocess
import time
from pathlib import Path
from itertools import product


def run_with_retries(script: Path, input_str: str, scene_name: str, max_retries: int = 10) -> tuple[bool, int]:
    """
    주어진 스크립트를 최대 max_retries 회까지 재시도하며 실행합니다.
    성공하면 (True, 시도 횟수), 실패하면 (False, 마지막 시도 횟수)를 반환합니다.
    """
    for attempt in range(1, max_retries + 1):
        print(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(
            ["python", str(script), "--scene", scene_name],
            input=input_str,
            text=True
        )
        if result.returncode == 0:
            return True, attempt
        elif attempt < max_retries:
            print(f"Retrying {script} after failure (Attempt {attempt})...")
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
    """
    print(f"Running {script}...")
    
    # 첫 번째 입력 (0)을 주고 프로세스 시작
    process = subprocess.Popen(
        ["python", str(script), "--scene", scene_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 첫 번째 입력 전송 (0)
    process.stdin.write("0\n")
    process.stdin.flush()
    
    # 두 번째 입력 전송 (instruction)
    process.stdin.write(f"{instruction}\n")
    process.stdin.flush()
    
    # 프로세스 종료 대기
    process.wait()
    
    # 에러 코드 출력
    if process.returncode != 0:
        print(f"Script {script} failed with error code: {process.returncode}")
        # stderr 내용도 출력
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"Error output: {stderr_output}")

def main() -> None:
    approaches = [
        # Path("src/dag_bayesian.py"),
        # Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py"),        
        # Path("src/baselines/cpm.py"),
        # Path("src/baselines/edf/dag_edf.py")
    ]

    # 재시도 대상 (LLM 방식) 스크립트 집합
    llm_scripts = {
        Path("src/baselines/progprompt/prog_ai2thor.py"),
        Path("src/baselines/cap/cap_ai2thor.py")
    }

    instructions = {
        1: "wash_egg_and_cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_fork_and_spoon_and_wash_dishes_and_wash_vegetables_and_organize_the_vegetables",
        2: "boil_potato_and_make_coffee_and_wash_lettuce_and_tomato_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel",
        3: "boil_potato_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_vegetables",
        4: "cook_egg_fry_and_make_coffee_and_heat_potato_using_microwave_and_wash_fork_and_spoon_and_wash_dishes",
        5: "boil_potato_and_wash_vegetables_and_put_creditcard_on_shelf_and_wash_dishes_and_wash_fork_and_spoon",
        6: "wash_egg_and_cook_egg_fry_and_wash_vegetables_and_wash_fork_and_spoon_and_wash_dishes_and_throw_away_paper_towel_and_put_creditcard_on_shelf",
        7: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_wash_fork_and_spoon_and_wash_dishes_and_throw_away_paper_towel_and_put_creditcard_on_shelf",
        8: "cook_egg_fry_and_wash_dishes_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_vegetables_and_heat_bread_using_microwave_and_make_coffee",
        9: "cook_egg_fry_and_make_coffee_and_put_creditcard_on_shelf_and_throw_away_paper_towel_and_wash_fork_and_spoon_and_wash_dishes_and_wash_vegetables_and_organize_the_vegetables",
        10: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee_and_heat_potato_using_microwave_and_wash_vegetables_and_wash_fork_and_spoon_and_wash_dishes",
        11: "cook_egg_fry_and_heat_potato_in_microwave_and_wash_plates",
        12: "cook_egg_fry_and_throw_away_paper_towel_and_wash_vegetables",
        13: "boil_potato_and_brew_coffee",
        14: "heat_the_potato_and_make_coffee_and_wash_plates_and_put_book_on_shelf",
        15: "heat_bread_using_microwave_and_wash_tomato_and_potato_and_dispose_of_paper_towel",
        16: "wash_and_heat_potato_and_wash_fork_and_spoon_and_dispose_of_paper_towel",
        17: "cook_egg_fry_and_heat_bread_using_microwave_and_make_coffee",
        18: "make_coffee_and_wash_vegetables_and_wash_fork_and_spoon",
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
    #나중엔 각 scene 별로 instruction 목록이 생길것이다. 
    kitchen_scene_instructions = [
    "heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and prepare_a_water_cup",
    # "heat_the_bread_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    # "make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    # "heat_the_bread_using_microwave and make_a_coffee and wash_apple_and_lettuce and set_the_table and put_saltshaker_on_the_table",
    # "heat_the_bread_using_microwave and make_a_coffee and put_apple_and_lettuce_in_fridge and set_the_table and put_saltshaker_on_the_table",
    # "boil_potato and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and prepare_a_water_cup",
    # "boil_potato and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    # "boil_potato and make_a_coffee and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table"
    # "cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    # "cook_egg and make_a_coffee and wash_apple_and_lettuce and set_the_table and put_saltshaker_on_the_table",
    # "cook_egg and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    # "cook_egg and heat_the_potato_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    # "fill_pot_with_water and make_a_coffee and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table",
    # "fill_pot_with_water and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and prepare_a_water_cup",# "cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon and set_the_table and put_saltshaker_on_the_table",
    # "fill_pot_with_water and heat_the_potato_using_microwave and wash_apple_and_lettuce and prepare_a_water_cup and put_saltshaker_on_the_table",
    # "fill_pot_with_water and heat_the_potato_using_microwave and put_apple_and_lettuce_in_fridge and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    # "boil_potato and cook_egg and heat_the_bread_using_microwave and wash_apple_and_lettuce and set_the_table",
    # "boil_potato and cook_egg and make_a_coffee and wash_all_fork_and_spoon and put_saltshaker_on_the_table",
    # "cook_egg and fill_pot_with_water and heat_the_bread_using_microwave and wash_apple_and_lettuce and wash_all_fork_and_spoon",
    ]
    bathroom_scene_instructions=[
    "wet_the_handtowel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    # "wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    # "wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    # "wet_the_towel_with_water and turn_on_the_candle and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    # "wet_the_handtowel_with_water and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    # "fill_bathtub_with_water_with_shower_head and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth and close_shower_curtain",
    # "fill_bathtub_with_water_with_shower_head and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and throw_away_cloth",
    # "fill_bathtub_with_water_with_shower_head and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth",
    # "fill_bathtub_with_water_with_shower_head and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light and throw_away_cloth",
    # "fill_bathtub_with_water_with_shower_head and wet_the_towel_with_water and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    # "clean_the_toilet and wet_the_handtowel_with_water and turn_on_the_candle and throw_away_cloth and close_shower_curtain",
    # "clean_the_toilet and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and close_shower_curtain",
    # "clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and throw_away_cloth and close_shower_curtain",
    # "clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and turn_on_the_light",
    # "clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_candle and close_shower_curtain"
    # "fill_bathtub_with_water_with_shower_head and clean_the_toilet and wet_the_handtowel_with_water and turn_on_the_candle and close_shower_curtain",
    # "fill_bathtub_with_water_with_shower_head and clean_the_toilet and wet_the_handtowel_with_water and place_toilet_paper_on_the_toilet_paper_holder and throw_away_cloth",
    # "fill_bathtub_with_water_with_shower_head and clean_the_toilet and wet_the_towel_with_water and place_toilet_paper_on_the_toilet_paper_holder and turn_on_the_light",
    # "fill_bathtub_with_water_with_shower_head and clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and close_shower_curtain",
    # "fill_bathtub_with_water_with_shower_head and clean_the_toilet and wet_the_towel_with_water and turn_on_the_light and throw_away_cloth"
    ]
    
    floorplane_1_instructions=[

    ]
    floorplan_7_instructions=[

    ]
    floorplan_13_instructions=[

    ]
    floorplan_18_instructions=[

    ]
    floorplan_27_instructions=[

    ]
    floorplan_401_instructions=[

    ]
    floorplan_415_instructions=[

    ]
    floorplan_422_instructions=[

    ]
    floorplan_426_instructions=[

    ]
    floorplan_427_instructions=[

    ]
    
    scene_list = [
        # "FloorPlan1",
        # "FloorPlan7",
        # "FloorPlan13",
        # "FloorPlan18",
        # "FloorPlan27",
        "FloorPlan401",
        # "FloorPlan415",
        # "FloorPlan422",
        # "FloorPlan426",
        # "FloorPlan427"
    ]
    num_runs_per_instruction = 2

    # itertools.product를 사용하여 네 개의 반복 범위를 하나로 결합
    for scene_name, approach, _, i in product(
                                            scene_list, 
                                            approaches, 
                                            range(num_runs_per_instruction),
                                            range(0, 1)
                                            ):
        number = int(scene_name.lstrip("FloorPlan"))
        if number >= 400:
            instruction = bathroom_scene_instructions[i]
        else:
            instruction = kitchen_scene_instructions[i]
        
        print(f"task_name : {instruction}, scene_name : {scene_name}")
        if approach in llm_scripts:
            process_retry_script(approach, instruction, scene_name)
        else:
            process_normal_script(approach, instruction, scene_name)

if __name__ == "__main__":
    main()
