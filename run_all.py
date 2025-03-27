# run_all.py
from datetime import datetime
import json
from math import inf
import os
import subprocess
import time
from src.utils.result_saver import result_save_llm
from src.utils.constants import SCENE_NAME
from pathlib import Path

def run_with_retries(script, input_str, max_retries=10):
    for attempt in range(1, max_retries + 1):
        print(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(
            ["python", script],
            input = input_str,
            text=True
            )
        if result.returncode == 0:
            return True, attempt
        elif attempt < max_retries:
            print(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 시간 후 재시도
           
    return False, attempt  # 모든 시도 실패

scripts = [
    "src/baselines/progprompt/prog_ai2thor.py",
    "src/baselines/cap/cap_ai2thor.py",
    "src/dag_bayesian.py",
    "src/baselines/cpm.py",
    "src/baselines/edf/dag_edf.py"
]

# 재시도 대상 스크립트들
retry_scripts = {
    "src/baselines/progprompt/prog_ai2thor.py",
    "src/baselines/cap/cap_ai2thor.py"
}

instructions ={
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
num_runs_per_instruction =1
for i in reversed(range(1,28,3)):
    for script in scripts:
        for j in range(num_runs_per_instruction):
            print(f"task_name : {instructions[i]}")
            filename = os.path.basename(script) 
            approach = os.path.splitext(filename)[0]  
            

            if script in retry_scripts:
                json_path = Path(f"assets/results/{instructions[i]}/approach/{approach}_simulation.json")
                input_str = f"{instructions[i]}\n"
                success, attempt = run_with_retries(script,input_str, max_retries=10)
                json_path.parent.mkdir(parents=True, exist_ok=True)                

                
                
                   

                if success==True:                    
                    data["attempt"]= attempt
                # 모든 시도 실패시 더미데이터 생성
                else:
                    now = datetime.now()
                    time_str = now.strftime("%Y-%m-%d %H:%M")

                    default_data = {
                        "saved_time": time_str,
                        "approach": approach,
                        "attempt": attempt,
                        "scene_name": SCENE_NAME,
                        "plans": [{"plan_name": instructions[i]}],
                        "computation_time": inf,
                        "success_rate": 0,
                        "scheduler_makespan": None,
                        "simulation_makespan": inf,
                        "realworld_makespan": None
                    }
                    data = default_data                  

                  
                with open(json_path, "w") as f:
                    json.dump(data, f, indent=4)

            else:
                print(f"Running {script}...")
                input_str=f"{i}\n"
                result = subprocess.run(
                    ["python", script],
                    input=input_str,
                    text= True
                    )
        
            
            
   
