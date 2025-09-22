import argparse
import json
import os
import os.path as osp
import random
import sys
import time
from pathlib import Path

import numpy as np
import openai
from ai2thor.controller import Controller
from ai2thor.platform import CloudRendering
from util.utils_execute import *

from src.simulation.runner_ai2thor import init_ai2thor_controller
from src.utils.common import create_module_logger
from src.utils.config.constants import *
from src.utils.io_utils.result_saver import result_save_llm
from src.utils.io_utils.task_io import list_task_files

current_dir = os.path.dirname(os.path.abspath(__file__))  # 이 파일의 현재 경로


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
        "--headless",
        action="store_true",
        help="Run in headless mode.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: DEBUG)",
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
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)",
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
    parser.add_argument(
        "--openai-api-key", type=str, default=os.getenv("OPENAI_API_KEY")
    )

    parser.add_argument("--prompt-task-examples", type=str, default="default")
    parser.add_argument("--instruction", type=str, default=None)
    parser.add_argument(
        "--log-path",
        type=str,
        default=None,
        help="Path to the log file for this specific run.",
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="The attempt number for the run.",
    )
    parser.add_argument(
        "--cloud-rendering",
        action="store_true",
        help="Use CloudRendering platform for AI2-THOR.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help="The path to save the results.",
    )
    return parser.parse_args()


def generate_plan(controller, task: str, args: argparse.Namespace, logger):
    # 현재 scene에 있는 object들을 가져옴
    # 이거 env json으로 해야하나 contoller로 하면 되나?
    obj = list(
        set(obj["objectType"] for obj in controller.step("Pass").metadata["objects"])
    )
    # ithor에서 할 수 있는 action들
    prompt = "from actions import walk <obj>, pickup <obj>, put <obj> <obj>, drop <obj>, open <obj>, close <obj>, toggleon <obj>, toggleoff <obj>, slice <obj>"
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
            "Heat Potato using Microwave and set the table for lunch",
            "use coffee machine to make coffee then pick up the apple",
            "Fill the bathtub with water",
            "wash tomato, potato and egg, and cook egg fry",
            "put tomato and apple in fridge and put book in shelf",
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
    print(f"Generating plan for: {task}\n")
    curr_prompt = (
        f"{prompt}\ntask : {task}\n"  ## 주어진 정보 + 수행할 task 이어서 prompt 만듦
    )
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
    plan_of_task_path = os.path.join(current_dir, f"result/plans_of_{task}.json")
    with open(plan_of_task_path, "w") as f:
        line[task] = text
        json.dump(line, f)

    computation_time = time.time() - computation_time_start

    prog_log_path = os.path.join(current_dir, f"result/prog_logs_{task}.txt")
    os.makedirs(os.path.dirname(prog_log_path), exist_ok=True)
    log_file = open(prog_log_path, "w", buffering=1)
    approach_name = "prog_ai2thor_simulation"
    result_path = f"{task}"

    simulate_execution(controller, [task], [text], log_file, args, logger)
    result_args = {
        "approach_name": approach_name,
        "user_input": task,
        "result": prog_log_path,
        "json_output_path": result_path,
        "computation_time": computation_time,
        "scene_name": args.scene,
        "attempt": args.attempt,
        "base_result_path": args.result_path,
    }
    result_save_llm(**result_args)


def planner_executer(args: argparse.Namespace, task: str, logger):
    scene_name = args.scene
    platform_obj = None
    if args.cloud_rendering:
        platform_obj = CloudRendering
    controller = init_ai2thor_controller(scene_name, platform=platform_obj)
    try:
        generate_plan(controller, task, args, logger)
    finally:
        controller.stop()


if __name__ == "__main__":
    args: argparse.Namespace = parse_arguments()
    logger = create_module_logger(
        module_name="prog_ai2thor",
        log_file_path=Path(args.log_path) if args.log_path else None,
        level=args.log_level,
    )

    instruction = args.instruction
    task = ""
    if instruction:
        try:
            choice = int(instruction)
            task_files = list_task_files(args.scene)
            if 1 <= choice <= len(task_files):
                task = Path(task_files[choice - 1]).stem
            else:
                print(
                    f"Error: Invalid number. Please choose a number between 1 and {len(task_files)}."
                )
                sys.exit(1)
        except ValueError:
            # It's a natural language instruction, not a number
            task = instruction.strip()
    else:
        print("명령어가 인자로 제공되지 않았습니다. 사용자 입력을 기다립니다...")
        task = input().strip()

    openai.api_key = args.openai_api_key

    planner_executer(args=args, task=task, logger=logger)
