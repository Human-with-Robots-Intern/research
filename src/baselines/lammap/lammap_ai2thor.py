"""
LaMMA-P AI2-THOR Integration

LaMMA-P baseline을 우리 프로젝트의 ai2thor 환경에서 실행하는 메인 엔트리포인트.
기존 baseline (CAP, ProgPrompt)과 동일한 인터페이스 패턴을 따릅니다.

Pipeline:
    1. ai2thor 컨트롤러 초기화 및 씬 설정
    2. 씬에서 객체 정보 추출 → LaMMA-P에 전달
    3. LaMMA-P PDDL 계획 생성 (LLM + Fast Downward)
    4. 계획을 코드로 변환 (LLM)
    5. 생성된 코드를 파싱하여 primitive actions로 변환
    6. Action handler를 통해 ai2thor에서 실행
    7. 결과 저장

Usage:
    python -m src.baselines.lammap.lammap_ai2thor \\
        --scene FloorPlan1 \\
        --instruction "Place the apple in the fridge" \\
        --openai-api-key-file api_key \\
        --gpt-version gpt-4o
"""

import argparse
import gc
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ai2thor.controller import Controller
from ai2thor.platform import CloudRendering

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from ithor.handlers.action import Action
from src.baselines.lammap.action_adapter import (
    execute_primitive_actions,
    flatten_mimic_to_primitive_actions,
)
from src.simulation.runner_ai2thor import init_ai2thor_controller
from src.utils.common import create_module_logger
from src.utils.config import constants
from src.utils.config.constants import set_init_prior_mean
from src.utils.get_state import save_scene_state
from src.utils.io_utils.result_saver import result_save_llm
from src.utils.ros_executor import RosExecutor


def get_scene_objects_for_lammap(controller: Controller) -> str:
    """ai2thor 씬에서 객체 정보를 추출하여 LaMMA-P가 사용하는 형식으로 반환합니다."""
    controller.step("Pass")
    metadata = controller.last_event.metadata

    obj_list = []
    for obj in metadata["objects"]:
        obj_info = {
            "name": obj["objectType"],
            "objectId": obj["objectId"],
            "mass": obj.get("mass", 0),
            "pickupable": obj.get("pickupable", False),
            "receptacle": obj.get("receptacle", False),
            "openable": obj.get("openable", False),
            "toggleable": obj.get("toggleable", False),
            "sliceable": obj.get("sliceable", False),
        }
        obj_list.append(obj_info)

    return f"\n\nobjects = {json.dumps(obj_list, indent=2)}"


def _build_action_durations(scene_type: str) -> dict:
    """Per-primitive-action duration table for LLM prompts.

    `scene_type='real_world'` uses REAL_NAV_DURATION; ai2thor scenes (kitchen,
    bathroom) use the per-step nav cost since path length varies. Kitchen
    additionally gets OPEN/CLOSE/SLICE entries so the LLM can budget the cost
    of microwave-open and egg-slice style actions when computing residual sleep.
    """
    nav = constants.REAL_NAV_DURATION if scene_type == "real_world" else constants.NAV_STEP_DURATION
    table = {
        "NAVIGATE_TO": nav,
        "GRASP": constants.GRASP_ACTION_DURATION,
        "PLACE_INSIDE": constants.PLACE_ACTION_DURATION,
        "PLACE_ON_TOP": constants.PLACE_ACTION_DURATION,
        "TOGGLE_ON": constants.TOGGLE_ACTION_DURATION,
        "TOGGLE_OFF": constants.TOGGLE_ACTION_DURATION,
        "MONITORING": constants.MONITORING_DURATION,
    }
    if scene_type != "real_world":
        # AI2-THOR scenes also expose OPEN/CLOSE/SLICE primitives. constants.py
        # has no dedicated duration; treat them like TOGGLE-class interactions.
        table["OPEN"] = constants.TOGGLE_ACTION_DURATION
        table["CLOSE"] = constants.TOGGLE_ACTION_DURATION
        table["SLICE"] = constants.TOGGLE_ACTION_DURATION
    return table


def run_lammap_planning(
    base_path: str,
    task: str,
    floor_plan: int,
    objects_ai: str,
    gpt_version: str,
    api_key_file: str,
    logger: logging.Logger,
    wait_units: int = 100,
    scene_type: str = "real_world",
) -> Tuple[str, int]:
    """LaMMA-P의 PDDL 계획 생성 → 코드 변환 파이프라인을 실행합니다.

    Args:
        scene_type: 'real_world' or 'kitchen'/'bathroom'. Selects NAV duration.

    Returns:
        (mimic_code, llm_call_count) — `llm_call_count` is the total number of
        OpenAI calls across TaskManager (decompose/allocate/problem-gen/validate)
        and MimicFormatTranslator (translate + validate-and-fix).
    """
    # LaMMA-P 경로 설정
    lammap_scripts = os.path.join(base_path, "scripts")
    sys.path.insert(0, base_path)
    sys.path.insert(0, lammap_scripts)

    # pddlrun_llmseparate의 핵심 클래스 import
    from scripts.pddlrun_llmseparate import TaskManager
    from plantocode import MimicFormatTranslator

    action_durations = _build_action_durations(scene_type)

    # 로봇 설정 (단일 로봇, 모든 스킬)
    available_robots = [
        {
            "name": "robot1",
            "skills": [
                "GoToObject", "OpenObject", "CloseObject", "BreakObject",
                "SliceObject", "ToggleObjectOn", "ToggleObjectOff", "PickupObject",
                "PutObject", "DropHandObject", "ThrowObject", "PushObject",
                "PullObject",
            ],
            "mass": 100,
        }
    ]

    # api_key 경로 resolve: 절대경로가 아니면 lammap base 기준으로 찾기
    if not os.path.isabs(api_key_file):
        candidates = [
            api_key_file,                                      # CWD 기준
            os.path.join(base_path, api_key_file),             # lammap 디렉토리 기준
            api_key_file + ".txt",                             # CWD 기준 .txt
            os.path.join(base_path, api_key_file + ".txt"),    # lammap 디렉토리 기준 .txt
        ]
        resolved_key = api_key_file
        for c in candidates:
            if os.path.isfile(c):
                resolved_key = c
                break
        api_key_file = resolved_key

    logger.info(f"[LAMMAP] Planning 시작: {task}")
    logger.info(f"[LAMMAP] api_key_file: {api_key_file}")

    # Step 1: PDDL 계획 생성
    t0 = time.time()
    logger.info("[LAMMAP] TaskManager 초기화 중...")
    task_manager = TaskManager(
        base_path=base_path,
        gpt_version=gpt_version,
        api_key_file=api_key_file,
        wait_units=wait_units,
        action_durations=action_durations,
        scene_type=scene_type,
    )
    logger.info(f"[LAMMAP] TaskManager 초기화 완료 ({time.time()-t0:.1f}s)")

    t1 = time.time()
    logger.info("[LAMMAP] process_tasks 시작 (LLM decompose/allocate/pddl/plan)...")
    task_manager.process_tasks(
        test_tasks=[task],
        available_robots=[available_robots],
        objects_ai=objects_ai,
    )
    logger.info(f"[LAMMAP] process_tasks 완료 ({time.time()-t1:.1f}s)")

    # Step 2: 계획을 실행 코드로 변환
    if task_manager.code_planpddl:
        combined_plan = task_manager.code_planpddl[0]
        logger.info(f"[LAMMAP] code_planpddl 사용 (길이: {len(combined_plan)})")
    elif task_manager.combined_plan:
        combined_plan = task_manager.combined_plan[0]
        logger.info(f"[LAMMAP] combined_plan 사용 (길이: {len(combined_plan)})")
    else:
        raise RuntimeError("LaMMA-P failed to generate a plan")

    t2 = time.time()
    logger.info("[LAMMAP] MimicFormatTranslator 초기화 중...")
    translator = MimicFormatTranslator(
        api_key_file=api_key_file,
        gpt_version=gpt_version,
        wait_units=wait_units,
        action_durations=action_durations,
        scene_type=scene_type,
    )

    logger.info("[LAMMAP] translate_to_mimic_format 호출 중 (LLM)...")
    mimic_code = translator.translate_to_mimic_format(task, combined_plan)
    logger.info(f"[LAMMAP] 코드 변환 완료 ({time.time()-t2:.1f}s, 길이: {len(mimic_code)})")

    # Validate & fix
    t3 = time.time()
    logger.info("[LAMMAP] validate_and_fix 호출 중 (LLM)...")
    is_valid, msg, corrected_code = translator.validate_and_fix_mimic_code(
        mimic_code, task
    )
    if corrected_code and len(corrected_code.strip()) > 0:
        mimic_code = corrected_code
    logger.info(f"[LAMMAP] 코드 검증 완료 ({time.time()-t3:.1f}s, valid={is_valid})")

    llm_call_count = (
        getattr(task_manager.llm, "call_count", 0)
        + getattr(translator.llm, "call_count", 0)
    )
    logger.info(f"[LAMMAP] 총 LLM 호출 수: {llm_call_count}")

    return mimic_code, llm_call_count


def run_lammap_from_task_file(
    base_path: str,
    task_file: str,
    task_index: int,
    objects_ai: str,
    gpt_version: str,
    api_key_file: str,
    logger: logging.Logger,
) -> Tuple[str, int]:
    """exp/ 폴더의 태스크 파일에서 특정 태스크를 로드하여 실행합니다."""
    with open(task_file, "r") as f:
        tasks = json.load(f)

    if task_index >= len(tasks):
        raise ValueError(f"Task index {task_index} out of range (max {len(tasks)-1})")

    task_data = tasks[task_index]
    instruction = task_data["instruction"]
    logger.info(f"Loading task from file: {instruction}")

    return run_lammap_planning(
        base_path=base_path,
        task=instruction,
        floor_plan=0,
        objects_ai=objects_ai,
        gpt_version=gpt_version,
        api_key_file=api_key_file,
        logger=logger,
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LaMMA-P AI2-THOR Baseline")
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        help="AI2-THOR 씬 이름 (default: FloorPlan1)",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default=None,
        help="실행할 태스크 명령어",
    )
    parser.add_argument(
        "--task-file",
        type=str,
        default=None,
        help="exp/ 폴더의 태스크 파일 경로 (--instruction 대신 사용)",
    )
    parser.add_argument(
        "--task-index",
        type=int,
        default=0,
        help="태스크 파일에서의 인덱스 (default: 0)",
    )
    parser.add_argument(
        "--openai-api-key-file",
        type=str,
        default="api_key",
        help="OpenAI API 키 파일 경로",
    )
    parser.add_argument(
        "--gpt-version",
        type=str,
        default="gpt-4o",
        choices=["gpt-3.5-turbo", "gpt-4o", "gpt-3.5-turbo-16k", "gpt-5"],
        help="사용할 GPT 모델",
    )
    parser.add_argument(
        "--cloud-rendering",
        default=False,
        action="store_true",
        help="CloudRendering 사용 여부",
    )
    parser.add_argument(
        "--ros",
        default=False,
        action="store_true",
        help="ROS 실행 모드 (default: False)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="로깅 레벨",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default=None,
        help="로그 파일 경로",
    )
    parser.add_argument(
        "--case",
        type=str,
        default="tasks_3_constraints_2",
        help="The name of the case.",
    )
    parser.add_argument(
        "--ablation-name",
        type=str,
        default=None,
        help="The name of the ablation configuration.",
    )
    parser.add_argument(
        "--simulation",
        default=False,
        action="store_true",
        help="Simulation mode flag.",
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="시도 횟수 (default: 1)",
    )
    parser.add_argument(
        "--init_prior_mean",
        type=float,
        default=60,
        help="초기 prior mean 값 (default: 60)",
    )
    parser.add_argument(
        "--init_prior_variance",
        type=float,
        default=900,
        help="초기 prior variance 값 (default: 900)",
    )
    parser.add_argument(
        "--task-folder-name",
        type=str,
        default=None,
        help="태스크 폴더 이름",
    )
    parser.add_argument(
        "--llm-cache-file",
        type=str,
        default=None,
        help="사전 계산된 LLM 결과 캐시 파일 경로 (없으면 실제 LLM 호출)",
    )
    return parser.parse_args()


def _load_cached_primitive_actions(
    cache_file: Optional[str],
    *,
    scene: str,
    case: Optional[str],
    instruction: Optional[str],
    instruction_dir_name: str,
    duration: int,
    task_folder_name: Optional[str],
    logger: logging.Logger,
) -> Optional[List[str]]:
    """Look up `{scene}|{case}|{instruction_filename}|{duration}` in the cache.

    Version index is derived from a `_v(\\d+)` suffix in `task_folder_name`
    (precompute_lammap_llm.py stores attempts as a list ordered by attempt).
    Returns None on miss; caller decides whether to fail-fast.
    """
    if not cache_file:
        return None
    cache_path = Path(cache_file)
    if not cache_path.exists():
        logger.warning(f"[LAMMAP] cache file not found: {cache_path}")
        return None

    instr_name = instruction if (instruction and instruction.endswith(".json")) else f"{instruction_dir_name}.json"
    cache_key = f"{scene}|{case}|{instr_name}|{duration}"

    version_idx = 0
    if task_folder_name:
        vm = re.search(r"_v(\d+)$", task_folder_name)
        if vm:
            version_idx = int(vm.group(1)) - 1

    with cache_path.open("r", encoding="utf-8") as f:
        cache = json.load(f)

    cached_list = cache.get(cache_key, [])
    if version_idx < len(cached_list) and cached_list[version_idx]:
        entry = cached_list[version_idx]

        # New dict format: {"primitive_actions": [...], "planning_computation_time": ..., ...}
        if isinstance(entry, dict) and "primitive_actions" in entry:
            actions = entry["primitive_actions"]
            pct = entry.get("planning_computation_time")
            logger.info(
                f"[LAMMAP] 캐시 히트: {cache_key} [v{version_idx + 1}] "
                f"(actions={len(actions)}, planning_computation_time={pct}s)"
            )
            return actions

        # Backward-compat: bare list of primitive_actions.
        if isinstance(entry, list):
            logger.info(
                f"[LAMMAP] 캐시 히트(legacy list): {cache_key} [v{version_idx + 1}] "
                f"(actions={len(entry)})"
            )
            return entry

        # Legacy mimic_code cache (string) — incompatible with this version.
        logger.error(
            f"[LAMMAP] 캐시 형식이 구버전(mimic_code 문자열)입니다. "
            f"`scripts/precompute_lammap_llm.py`를 새 버전으로 다시 돌려 "
            f"primitive_actions 형식으로 재생성하세요. key={cache_key}"
        )
        return None

    logger.warning(f"[LAMMAP] 캐시 미스: {cache_key} [v{version_idx + 1}]")
    return None


def main():
    args = parse_arguments()
    scene_name = args.scene
    instruction = args.instruction

    if args.init_prior_mean is not None:
        set_init_prior_mean(args.init_prior_mean)

    if args.task_folder_name:
        dynamic_task_path = constants.ASSETS_PATH / "tasks" / args.task_folder_name
        constants.set_task_path(dynamic_task_path)
        base_result_path = constants.RESULT_PATH / args.task_folder_name
    else:
        base_result_path = constants.RESULT_PATH

    approach_name_base = "lammap"
    if args.simulation:
        approach_name = f"{approach_name_base}_simulation"
    elif args.ros:
        approach_name = f"{approach_name_base}_ros"
    else:
        approach_name = approach_name_base

    logger = create_module_logger(
        module_name=approach_name,
        log_file_path=Path(args.log_path) if args.log_path else None,
        level=args.log_level,
    )

    # instruction_dir_name and task_string follow the run_all convention used
    # by other baselines (cpm/dag_bayesian/progprompt).
    if instruction and instruction.endswith(".json"):
        instruction_dir_name = Path(instruction).stem
        m = re.match(r"\d+_(.*)", instruction_dir_name)
        task_string = m.group(1).replace("_", " ") if m else instruction_dir_name.replace("_", " ")
    elif instruction:
        instruction_dir_name = re.sub(r"[^a-zA-Z0-9]+", "_", instruction).strip("_")
        task_string = instruction
    elif args.task_file:
        instruction_dir_name = f"lammap_task_{args.task_index}"
        task_string = None
    else:
        raise ValueError("--instruction or --task-file is required")

    trajectory_path = (
        base_result_path
        / f"states{int(args.init_prior_mean)}/{args.case}/{instruction_dir_name}/{scene_name}/{approach_name}/trajectory_log.json"
    )
    if trajectory_path.exists():
        trajectory_path.unlink()

    controller = None
    action_interface: Any = None
    t_main_start = time.time()
    wait_units = int(args.init_prior_mean) if args.init_prior_mean is not None else 100

    try:
        # --- Action interface (progprompt pattern) ---
        if args.simulation:
            platform_obj = CloudRendering if args.cloud_rendering else None
            controller = init_ai2thor_controller(scene_name, platform=platform_obj)
            save_scene_state(
                controller=controller,
                output_path=base_result_path / f"states{int(args.init_prior_mean)}",
                case_name=args.case,
                scene_name=scene_name,
                instruction=instruction_dir_name,
                approach_name=approach_name,
                state_label="init",
            )
            action_interface = Action(
                controller,
                logger=logger,
                trajectory_log_json_path=trajectory_path,
            )
        elif args.ros:
            save_scene_state(
                controller=None,
                output_path=base_result_path / f"states{int(args.init_prior_mean)}",
                case_name=args.case,
                scene_name=scene_name,
                instruction=instruction_dir_name,
                approach_name=approach_name,
                state_label="init",
            )
            action_interface = RosExecutor(
                trajectory_log_path=trajectory_path,
                instruction=instruction,
            )
        else:
            raise ValueError("Either --simulation or --ros must be set")

        # --- Resolve primitive_actions: cache-first, LLM as standalone fallback ---
        primitive_actions = _load_cached_primitive_actions(
            cache_file=args.llm_cache_file,
            scene=scene_name,
            case=args.case,
            instruction=instruction,
            instruction_dir_name=instruction_dir_name,
            duration=wait_units,
            task_folder_name=args.task_folder_name,
            logger=logger,
        )

        if primitive_actions is None:
            if args.llm_cache_file:
                # Cache file specified but missed — fail-fast so silent reruns of
                # the LLM never sneak into the experiment matrix.
                raise RuntimeError(
                    f"[LAMMAP] cache miss for "
                    f"{scene_name}|{args.case}|{instruction}|{wait_units}; "
                    f"populate {args.llm_cache_file} via "
                    f"scripts/precompute_lammap_llm.py"
                )

            # Standalone fallback: invoke the full LaMMaP pipeline.
            logger.info("[LAMMAP] cache 미사용 — LLM/PDDL 직접 호출 (standalone 모드)")
            if args.ros:
                with open("assets/ros/static/object_init_states.json") as f:
                    ros_objs = json.load(f)
                objects_ai = f"\n\nobjects = {json.dumps(list(ros_objs.keys()))}"
            else:
                objects_ai = get_scene_objects_for_lammap(controller)

            lammap_base = os.path.dirname(os.path.abspath(__file__))
            if args.task_file:
                mimic_code, _llm_calls = run_lammap_from_task_file(
                    base_path=lammap_base,
                    task_file=args.task_file,
                    task_index=args.task_index,
                    objects_ai=objects_ai,
                    gpt_version=args.gpt_version,
                    api_key_file=args.openai_api_key_file,
                    logger=logger,
                )
                if not task_string:
                    with open(args.task_file) as f:
                        tasks = json.load(f)
                    task_string = tasks[args.task_index]["instruction"]
            else:
                mimic_code, _llm_calls = run_lammap_planning(
                    base_path=lammap_base,
                    task=task_string,
                    floor_plan=int(scene_name.replace("FloorPlan", "")),
                    objects_ai=objects_ai,
                    gpt_version=args.gpt_version,
                    api_key_file=args.openai_api_key_file,
                    logger=logger,
                    wait_units=wait_units,
                    scene_type=("real_world" if args.ros else "kitchen"),
                )
            primitive_actions = flatten_mimic_to_primitive_actions(
                mimic_code,
                mode=("ros" if args.ros else "ai2thor"),
                controller=controller,
                logger=logger,
            )

        if not primitive_actions:
            raise RuntimeError("[LAMMAP] No primitive actions to execute")

        logger.info(f"[LAMMAP] primitive_actions ({len(primitive_actions)}):")
        for i, pa in enumerate(primitive_actions):
            logger.info(f"  [{i + 1}] {pa}")

        # --- Execute via the unified action_interface ---
        computation_time_start = time.time()
        if args.simulation:
            elapsed_time, all_succeeded = execute_primitive_actions(
                controller=controller,
                action_interface=action_interface,
                primitive_actions=primitive_actions,
                logger=logger,
            )
        else:  # ROS
            all_succeeded, elapsed_time, _action_logs = action_interface.execute_primitive_actions(
                primitive_actions
            )
        computation_time = time.time() - computation_time_start

        logger.info(
            f"[LAMMAP] 실행 완료 — elapsed={elapsed_time}s, "
            f"success={all_succeeded}, computation_time={computation_time:.2f}s"
        )

        save_scene_state(
            controller=controller,
            output_path=base_result_path / f"states{int(args.init_prior_mean)}",
            case_name=args.case,
            scene_name=scene_name,
            instruction=instruction_dir_name,
            approach_name=approach_name,
            state_label="end",
        )

        result_save_llm(
            approach_name=approach_name,
            user_input=instruction_dir_name,
            result=str(trajectory_path),
            json_output_path=instruction_dir_name,
            computation_time=computation_time,
            scene_name=scene_name,
            attempt=args.attempt,
            init_prior_mean=args.init_prior_mean,
            case_name=args.case,
            base_result_path=base_result_path,
        )

        logger.info("[LAMMAP] 실행이 완료되었습니다.")

    except Exception as e:
        logger.error(f"[LAMMAP] 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        if controller:
            try:
                controller.stop()
            except Exception:
                pass
        sys.exit(1)
    finally:
        if isinstance(action_interface, RosExecutor):
            try:
                action_interface.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down ROS executor: {e}")
        if controller:
            try:
                controller.stop()
            except Exception as e:
                logger.error(f"Error stopping controller: {e}")
        gc.collect()
        logger.info(f"[LAMMAP] 전체 소요시간: {time.time() - t_main_start:.1f}s. Exiting.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # ai2thor cloud_rendering 의 Unity 자식 process 가 controller.stop() 후에도
        # 안 죽고 살아있어 worker 가 종료 안 되는 문제 회피.
        # 모든 결과 파일 저장 및 logger flush 가 main() finally 에서 이미 끝났음.
        import os
        os._exit(0)
