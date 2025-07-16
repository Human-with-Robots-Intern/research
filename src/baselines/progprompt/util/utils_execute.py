import math
import os
import random
import re
import sys
import time

import numpy as np
from ai2thor.controller import Controller
from openai import OpenAI

from src.utils.common import create_module_logger

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
)
from dotenv import load_dotenv

from ithor.handlers.action import Action
from ithor.handlers.arm_handler import ArmHandler
from ithor.handlers.camera_handler import CameraHandler
from ithor.handlers.interaction_handler import InteractionHandler
from ithor.handlers.move_handler import MoveHandler
from ithor.handlers.navigation_handler import NavigationHandler

load_dotenv()
logger = create_module_logger(__name__, module_log=True)
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY not found in environment variables.")
    raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")

client = OpenAI(api_key=openai_api_key)


def LM(
    prompt,
    gpt_version,
    max_tokens=128,
    temperature=0,
    stop=None,
    logprobs=True,
    frequency_penalty=0,
):
    ## function to query LM ##
    # you may adjust the genration parameters as needed
    # more info on parameters here:
    # https://platform.openai.com/docs/api-reference/completions/create

    message = [
        {
            "role": "system",
            "content": "You are a highly intelligent and context-aware Household AI Robot Assistant.",
        },
        {
            "role": "user",
            "content": f"{prompt}"
            "1. Respond only with the `def` function code. "
            "2. Do not include triple quotes (```) or the word 'python' in your response."
            "3. It should follow the format of the example I gave."
            "4. assert&else can be utilized aggressively."
            "5. Do not write iteration statements(ex. for, while) for iterations. If you must repeat it, write it in full."
            "6. Object name must be exactly the same.",
        },
    ]
    response = client.chat.completions.create(
        model=gpt_version,
        messages=message,
        max_tokens=max_tokens,
        temperature=temperature,
        # stop=stop,
        logprobs=logprobs,
        frequency_penalty=frequency_penalty,
    )

    return response, response.choices[0].message.content.strip().replace(
        "```python", ""
    ).replace("```", "")


def LM_assert(
    prompt,
    gpt_version,
    max_tokens=2,
    temperature=0,
    stop=None,
    logprobs=True,
    frequency_penalty=0,
):
    ## function to query LM ##
    # you may adjust the genration parameters as needed
    # more info on parameters here:
    # https://platform.openai.com/docs/api-reference/completions/create

    message = [
        {
            "role": "system",
            "content": "You are a helpful assistant. just give me only word 'True' or 'False'",
        },
        {"role": "user", "content": f"{prompt}"},
    ]

    response = client.chat.completions.create(
        model=gpt_version,
        messages=message,
        max_tokens=max_tokens,
        temperature=temperature,
        # stop=stop,
        logprobs=logprobs,
        frequency_penalty=frequency_penalty,
    )

    return response, response.choices[0].message.content.strip()


def fun_processing(plan):  # gen plan이 들어오면 각 단계별로 나눠서 저장
    print(plan)
    subgoals = {}
    sg = "0"
    subgoals[sg] = []
    for i in plan.split("\n"):
        # def도 같이 들어가기 때문에 def가 나오면 무시
        if "def" in i:
            continue
        # plan 단계별로 보기
        i = i.strip()
        # 빈 줄은 건너뜀
        if len(i) < 1:
            continue
        # 이건 무조건 없을텐데 no_comments가 주석 제거하는거임.
        """if "comments" in args.prompt_task_examples_ablation:
            subgoals["0"].append(i)"""

        if "#" in i:
            sg = i.split("#")[1]  # '#'이후에 나오는 문자열 저장
            sg = sg.strip()  # 공백 제거
            subgoals[sg] = []  # 문자열을 키로 추가
        else:
            subgoals[sg].append(i)  # 키에 해당하는 함수가 들어감
    print(subgoals)
    return subgoals


def find_objID(controller, obj_type: str) -> str | None:
    """
    Find object ID by matching object type (case-insensitive).
    
    Args:
        controller: AI2Thor controller
        obj_type: Object type name to search for
        
    Returns:
        str | None: Object ID if found, None otherwise
    """
    if not obj_type:
        return None
        
    obj_type_lower = obj_type.lower()
    for obj in controller.last_event.metadata["objects"]:
        if obj["objectType"].lower() == obj_type_lower:
            return obj["objectId"]
    return None


def last_action_success(controller):  ## 마지막 행동이 성공했는지 확인
    if controller.last_event.metadata["lastActionSuccess"]:
        return True
    else:
        return False


def see_have(controller):  ## assert 및 해야할 행동

    controller.step(action="Pass")
    data = controller.last_event.metadata

    # agent가 있는 방 name
    agent_in_room = controller.scene
    # agent가 가지고 있는 object 이름 및 ID
    inventory_objects = data["inventoryObjects"]
    if inventory_objects:
        agent_has_obj = [obj["objectType"] for obj in inventory_objects]
        agent_has_objid = [obj["objectId"] for obj in inventory_objects]
    else:
        agent_has_obj = ""
        agent_has_objid = ""
    # agent와 가까이 있는 object 이름 및 ID
    # ai2thor 에서는 controller을 정의할 때 visibilityDistance를 정의하는데
    # 사실상 visible=true 라는건 볼 수 있고, 가까운걸로 보는게 좋을 것 같음
    obj_ids = dict(
        [
            (obj["objectId"], obj["objectType"])
            for obj in data["objects"]
            if obj["visible"]
        ]
    )
    # relation 뽑아내기. receptacle을 holds로 바꿈. ex) fridge holds egg
    # 관계를 저장할 리스트
    relations = []

    # obj_ids에서 각 객체를 확인
    for obj_id, obj_type in obj_ids.items():
        # obj_ids에서 해당 objectId로 객체 찾기
        obj = next((obj for obj in data["objects"] if obj["objectId"] == obj_id), None)
        if obj is None:
            continue

        receptacle_ids = obj.get("receptacleObjectIds", [])

        if receptacle_ids:  # receptacleObjectIds가 비어 있지 않으면
            for receptacle_id in receptacle_ids:
                # receptacle_id에 해당하는 objectType을 전체 metadata에서 찾아서 사용
                receptacle_obj = next(
                    (
                        obj
                        for obj in data["objects"]
                        if obj["objectId"] == receptacle_id
                    ),
                    None,
                )

                if receptacle_obj:
                    # 'holds' 관계 생성
                    relation = f"{obj_ids[obj_id]} holds {receptacle_obj['objectType']}"
                    relations.append(relation)
                else:
                    print(
                        f"Warning: receptacleId {receptacle_id} not found in metadata"
                    )

    # 이젠 state 뽑아낼거임(obj)
    objs = []
    # 속성 리스트
    properties = [
        # "isInteractable",
        "isToggled",
        "isBroken",
        "isFilledWithLiquid",
        "isDirty",
        "isUsedUp",
        "isCooked",
        "isHeatSource",
        "isColdSource",
        "isSliced",
        "isOpen",
        "isPickedUp",
        "isMoving",
    ]

    # 속성 체크를 위해 각 객체를 한 번만 처리
    for obj in data["objects"]:
        # obj_ids에 있는 객체만 처리
        if obj["objectId"] not in obj_ids or not obj["visible"]:
            continue

        object_type = obj_ids[obj["objectId"]]  # objectId로 objectType을 얻음
        ob_states = [object_type, []]  # [objectType, 속성 목록]

        # 각 속성에 대해 체크
        for prop in properties:
            if (
                prop == "isOpen"
                and obj.get(prop, False) is False
                and obj.get("openable", False) is True
            ):
                ob_states[1].append("isClosed")
            elif (
                prop == "isToggled"
                and obj.get(prop, False) is False
                and obj.get("toggleable", False) is True
            ):
                ob_states[1].append("isToggledOff")
            elif obj.get(prop, False):  # 속성이 True인 경우
                ob_states[1].append(prop)

        # 속성이 하나라도 있다면 문자열로 추가
        if ob_states[1]:
            objs.append(f"{ob_states[0]} is {' and '.join(ob_states[1])}")
        else:
            # 속성이 모두 False인 경우 object 이름만 추가
            objs.append(ob_states[0])

    objs = ", ".join(objs)
    objs = list(set(objs.split(", ")))
    # 빈 문자열 제거
    objs = [ob for ob in objs if len(ob) > 0]

    # obj들의 상태를 다시 ,로 연결하고, 다른 obj들과 relation들도 ,로 연결
    objs = ", ".join(objs) + ", " + ", ".join(relations) + ". "
    # 지금 갖고있는 obj들도 objs에 추가
    if len(agent_has_obj) > 0:
        agent_has_obj = ", ".join(agent_has_obj)
        objs += f" You have {agent_has_obj}. "

    return objs


def get_current_state_prompt():
    ## fixed function to define "PROMPT for state check"
    ## current state 는 state \n\n assert로 구성되어 있음
    current_state_prompt = "kitchencounterdrawer, door is OPEN, character, wallpictureframe, clothespile is CLOSED, coffeemaker is OFF, pie, wall, bedroom, microwave is OFF and CLOSED, lightswitch is ON, kitchencabinet is CLOSED, washingsponge, bellpepper, salmon, fridge is CLOSED, wallshelf, tvstand, paper, floor, chips, photoframe, kitchen, whippedcream, candybar, faucet is OFF, tv is OFF, cereal, stovefan, waterglass, cutleryknife, kitchentable, condimentbottle, wineglass, bookshelf, cutleryfork, chocolatesyrup, walllamp, bench, sink, crackers, orchid, condimentshaker, kitchencounter is CLOSED, livingroom, powersocket, coffeepot is CLOSED, creamybuns, ceilinglamp, rug, book is CLOSED, plate, toaster is OFF, clock is OFF, wallphone is OFF, ceiling, fryingpan, box is CLOSED, dishbowl, bananas, breadslice, bathroom, garbagecan is CLOSED, stove is OFF and CLOSED, dishwashingliquid, plate ON kitchencounter, cutleryfork ON kitchentable, bookshelf ON floor, cutleryknife ON kitchentable, bellpepper ON kitchencounter, microwave ON kitchencounterdrawer, chocolatesyrup ON wallshelf, whippedcream ON rug, salmon ON microwave, orchid ON tvstand, wallpictureframe ON wall, bench ON floor, tvstand ON floor, book INSIDE bookshelf, bananas ON dishbowl, toaster ON kitchencounterdrawer, whippedcream ON kitchentable, dishbowl INSIDE bookshelf, fryingpan ON stove, rug ON kitchentable, coffeepot INSIDE coffeemaker, waterglass ON rug, dishwashingliquid ON kitchencounter, wallshelf ON wall, washingsponge ON kitchencounter, clothespile INSIDE bookshelf, bananas INSIDE bookshelf, box ON bookshelf, plate ON kitchentable, waterglass ON kitchentable, creamybuns ON wallshelf, breadslice INSIDE toaster, coffeemaker ON kitchencounterdrawer, chips ON wallshelf, book ON kitchentable, dishbowl ON bookshelf, pie ON kitchentable, wineglass ON tvstand, box ON tvstand, coffeepot ON kitchencounter, bellpepper ON kitchencounterdrawer, condimentshaker INSIDE bookshelf, coffeemaker ON kitchencounter, toaster ON kitchencounter, box INSIDE bookshelf, crackers ON wallshelf, character HOLD_RH book, faucet ON kitchencounter, book ON rug, cereal ON wallshelf, plate INSIDE microwave, candybar ON wallshelf, condimentbottle INSIDE bookshelf, tv ON tvstand, microwave ON kitchencounter, paper INSIDE bookshelf, kitchencounterdrawer ON kitchencounter, fridge ON floor, photoframe ON tvstand, wallpictureframe ON wallpictureframe, bench ON rug, pie ON rug, kitchencounterdrawer ON kitchencounterdrawer, dishbowl ON kitchencounter.\n\nassert('close' to 'mug' )\nFalse\nassert('close' to 'microwave' )\nTrue\nassert('book' is 'closed' )\nTrue\nassert('lightswitch' is 'OFF')\nFalse\nassert('book' in 'bookshelf')\nTrue\nassert('book' in 'hands')\nTrue\nassert('cereal' on 'bookshelf')\nFalse"
    objs = ["microwave", "book", "lightswitch", "bookshelf", "cereal"]
    state, asserts = current_state_prompt = current_state_prompt.split("\n\n")
    state = state.split(",")
    state = "You see: " + ", ".join(
        [
            i.strip() for i in state if any(element in i for element in objs)
        ]  # obj에 있는 element가 state에 있는 i 에 있으면 추가. 현재 scene 에 관련 있는 obj들만 뽑으려고 함
    )
    current_state_prompt = f"{state}\n\n{asserts}"
    return current_state_prompt


current_state_prompt = get_current_state_prompt()


def simulate_execution(controller, test_tasks, gen_plan, log_file, args):
    elapsed_time = 0
    Act = Action(controller)
    ## gen plan 토대로 실행
    for task, plan in zip(test_tasks, gen_plan):
        log_file.write(f"Starting simulation for task: {task}\n")
        subgoals = fun_processing(plan)

        total_steps = 0
        last_assert = None
        for subgoal in subgoals.keys():
            step = 1
            act = ""
            for action in subgoals[subgoal]:
                if step > 50:
                    break

                if (
                    "assert" in action
                ):  # assert 이 action 에 있으면 gpt 보내기 & last_assert = action 이 됨
                    objs = see_have(controller)
                    check_state = ""
                    last_assert = action
                    assert_objs = re.findall(r"\b[a-z]+", action)[
                        1::2
                    ]  ## 소문자 단어만을 추출해서 1,3,5,7...번째 단어만 추출
                    # state = objs.split(",")
                    # state = "You see: " + ", ".join(
                    #     [
                    #         i.strip()
                    #         for i in state
                    #         if any(ele in i for ele in assert_objs)
                    #     ]
                    # )
                    state = "You see: " + objs
                    # current_state_prompt는 example assertion check(s) 임
                    current_state = f"{current_state_prompt}\n\n{state}\n\n{action}\n"
                    # state check
                    _, check_state = LM_assert(
                        current_state, args.gpt_version, max_tokens=2, stop=["\n"]
                    )
                    log_file.write(
                        f"State check:\n{state}\n{action}\n{check_state.strip()}\n"
                    )
                    continue  # state check 하고 다음 action으로 넘어감
                ############################ 답장 온거에 따라서 다음 action 결정
                # get recovery actions
                if (
                    last_assert != None
                ):  # True + action 안에 else 가 있으면 다음 action으로 넘어감(사실상 다음 action). False가 답변이면 else action 이 action 이 되는거임. 근데 이제 else 가 없다면 lm 보내서 재확인
                    if "True" in check_state:
                        # skip revovery if state check is true
                        if "else: " in action:
                            continue  # 다음 action으로 넘어감
                    elif "False" in check_state:
                        if "else: " in action:
                            action = action.split(": ")[-1].strip()
                            # false 일 때 할 행동이 있다면 action으로 넣음
                        else:
                            # false 일 때 할 행동이 없다면 다시 check
                            state = objs.split(",")
                            state = "You see: " + ", ".join(
                                [
                                    i.strip()
                                    for i in state
                                    if any(ele in i for ele in assert_objs)
                                ]
                            )
                            current_state = (
                                f"{current_state_prompt}\n\n{state}\n\n{action}\n"
                            )
                            _, check_state = LM_assert(
                                current_state,
                                args.gpt_version,
                                max_tokens=2,
                                stop=["\n"],
                            )
                            log_file.write(
                                f"State check:\n{state}\n{action}\n{check_state.strip()}\n"
                            )

                # since above steps are not for env, following line go through the env
                total_steps += 1
                action = action.split(")")[0]
                action = re.findall(r"\b[a-z]+", action.lower())
                log_file.write(f"Executing action: {action}\n")
                if action[0] == "wait":
                    wait_time = action[1]
                else:   
                    objID = find_objID(controller, action[1])
                    if objID is None:
                        log_file.write(f"WARNING: Could not find object '{action[1]}' in scene\n")
                        logger.warning(f"Could not find object '{action[1]}' in scene")
                        # List available objects for debugging
                        available_objects = [obj["objectType"] for obj in controller.last_event.metadata["objects"]]
                        log_file.write(f"Available objects: {available_objects}\n")
                        continue  # Skip this action and continue with next one

                # assert 먼저 해결
                log_file.write(f"start_time:{str(round(elapsed_time,2))} \n")
                match action[0]:
                    case "walk":
                        # move action
                        elapsed_time += Act.move_to(objID)
                        # move_to 뒤에 바로 오는 log 기록은 살짝 무의미해 보임

                    case "pickup":
                        # pickup action
                        elapsed_time += Act.pickup(objID)
                    case "put":
                        # put action
                        target = find_objID(controller, action[2])
                        elapsed_time += Act.put(target)
                    case "drop":
                        # drop action
                        elapsed_time += Act.drop()
                    case "slice":
                        # slice action
                        elapsed_time += Act.slice(objID)
                    case "open":
                        # open action
                        elapsed_time += Act.open(objID)
                    case "close":
                        # close action
                        elapsed_time += Act.close(objID)
                    case "toggle_on":
                        elapsed_time += Act.toggleon(objID)
                    case "toggle_off":
                        elapsed_time += Act.toggleoff(objID)
                    case "fill":
                        liquid = find_objID(controller, action[2])
                        elapsed_time += Act.fill(objID)
                    case "wait":
                        elapsed_time += Act.wait(wait_time)
                    case "done":
                        time.sleep(0.3)
                        pass
                    case _:
                        log_file.write("Invalid action\n")
                        break
                log_file.write(f"end_time: {str(round(elapsed_time,2))}\n")
                log_file.write(f"execution_status: {last_action_success(controller)}\n")

                # Synchronize state after each action
                controller.step(action="Pass")
                
    print(f"{round(elapsed_time, 2)=}")
    log_file.write(f"Total time spent : {round(elapsed_time, 2)}")
