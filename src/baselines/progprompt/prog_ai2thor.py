import argparse
import json
import os
import os.path as osp
import random
import sys
import time

import numpy as np
import openai
from ai2thor.controller import Controller
from simulation.runner_ai2thor import init_ai2thor_controller
from util.utils_execute import *


from utils.config.constants import *
from utils.io_utils.result_saver import result_save_llm

current_dir = os.path.dirname(os.path.abspath(__file__)) # 이 파일의 현재 경로

def parse_arguments() -> argparse.Namespace:
    """
    명령행 인자를 파싱합니다.
    """
    parser = argparse.ArgumentParser(description="Task Scheduler")
    parser.add_argument(
        "-d",
        "--decomposition",
        default=True,
        action="store_true",
        help="태스크 분해 여부 (default: True)",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        default=True,
        action="store_true",
        help="시각화 실행 여부 (default: True)",
    )
    parser.add_argument(
        "-r",
        "--reset",
        default=True,
        action="store_true",
        help="리셋 실행 여부 (default: True)",
    )
    parser.add_argument(
        "-s",
        "--simulation",
        default=True,
        action="store_true",
        help="시뮬레이션 실행 여부 (default: True)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: DEBUG)"
    )
    parser.add_argument(
        "--gpt-version",
        type=str,
        default="gpt-4o",
        choices=["gpt-4o", "gpt-4o-mini"],
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        # 추후에 scene 목록이 생기면 choices = [] 으로 구현한다.
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)"
    )
    parser.add_argument(
        "--prompt-num-examples", type=int, default=4, choices=range(1, 5)
    )
    parser.add_argument(
        "--prompt-task-examples-ablation",
        type=str,
        default="none",
        choices=["none", "no_comments", "no_feedback", "no_comments_feedback"],
    )
    parser.add_argument("--openai-api-key", type=str, default=os.getenv("OPENAI_API_KEY"))
    
    parser.add_argument("--prompt-task-examples", type=str, default="default")
    return parser.parse_args()

def generate_plan(controller, args):
    # 현재 scene에 있는 object들을 가져옴
    obj = list(
        set(obj["objectType"] for obj in controller.step("Pass").metadata["objects"])
    )
    # ithor에서 할 수 있는 action들
    prompt = "from actions import walk <obj>, pickup <obj>, put <obj> <obj>, drop <obj>, open <obj>, close <obj>, toggleon <obj>, toggleoff <obj>, slice <obj>, fill <obj> <obj>"
    # 현재 scene에 있는 objects
    prompt += f"\nobjects(name) = {obj}\n\n"

    # 미리 만들어둔 plan 함수를 prompt 에 추가함.
    example_task_path = os.path.join(current_dir, "example_task.json")
    with open(example_task_path, "r") as f:
        tmp = json.load(f)
        prompt_egs = {}
        for k, v in tmp.items():
            prompt_egs[k] = v
    if args.prompt_task_examples == "default":
        default_examples = [
            "Wash_Tomato_and_Potato_and_egg_and_Cook_Egg_Fry",
            "Use_coffee_machine_to_make_coffee_then_pick_up_the_Apple",
            "make_me_a_toast_and_set_the_table_for_lunch",
            "put_tomato_and_apple_in_fridge_and_put_book_in_shelf",
        ]
        for i in range(args.prompt_num_examples):
            prompt += (
                "task : "
                + default_examples[i]
                + " \n"
                + prompt_egs[default_examples[i]]
                + "\n\n"
            )

    test_tasks = []
    # "toast the bread and put tomato in the fridge. put egg in the pan."
    # "pick the egg"
    # "put the book in the sinkbasin"
    # "Heat potato with Microwave"
    # "Wash a plate three times"
    gen_plan = []
    computation_time_start = time.time()

    # Read task from input
    task = input()
    print(f"Generating plan for: {task}\n")
    curr_prompt = f"{prompt}\ntask : {task}\n"  ## 주어진 정보 + 수행할 task 이어서 prompt 만듦
    _, text = LM(
        curr_prompt,
        args.gpt_version,
        max_tokens=600,
        stop=["def"],
        frequency_penalty=0.15,
    )
    # save generated plan
    line = {}
    print(f"Saving generated plan at: {task}.json\n")
    plan_of_task_path = os.path.join(current_dir,f"result/plans_of_{task}.json")
    with open(plan_of_task_path, "w") as f:
        line[task] = text
        json.dump(line, f)
            
    computation_time = time.time() - computation_time_start

    prog_log_path = os.path.join(current_dir, f"result/prog_logs_{task}.txt")
    os.makedirs(os.path.dirname(prog_log_path), exist_ok=True)
    log_file = open(prog_log_path, "w", buffering=1)
    approach_name = "prog_ai2thor_simulation"
    result_path = f"{task}"
    # simulate_execution 함수도 execute_subtask로 변경 가능한지 검토할 필요가 있다. 
    simulate_execution(controller, [task], [text], log_file, args)
    result_args={
        "approach_name": approach_name,
        "user_input": task,
        "result_txt":prog_log_path,
        "json_output_path":result_path,
        "computation_time":computation_time,
        "scene_name": args.scene,
    }
    result_save_llm(**result_args)



def planner_executer(args):
    scene_name = args.scene
    controller = init_ai2thor_controller(scene_name)
    generate_plan(controller, args)


if __name__ == "__main__":
    args: argparse.Namespace = parse_arguments()    

    openai.api_key = args.openai_api_key

    planner_executer(args=args)


