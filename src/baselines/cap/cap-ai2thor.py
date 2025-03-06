import os
import numpy as np
import time
import threading
import copy


# import for ai2thor
from ai2thor.controller import Controller

# setting.json 에 ai2thor 위치 환경변수 추가한 상태로 해야함.
from handlers.camera_handler import CameraHandler
from handlers.navigation_handler import NavigationHandler
from handlers.action import Action

from utils.constants import *
from utils.file_utils import *

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

import utils.LMPgen as gen


def initialize_controller(log_file):
    # initialize controller
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
    camera_handler = CameraHandler(controller)
    Navi = NavigationHandler(controller, camera_handler, log_file)
    Act = Action(controller, Navi, camera_handler, log_file)

    return controller, camera_handler, Navi, Act


## LMP Prompts
# 텍스트 파일 읽기
prompt_scene_ui_path = "cap/data/prompt_scene_ui.txt"
prompt_parse_obj_name_path = "cap/data/prompt_parse_obj_name.txt"
prompt_parse_question_path = "cap/data/prompt_parse_question.txt"
prompt_fgen_path = "cap/data/prompt_fgen.txt"


def read_txt(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return content  # 파일 내용을 출력
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")


prompt_scene_ui = read_txt(prompt_scene_ui_path).strip()
prompt_parse_obj_name = read_txt(prompt_parse_obj_name_path).strip()
prompt_parse_question = read_txt(prompt_parse_question_path).strip()
prompt_fgen = read_txt(prompt_fgen_path).strip()

## cfg 정의
cfg_scene = {
    "lmps": {
        "scene_ui": {
            "prompt_text": prompt_scene_ui,
            "engine": "gpt-4o",
            "max_tokens": 512,
            "temperature": 0,
            "query_prefix": "# ",
            "query_suffix": ".",
            "stop": ["#", "objects = ["],
            "maintain_session": True,
            "debug_mode": False,
            "include_context": True,
            "has_return": False,
            "return_val_name": "ret_val",
        },
        "parse_obj_name": {
            "prompt_text": prompt_parse_obj_name,
            "engine": "gpt-4o",
            "max_tokens": 512,
            "temperature": 0,
            "query_prefix": "# ",
            "query_suffix": ".",
            "stop": ["#", "objects = ["],
            "maintain_session": False,
            "debug_mode": False,
            "include_context": True,
            "has_return": True,
            "return_val_name": "ret_val",
        },
        "parse_question": {
            "prompt_text": prompt_parse_question,
            "engine": "gpt-4o",
            "max_tokens": 512,
            "temperature": 0,
            "query_prefix": "# ",
            "query_suffix": ".",
            "stop": ["#", "objects = ["],
            "maintain_session": False,
            "debug_mode": False,
            "include_context": True,
            "has_return": True,
            "return_val_name": "ret_val",
        },
        "fgen": {
            "prompt_text": prompt_fgen,
            "engine": "gpt-4o",
            "max_tokens": 512,
            "temperature": 0,
            "query_prefix": "# define function: ",
            "query_suffix": ".",
            "stop": ["# define", "# example"],
            "maintain_session": False,
            "debug_mode": False,
            "include_context": True,
        },
    }
}

vars_log = open("vars_log.txt", "w", buffering=1)


def setup_LMP(controller, Navi, Action, cfg_scene):
    # LMP env wrapper
    # 위에 있음.
    cfg_scene = copy.deepcopy(cfg_scene)
    # cfg_tabletop 에 "env":{} 생성
    cfg_scene["env"] = dict()
    # "env": {"init_objs": [env.obj_name_to_id.key()]}
    cfg_scene["env"]["init_objs"] = obj = list(
        set(obj["objectType"] for obj in controller.step("Pass").metadata["objects"])
    )
    # "env": {"init_objs": [env.obj_name_to_id.key()], "coords": {lmp_tabletop_coords}}
    # cfg_scene["env"]["coords"] = lmp_tabletop_coords
    # cfg_tabletop 에 "lmps" 와 "env" key가 있는거임
    LMP_env = gen.LMP_wrapper(controller, cfg_scene)

    # creating APIs that the LMPs can interact with
    fixed_vars = {"np": np}
    fixed_vars.update({"time": time})
    fixed_vars.update({"controller": Controller})

    for var_name, var_value in fixed_vars.items():
        vars_log.write(f"{var_name}: {var_value}\n")

    variable_vars = {k: getattr(Navi, k) for k in ["move_to"]}
    variable_vars.update(
        {
            k: getattr(Action, k)
            for k in [
                "pickup",
                "slice",
                "put",
                "drop",
                "toggleon",
                "toggleoff",
                "open",
                "close",
            ]
        }
    )
    variable_vars.update(
        {
            k: getattr(LMP_env, k)
            for k in [
                "is_obj_visible",
                "get_obj_names",
                "get_obj_id",
                "get_true_states",
                "get_ability_states",
                "get_parentReceptacles",
                "get_obj_in_hand",
            ]
        }
    )
    for var_name, var_value in variable_vars.items():
        vars_log.write(f"{var_name}: {var_value}\n")

    # 에다가 함수 추가
    variable_vars["say"] = lambda msg: print(f"robot says: {msg}")

    # creating the function-generating LMP
    lmp_fgen = gen.LMPFGen(cfg_scene["lmps"]["fgen"], fixed_vars, variable_vars)

    # creating other low-level LMPs
    # 함수: 속성 저장해놓는다고 생각하는게 편할듯. .update는 있으면 수정, 없으면 추가하는 dict 전용 함수
    variable_vars.update(
        {
            k: gen.LMP(k, cfg_scene["lmps"][k], lmp_fgen, fixed_vars, variable_vars)
            for k in [
                "parse_obj_name",
                "parse_question",
            ]
        }
    )

    # creating the LMP that deals w/ high-level language commands
    # 아 이래서 계층적이라고 한건가?
    lmp_scene_ui = gen.LMP(
        "scene_ui",
        cfg_scene["lmps"]["scene_ui"],
        lmp_fgen,
        fixed_vars,
        variable_vars,
    )

    return lmp_scene_ui


if __name__ == "__main__":
    user_input = (
        "Heat potato with microwave, wash a plate three times and cook fried egg"
    )

    log_file = open(f"cap/result/cap_logs_{user_input}.txt", "w", buffering=1)
    controller, camera_handler, Navi, Acttion = initialize_controller(log_file)

    lmp_scene_ui = setup_LMP(controller, Navi, Acttion, cfg_scene)
    # toast the bread
    # put tomato in the fridge
    # put egg in the pan : 냉장고 문을 안열고 계란 집음
    # put the book in the sinkbasin : put 상호작용이 불가능해서 던짐
    # toast the bread and put tomato in the fridge. put egg in the pan.
    # pick the apple and drop the apple

    objs = list(
        set(obj["objectType"] for obj in controller.step("Pass").metadata["objects"])
    )
    lmp_scene_ui(user_input, objects=f"{objs}")
