import argparse
import copy
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TextIO

import numpy as np

# import for ai2thor
from ai2thor.controller import Controller
from ai2thor.platform import CloudRendering

import src.baselines.cap.util.LMPgen as gen
from src.simulation.runner_ai2thor import init_ai2thor_controller
from src.utils.common import create_module_logger
from src.utils.config.constants import *
from src.utils.get_state import save_scene_state
from src.utils.io_utils.result_saver import result_save_llm
from src.utils.io_utils.task_io import list_task_files

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from ithor.handlers.action import Action

last_end_time: float = 0.0  # 마지막 액션의 종료 시간을 추적
## LMP Prompts
# LMP(Language Model Program)를 위한 프롬프트 파일 경로
prompt_scene_ui_path = "src/baselines/cap/data/prompt_scene_ui.txt"
prompt_parse_obj_name_path = "src/baselines/cap/data/prompt_parse_obj_name.txt"
prompt_parse_question_path = "src/baselines/cap/data/prompt_parse_question.txt"
prompt_fgen_path = "src/baselines/cap/data/prompt_fgen.txt"


def read_txt(file_path: str) -> Optional[str]:
    """지정된 경로의 텍스트 파일을 읽어 내용을 반환합니다.

    Args:
        file_path (str): 읽어올 파일의 경로.

    Returns:
        Optional[str]: 파일의 내용. 파일을 찾을 수 없거나 오류 발생 시 None을 반환합니다.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return content  # 파일 내용을 출력
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


# 프롬프트 파일 읽기
prompt_scene_ui = read_txt(prompt_scene_ui_path).strip()
prompt_parse_obj_name = read_txt(prompt_parse_obj_name_path).strip()
prompt_parse_question = read_txt(prompt_parse_question_path).strip()
prompt_fgen = read_txt(prompt_fgen_path).strip()


def build_temporal_logic_guidelines(wait_units: int) -> str:
    """Temporal logic guideline text with dynamic wait time units.

    Args:
        wait_units (int): Canonical integer wait time to reference in examples.

    Returns:
        str: Multi-line guideline text to be appended to prompts.
    """
    return (
        """
    # Guidelines for Temporal Logic in Task Planning

    - Task Sequencing:
        - Ensure all tasks follow logical order (A before B when prerequisite).
        - Identify and respect prerequisites between tasks.

    - Autonomous Processing & Wait Times:
        - Infer reasonable integer wait times for autonomous operations or process completion.
        - Typical ranges:
            - Microwave/Stove cooking: ~{wait} time units
            - Filling a Pot: ~{wait} time units
            - Filling a Mug: ~{wait} time units

    - Immediate Sequential Actions:
        - If a single continuous operation is split (e.g., pick up then place),
          the time gap between them is 0 (immediate succession).

    - Urgency and Immediate Follow-up:
        - Some actions must immediately follow the prior one due to time-sensitive states.
        - Examples:
            - Turn off stove immediately after cooking completes.
            - Turn off faucet immediately when a container is full.
            - Promptly remove items when machine cycles complete.
        - If a follow-up is not time-critical (e.g., serving/eating later), it need not be immediate.
    """
    ).format(wait=wait_units)


def timed_action(
    log_file: TextIO, action_name: str, action_func: Callable, controller: Controller
) -> Callable[..., float]:
    """주어진 액션 함수를 감싸 시간 측정 및 로깅을 수행합니다.

    액션 실행 전후로 시간을 측정하고, 그 결과를 지정된 로그 파일에
    `result_save_llm`가 파싱할 수 있는 형식으로 기록합니다.
    액션의 시작 시간은 이전 액션이 끝난 시간으로 설정됩니다.

    Args:
        log_file (TextIO): 로그를 기록할 파일 객체.
        action_name (str): 로깅에 사용될 액션의 이름.
        action_func (Callable): 실행 시간을 측정하고 로깅할 실제 액션 함수.
        controller (Controller): AI2-THOR 컨트롤러 인스턴스. 액션 성공 여부 확인에 사용됩니다.

    Returns:
        Callable[..., float]: 시간을 측정하고 결과를 로깅하는 래퍼 함수.
                            이 래퍼 함수는 실행된 액션의 소요 시간을 반환합니다.
    """

    def wrapper(*args: Any, **kwargs: Any) -> float:
        """래퍼 함수는 실제 액션을 실행하고 로깅합니다."""
        global last_end_time
        # 액션 시작 로그: 액션 이름과 대상을 공백으로 구분된 단일 문자열로 기록하도록 수정합니다.
        action_log_str = " ".join([action_name] + [str(arg) for arg in args])
        # 최종 JSON에서 단일 문자열로 인식되도록, 로그 파일에 문자열 리터럴 형식으로 기록합니다.
        log_file.write(f'Executing action: "{action_log_str}"\n')

        # 이전 액션의 종료 시간을 현재 액션의 시작 시간으로 사용
        start_time = last_end_time
        elapsed_time = action_func(*args, **kwargs)  # 실제 액션 함수 실행
        if elapsed_time is None:
            # action_func가 None을 반환하는 경우, 시간 변화가 없음을 의미.
            elapsed_time = 0.0

        end_time = start_time + elapsed_time
        last_end_time = end_time  # 다음 액션을 위해 마지막 종료 시간 업데이트

        # 액션 시간 및 실행 결과 로그
        log_file.write(f"start_time: {round(start_time, 2)}\n")
        log_file.write(f"end_time: {round(end_time, 2)}\n")

        if controller.last_event.metadata["lastActionSuccess"]:
            log_file.write(f"execution_status: {True}\n")
        else:
            log_file.write(f"execution_status: {False}\n")

        # Synchronize state after the action has been executed and logged.
        controller.step(action="Pass")

        return elapsed_time

    return wrapper


def build_cfg_scene(temporal_guidelines: str) -> Dict[str, Any]:
    """LMP 설정을 런타임에 생성해 반환합니다.

    Args:
        temporal_guidelines (str): 프롬프트에 주입할 시간 논리 가이드라인.

    Returns:
        Dict[str, Any]: LMP 설정 딕셔너리.
    """
    return {
        "lmps": {
            "scene_ui": {
                "prompt_text": prompt_scene_ui
                + "\n"
                + temporal_guidelines
                + "\nobjects = [{objects}]",
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
                "prompt_text": prompt_fgen + "\n" + temporal_guidelines,
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


def setup_LMP(
    controller: Controller, Act: Action, cfg_scene: Dict[str, Any], log_file: TextIO
) -> gen.LMP:
    """LMP (Language Model Program) 환경을 설정하고 초기화합니다.

    AI2-THOR 컨트롤러와 액션 핸들러를 기반으로 LMP 환경을 구성합니다.
    환경에는 초기 객체 목록과 좌표 정보가 포함됩니다.
    또한, LMP가 상호작용할 수 있는 API(액션 함수, 상태 조회 함수 등)를
    정의하고, 시간 측정 및 로깅을 위해 액션 함수들을 `timed_action`으로 감쌉니다.
    마지막으로, 다양한 LMP(함수 생성, 파싱, 상위 레벨 명령어 처리)를
    생성하여 반환합니다.

    Args:
        controller (Controller): AI2-THOR 시뮬레이션 컨트롤러.
        Act (Action): 시뮬레이션 환경에서 에이전트의 액션을 정의하는 핸들러.
        cfg_scene (Dict[str, Any]): LMP 설정을 담고 있는 딕셔너리.
        log_file (TextIO): 액션 로그를 기록할 파일 객체.

    Returns:
        gen.LMP: 사용자의 상위 레벨 언어 명령을 처리하도록 설정된 메인 LMP 객체.
    """
    # LMP env wrapper
    # 설정 파일을 깊은 복사하여 원본을 유지합니다.
    cfg_scene = copy.deepcopy(cfg_scene)
    # LMP 환경에 대한 정보를 저장할 딕셔너리를 생성합니다.
    # 현재 구현에서는 이 딕셔너리가 사용되지 않으므로 주석 처리합니다.
    # cfg_scene["env"] = dict()
    # 이 값은 LMP_wrapper에서 직접 다시 계산되므로, 현재 구현에서는 중복입니다.
    # 추후 리팩토링을 통해 LMP_wrapper가 이 값을 사용하도록 변경할 수 있습니다.
    # cfg_scene["env"]["init_objs"] = list(
    #     set(obj["objectType"] for obj in controller.step("Pass").metadata["objects"])
    # )

    # LMP 환경을 감싸는 래퍼를 생성합니다.
    LMP_env = gen.LMP_wrapper(controller, cfg_scene)

    # LMP가 사용할 수 있는 API(고정 변수)를 정의합니다.
    fixed_vars = {"np": np}
    fixed_vars.update({"time": time})
    fixed_vars.update({"controller": Controller})

    for var_name, var_value in fixed_vars.items():
        vars_log.write(f"{var_name}: {var_value}\n")

    # LMP가 사용할 수 있는 API(가변 변수, 주로 액션 함수)를 정의합니다.
    # pickup, slice, put, drop, toggleon, toggleoff, open, close, monitoring, wait, fill, move to
    variable_vars = {
        k: getattr(Act, k)
        for k in [
            "pickup",
            "slice",
            "put",
            "drop",
            "toggle_on",
            "toggle_off",
            "open",
            "close",
            "monitoring",
            "wait",
            "fill",
            "move_to",
        ]
    }

    # 정의된 액션 함수들을 timed_action으로 감싸 시간 측정 및 로깅을 추가합니다.
    for action_name in [
        "pickup",
        "slice",
        "put",
        "drop",
        "toggle_on",
        "toggle_off",
        "open",
        "close",
        "monitoring",
        "wait",
        "fill",
        "move_to",
    ]:
        original_func = variable_vars[action_name]
        variable_vars[action_name] = timed_action(
            log_file, action_name, original_func, controller
        )

    # 환경 상태를 조회하는 함수들을 가변 변수에 추가합니다.
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

    # 로봇이 메시지를 출력하는 'say' 함수를 추가합니다.
    variable_vars["say"] = lambda msg: print(f"robot says: {msg}")

    # 함수 생성 LMP(lmp_fgen)를 생성합니다.
    lmp_fgen = gen.LMPFGen(cfg_scene["lmps"]["fgen"], fixed_vars, variable_vars)

    # 다른 저수준 LMP(객체 이름 파싱, 질문 파싱)들을 생성합니다.
    variable_vars.update(
        {
            k: gen.LMP(k, cfg_scene["lmps"][k], lmp_fgen, fixed_vars, variable_vars)
            for k in [
                "parse_obj_name",
                "parse_question",
            ]
        }
    )

    # 고수준 언어 명령을 처리하는 메인 LMP(lmp_scene_ui)를 생성합니다.
    lmp_scene_ui = gen.LMP(
        "scene_ui",
        cfg_scene["lmps"]["scene_ui"],
        lmp_fgen,
        fixed_vars,
        variable_vars,
    )

    return lmp_scene_ui


def parse_arguments() -> argparse.Namespace:
    """스크립트 실행을 위한 명령행 인자를 파싱합니다.

    Returns:
        argparse.Namespace: 파싱된 명령행 인자를 담고 있는 객체.
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
        "--scene",
        type=str,
        default="FloorPlan1",
        # 추후에 scene 목록이 생기면 choices = [] 으로 구현한다.
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)",
    )
    parser.add_argument(
        "--instruction", type=str, default=None, help="실행할 자연어 명령어"
    )
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
        help="The attempt number for a run.",
    )
    parser.add_argument(
        "--cloud-rendering",
        action="store_true",
        help="Use CloudRendering platform for AI2-THOR.",
    )
    parser.add_argument(
        "--init_prior_mean",
        type=float,
        default=None,
        help="베이지안 추정을 위한 초기 평균값 (기본값: 60.0)",
    )
    parser.add_argument(
        "--init_prior_variance",
        type=float,
        default=None,
        help="베이지안 추정을 위한 초기 분산값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="The name of the case.",
    )
    parser.add_argument(
        "--ablation-name",
        type=str,
        default=None,
        help="The name of the ablation configuration.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    # --- 스크립트 설정 및 초기화 ---
    approach_name = "cap_ai2thor_simulation"
    args = parse_arguments()

    # Handle INIT_PRIOR_MEAN override
    if args.init_prior_mean is not None:
        from src.utils.config.constants import set_init_prior_mean

        set_init_prior_mean(args.init_prior_mean)

    logger = create_module_logger(
        module_name=approach_name,
        log_file_path=Path(args.log_path) if args.log_path else None,
        level=args.log_level,
    )
    scene_name = args.scene
    instruction = args.instruction
    controller = None
    log_file = None

    platform_obj = None
    if args.cloud_rendering:
        platform_obj = CloudRendering

    try:
        task_files = list_task_files(scene_name)

        if args.case:
            if instruction is None:
                print("Error: --case가 지정되면 --instruction도 필요합니다.")
                sys.exit(1)
            stem = Path(instruction).stem
            m = re.match(r"\d+_(.*)", stem)
            instruction = m.group(1) if m else stem
        elif instruction:
            try:
                choice = int(instruction)
                if 1 <= choice <= len(task_files):
                    instruction = Path(task_files[choice - 1]).stem
                else:
                    print(
                        f"Error: Invalid number. Please choose a number between 1 and {len(task_files)}."
                    )
                    sys.exit(1)
            except ValueError:
                # instruction is not a number, so we treat it as a natural language command.
                pass
        else:
            print("명령어가 인자로 제공되지 않았습니다. 사용자 입력을 기다립니다...")
            instruction = input()

        # 결과 로깅을 위한 파일 열기
        if args.log_path:
            log_file_path = Path(args.log_path)
        else:
            log_dir = Path("src/baselines/cap/result")
            log_dir.mkdir(exist_ok=True)
            log_file_path = log_dir / f"cap_logs_{instruction}.txt"

        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_file_path, "w", buffering=1)

        # AI2-THOR 컨트롤러 초기화
        controller = init_ai2thor_controller(scene_name, platform=platform_obj)
        # Use a consistent directory name for state saving (keep numeric prefix when case)
        instruction_dir_name = (
            Path(args.instruction).stem
            if (args.case and args.instruction)
            else (Path(instruction).stem if instruction else instruction)
        )
        save_scene_state(
            controller=controller,
            output_path=Path(f"assets/results/states{int(args.init_prior_mean)}"),
            case_name=args.case,
            scene_name=scene_name,
            instruction=instruction_dir_name,
            approach_name=approach_name,
            state_label="init",
        )
        # Action 핸들러 초기화
        ithor_action_controller = (
            Action(
                controller,
                logger=logger,
                trajectory_log_json_path=Path(
                    f"assets/results/states{int(args.init_prior_mean)}/{args.case}/{instruction_dir_name}/{scene_name}/{approach_name}/trajectory_log.json"
                ),
            ),
        )

        # LMP 환경 설정
        wait_units = (
            int(args.init_prior_mean) if args.init_prior_mean is not None else 60
        )
        temporal_guidelines = build_temporal_logic_guidelines(wait_units)
        cfg_scene_runtime = build_cfg_scene(temporal_guidelines)
        lmp_scene_ui = setup_LMP(
            controller, ithor_action_controller, cfg_scene_runtime, log_file
        )

        # --- 태스크 실행 ---
        # 사용 예시:
        # toast the bread
        # put tomato in the fridge
        # put egg in the pan : 냉장고 문을 안열고 계란 집음
        # put the book in the sinkbasin : put 상호작용이 불가능해서 던짐
        # toast the bread and put tomato in the fridge. put egg in the pan.
        # pick the apple and drop the apple

        # 현재 장면에 있는 객체 목록 가져오기
        objs = list(
            set(
                obj["objectType"] for obj in controller.step("Pass").metadata["objects"]
            )
        )
        print(f"objs: {objs}")
        cap_log_path = log_file_path
        print(f"'{instruction}' 명령을 실행합니다...")
        computation_time_start = time.time()

        # LMP를 통해 명령어 실행
        lmp_scene_ui(instruction, objects=f"{objs}")

        # --- 결과 저장 ---
        # 현재 computaion_time은 시뮬레이션 타임을 포함해서 정확하지 않음.
        # 추후에 llmgeneration 방식의 computation_time을 폐기할 수 있으므로 일단 스킵
        computation_time = time.time() - computation_time_start
        result_path = f"{instruction_dir_name}"
        result_args = {
            "approach_name": approach_name,
            "user_input": instruction_dir_name,
            "result": str(cap_log_path),
            "json_output_path": result_path,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "attempt": args.attempt,
            "init_prior_mean": args.init_prior_mean,
            "case_name": args.case,
        }

        result_save_llm(**result_args)
        save_scene_state(
            controller=controller,
            output_path=Path(f"assets/results/states{int(args.init_prior_mean)}"),
            case_name=args.case,
            scene_name=scene_name,
            instruction=instruction_dir_name,
            approach_name=approach_name,
            state_label="end",
        )
        if log_file:
            log_file.flush()
            log_file.close()
        print("실행이 완료되었습니다.")
    finally:
        if controller:
            controller.stop()
        # 보조 파일 핸들 및 프로세스 종료 보장
        try:
            if log_file and not log_file.closed:
                log_file.flush()
                log_file.close()
        except Exception:
            pass
        try:
            if not vars_log.closed:
                vars_log.flush()
                vars_log.close()
        except Exception:
            pass
        # 백그라운드 스레드/리소스가 잔류하더라도 프로세스 종료
        sys.exit(0)
