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
from util.utils_execute import *


from ithor.utils.constants import *

current_dir = os.path.dirname(os.path.abspath(__file__)) # 이 파일의 현재 경로


def initialize_controller():

    controller = Controller(
        agentMode="default",  # "default", "locobot", "drone", or "arm",
        massThreshold=0.04,  # 물리 엔진에서 물체를 움직이는 최소 질량
        scene=SCENE_NAME,  # Scene 이름
        gridSize=GRID_SIZE,  # Move Actions의 Mean
        movementGaussianSigma=0.005,  # Move Actions의 Sigma
        renderDepthImage=False,  # Depth Image 렌더링 여부 (오랜 시간 소요)
        renderInstanceSegmentation=False,  # Instance Segmentation 렌더링 여부 (오랜 시간 소요)
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
        renderThirdPartyCameras=False,
        fieldOfView=60,
    )

    return controller


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

    test_tasks = [
        "Heat potato with Microwave. Wash a plate three times and cook fried egg"
    ]
    # "toast the bread and put tomato in the fridge. put egg in the pan."
    # "pick the egg"
    # "put the book in the sinkbasin"
    # "Heat potato with Microwave"
    # "Wash a plate three times"
    gen_plan = []
    for task in test_tasks:
        print(f"Generating plan for: {task}\n")
        curr_prompt = f"{prompt}\ntask : {task}\n"  ## 주어진 정보 + 수행할 task 이어서 prompt 만듦
        _, text = LM(
            curr_prompt,
            args.gpt_version,
            max_tokens=600,
            stop=["def"],
            frequency_penalty=0.15,
        )
        gen_plan.append(text)  # 답장온거 저장

        # save generated plan
        line = {}
        print(f"Saving generated plan at: {task}.json\n")
        plan_of_task_path = os.path.join(current_dir,f"result/plans_of_{task}.json")
        with open(plan_of_task_path, "w") as f:
            for plan, task in zip(gen_plan, test_tasks):
                line[task] = plan
            json.dump(line, f)
    prog_log_path = os.path.join(current_dir, f"result/prog_logs_{task}.txt")
    log_file = open(prog_log_path, "w", buffering=1)
    simulate_execution(controller, test_tasks, gen_plan, log_file, args)


def planner_executer(args):
    controller = initialize_controller()
    generate_plan(controller, args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser() 

    parser.add_argument(
        "--prompt-task-examples",
        type=str,
        default="default",
        choices=["default", "random"],
    )
    # for random task examples, choose seed
    parser.add_argument("--seed", type=int, default=0)

    ## NOTE: davinci or older GPT3 versions have a lower token length limit
    ## check token length limit for models to set prompt size:
    ## https://platform.openai.com/docs/models
    parser.add_argument(
        "--prompt-num-examples", type=int, default=4, choices=range(1, 5)
    )
    parser.add_argument(
        "--prompt-task-examples-ablation",
        type=str,
        default="none",
        choices=["none", "no_comments", "no_feedback", "no_comments_feedback"],
    )
    parser.add_argument("--openai-api-key", type=str, default="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")

    parser.add_argument(
        "--gpt-version",
        type=str,
        default="gpt-4o",
        choices=["gpt-4o", "gpt-4o-mini"],
    )
    parser.add_argument("--load-generated-plans", type=bool, default=False)

    
    args = parser.parse_args()
    openai.api_key = args.openai_api_key

    planner_executer(args=args)


