import csv
import functools
import glob
import json
import logging
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import optuna

# --- 프로젝트 경로 설정 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"sys.path updated: {sys.path[:3]}")
except NameError:
    # Handle cases where __file__ is not defined (e.g., interactive environments)
    PROJECT_ROOT = Path(".").resolve()
    SRC_ROOT = PROJECT_ROOT / "src"
    ASSETS_ROOT = PROJECT_ROOT / "assets"
    ITHOR_ROOT = PROJECT_ROOT / "ithor"
    sys.path.insert(0, str(SRC_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(ITHOR_ROOT))

# --- 필요한 모듈 임포트 ---
try:
    from handlers.navigation_handler import load_navigation_graph

    from core.agent import Agent
    from core.dataclass import CompletedEntry, SchedulerState
    from core.scheduler import Scheduler
    from core.task import Subtask, Task
    from scheduler.action_handler import ActionHandler
    from scheduler.constraint_handler import ConstraintHandler
    from scheduler.heuristic_manager import HeuristicManager
    from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
    from src.utils.common.logger import create_module_logger  # Assuming logger setup
    from src.utils.config import BEAM_WIDTH, SCENE_NAME, SIMULATION_DEPTH
    from src.utils.io_utils.result_saver import compose_plans
    from src.utils.io_utils.task_io import (
        list_task_files,
        load_scene_positions,
        load_task_data_from_file,
    )
    from src.utils.task import TaskUtil
except ImportError as e:
    print(f"Fatal Error importing: {e}\nPYTHONPATH: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Fatal Error during initial imports: {e}")
    sys.exit(1)


# --- 로깅 설정 ---
def setup_logging():
    """애플리케이션 루트 로거를 설정합니다."""
    log_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] %(message)s"
    )
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(log_formatter)
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)
    logging.getLogger("optuna").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


log = setup_logging()


# ==============================================================================
# 전역 변수 및 설정 (Global Variables & Configuration)
# ==============================================================================

# --- 경로 설정 ---
TASK_FILES_DIR = ASSETS_ROOT / "tasks"
SCENE_POSITIONS_DIR = ASSETS_ROOT / "knowledge" / "scene_positions"

# --- 튜닝 대상 태스크 목록 ---
# 모든 task 사용시:
# TUNING_TASK_NAMES_LIST = [p.name for p in TASK_FILES_DIR.glob("*.json")]
# 특정 task 사용시:
TUNING_TASK_NAMES_LIST = ["complex3_12subtasks(dc1, dnc2, dnc3, nd(2, 3)).json"]

# --- 전역 객체 (초기화 필요) ---
CONTROLLER_INSTANCE: Optional[Any] = None  # AI2-THOR 컨트롤러
NAV_GRAPH: Optional[Dict] = None  # 네비게이션 그래프
INITIAL_SCENE_POSITIONS: Optional[Dict] = None  # 초기 객체 위치
TASK_PATHS_TO_TUNE: List[Path] = []  # 튜닝에 사용할 태스크 파일 경로 리스트

# --- CSV 로깅 설정 ---
CSV_FILENAME: Path = Path()  # 스터디 생성 후 설정됨
CSV_HEADER = [
    "trial_number",
    "value",
    "state",
    "datetime_start",
    "datetime_complete",
    "duration",
    "param_alpha",
    "param_beta",
    "param_zeta",
    "user_attr_num_completed",
    "user_attr_num_failed",
    "user_attr_avg_completed_makespan",
]

# --- Optuna 목적 함수 페널티 및 임계값 설정 ---
PENALTY_BASE_MAKESPAN = 5000.0  # 유효하지 않은 결과에 대한 기본 페널티 (Makespan 기준)
PENALTY_MULTIPLIER_DEFAULT = 1.5  # 일반 실패 시 페널티 배율
PENALTY_MULTIPLIER_EXEC_FAIL = (
    1.5 * PENALTY_MULTIPLIER_DEFAULT
)  # 실행 실패 시 페널티 배율
PENALTY_MULTIPLIER_TIMEOUT = 1.2 * PENALTY_MULTIPLIER_DEFAULT  # 타임아웃 시 페널티 배율
PENALTY_MULTIPLIER_LOW_SUCCESS = 0.8  # 성공률 낮을 시 페널티 배율
PENALTY_MULTIPLIER_HIGH_COMP_TIME = 0.5  # 계산 시간 길 시 페널티 배율
CRITICAL_FAILURE_PENALTY = 1e10  # 시뮬레이션 함수 자체 오류 시 최대 페널티
MAX_STEPS_PER_TASK = 350  # 태스크 당 최대 시뮬레이션 스텝 수
MIN_SUCCESS_RATE = 1.0  # 유효한 실행으로 간주하기 위한 최소 성공률 (1.0 = 100%)
MAX_COMPUTATION_TIME_PER_TASK = 150.0  # 태스크 당 최대 허용 계산 시간 (초)


# ==============================================================================
# 초기화 및 정리 함수 (Initialization & Cleanup Functions)
# ==============================================================================


def initialize_global_resources():
    """AI2-THOR 컨트롤러, 네비게이션 그래프, 초기 위치, 태스크 목록을 초기화합니다."""
    global CONTROLLER_INSTANCE, NAV_GRAPH, INITIAL_SCENE_POSITIONS, TASK_PATHS_TO_TUNE
    try:
        log.info("--- Initializing Global Resources ---")

        # 1. 컨트롤러 초기화 (이미 있으면 재사용)
        if CONTROLLER_INSTANCE is None:
            CONTROLLER_INSTANCE = init_ai2thor_controller(
                scene=SCENE_NAME, width=300, height=300  # 필요시 설정값 변경
            )
            log.info(f"AI2-THOR controller initialized for scene '{SCENE_NAME}'.")
        else:
            log.info("AI2-THOR controller already initialized.")

        # 2. 네비게이션 그래프 로드 (이미 있으면 재사용)
        if NAV_GRAPH is None:
            NAV_GRAPH = load_navigation_graph(CONTROLLER_INSTANCE)
            log.info("Navigation graph loaded.")
        else:
            log.info("Navigation graph already loaded.")

        # 3. 초기 씬 위치 로드 (이미 있으면 재사용)
        if INITIAL_SCENE_POSITIONS is None:
            positions_file = SCENE_POSITIONS_DIR / f"{SCENE_NAME}_positions.json"
            if not positions_file.exists():
                log.error(f"Scene positions file not found: {positions_file}")
                return False
            INITIAL_SCENE_POSITIONS = load_scene_positions(positions_file)
            log.info(f"Initial scene positions loaded from '{positions_file.name}'.")
        else:
            log.info("Initial scene positions already loaded.")

        # 4. 튜닝 대상 태스크 파일 경로 설정
        TASK_PATHS_TO_TUNE.clear()
        found_tasks_paths = []
        for name in TUNING_TASK_NAMES_LIST:
            task_path = TASK_FILES_DIR / name
            if task_path.is_file():  # 파일인지 확인
                found_tasks_paths.append(task_path)
            else:
                log.warning(
                    f"Specified task file not found or is not a file: {task_path}"
                )

        # 지정된 태스크를 찾지 못한 경우, 폴더 내 다른 태스크 사용 (최대 3개)
        if not found_tasks_paths:
            log.warning(
                f"No specified tasks found. Falling back to first 3 tasks in '{TASK_FILES_DIR}'."
            )
            # glob 대신 Path 객체의 iterdir 사용 권장
            all_available = sorted(
                [p for p in TASK_FILES_DIR.glob("*.json") if p.is_file()]
            )
            found_tasks_paths = all_available[: min(3, len(all_available))]

        TASK_PATHS_TO_TUNE.extend(found_tasks_paths)

        if not TASK_PATHS_TO_TUNE:
            log.error(f"No task files found in '{TASK_FILES_DIR}' to run tuning.")
            return False

        log.info(f"Selected tasks for tuning: {[p.name for p in TASK_PATHS_TO_TUNE]}")
        log.info("--- Global Resources Initialized Successfully ---")
        return True

    except Exception as e:
        log.critical(f"Global resource initialization failed: {e}", exc_info=True)
        return False


def cleanup_resources():
    """AI2-THOR 컨트롤러를 정지시킵니다."""
    global CONTROLLER_INSTANCE
    if CONTROLLER_INSTANCE:
        try:
            CONTROLLER_INSTANCE.stop()
            log.info("AI2-THOR controller stopped.")
            CONTROLLER_INSTANCE = None  # 참조 제거
        except Exception as e:
            log.error(f"Error stopping AI2-THOR controller: {e}")


# ==============================================================================
# 시뮬레이션 실행 관련 함수 (Simulation Runner Functions)
# ==============================================================================


def _initialize_task_state(
    task_path: Path, controller_instance: Any, scene_name: str
) -> Tuple[Optional[SchedulerState], Optional[Dict], str]:
    """태스크 데이터를 로드하고, 컨트롤러를 리셋하며, 초기 SchedulerState를 생성합니다."""
    task_name_str = task_path.stem
    try:
        # 1. 태스크 데이터 로드
        task_data_list = load_task_data_from_file(task_path)  # Path 객체 전달
        if not task_data_list:
            log.error(f"[{task_name_str}] No task data loaded from file.")
            return None, None, task_name_str

        # 2. Subtasks 및 제약조건 그래프 생성
        subtasks, constraints = TaskUtil.build_tasks_and_constraints(
            task_data=task_data_list, enable_decomposition=True  # 필요시 분해 활성화
        )
        log.debug(
            f"[{task_name_str}] Built {len(subtasks)} subtasks and constraint graph with {len(constraints.nodes())} nodes."
        )

        # 3. 컨트롤러 리셋 및 초기 메타데이터 얻기
        event = controller_instance.reset(scene=scene_name)
        if not event:
            log.error(f"[{task_name_str}] Controller reset failed.")
            return None, None, task_name_str
        live_metadata = event.metadata

        # 4. 전역 초기 위치 사용 확인
        if INITIAL_SCENE_POSITIONS is None:
            log.error(f"[{task_name_str}] Initial scene positions not loaded globally.")
            return None, None, task_name_str

        # 5. 초기 상태 생성 (held object 포함)
        live_initial_held_list = live_metadata.get("inventoryObjects", [])
        live_initial_held = (
            live_initial_held_list[0]["objectId"] if live_initial_held_list else None
        )

        # [수정됨] @dataclass 객체 업데이트 방식 변경 (_replace 제거)
        # 새로운 객체를 생성하면서 필요한 필드만 업데이트
        initial_state = SchedulerState(
            subtask=subtasks[0],
            completed_subtasks=[],
            remaining_subtasks=subtasks[1:],
            constraints=constraints,
            current_time=0.0,  # 업데이트할 값
            scene_positions=INITIAL_SCENE_POSITIONS,
            held_object=live_initial_held,  # 업데이트할 값
        )

        log.info(
            f"[{task_name_str}] Initial state created. Time: {initial_state.current_time:.2f}, Remaining: {[s.name for s in initial_state.remaining_subtasks]}"
        )
        return initial_state, task_data_list, task_name_str

    except Exception as e:
        log.error(
            f"[{task_name_str}] Error during task state initialization: {e}",
            exc_info=True,
        )
        return None, None, task_name_str


def _run_simulation_step(
    step_count: int,
    current_state: SchedulerState,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    task_name_str: str,
    result_schedule: List[CompletedEntry],
    simulation_time_accumulator: float,
) -> Tuple[Optional[SchedulerState], List[CompletedEntry], float, bool]:
    """시뮬레이션 루프의 한 스텝을 수행합니다 (스케줄링 -> 실행 -> 상태 업데이트)."""
    log.debug(
        f"[{task_name_str}] --- Step {step_count} --- Current Time: {current_state.current_time:.2f}"
    )
    should_stop_loop = False
    next_state_after_step = None

    try:
        # 1. 스케줄러로부터 다음 상태 얻기
        log.debug(f"[{task_name_str}] Calling scheduler.get_next_state...")
        next_sched_state = scheduler_instance.get_next_state(current_state)

        if next_sched_state is None:
            log.warning(f"Scheduler returned None for '{task_name_str}'.")
            should_stop_loop = True
            # 종료 조건 확인 (남은 태스크 없으면 성공, 있으면 계획 실패)
            next_state_after_step = (
                current_state if not current_state.remaining_subtasks else None
            )
            if next_state_after_step is None:
                log.error(
                    f"[{task_name_str}] Planning failure: Scheduler returned None but tasks remain."
                )
            return (
                next_state_after_step,
                result_schedule,
                simulation_time_accumulator,
                should_stop_loop,
            )

        scheduled_subtask = next_sched_state.subtask
        if not scheduled_subtask or not scheduled_subtask.name:
            log.error(
                f"[{task_name_str}] Invalid subtask from scheduler: {scheduled_subtask}"
            )
            should_stop_loop = True
            return None, result_schedule, simulation_time_accumulator, should_stop_loop

        log.info(
            f"[{task_name_str}] Scheduler selected: '{scheduled_subtask.name}' (Type: {scheduled_subtask.type})"
        )

        # 2. 시뮬레이션에서 Subtask 실행
        log.debug(f"[{task_name_str}] Executing subtask '{scheduled_subtask.name}'...")
        subtask_elapsed_time, execution_status = execute_subtask(
            controller_instance, scheduled_subtask
        )
        subtask_elapsed_time = float(subtask_elapsed_time)  # 타입 보장
        execution_status = bool(execution_status)
        log.info(
            f"[{task_name_str}] Execution: Status={execution_status}, Time={subtask_elapsed_time:.2f}s"
        )

        # 3. 실행 결과로부터 상태 정보 업데이트 (위치, 보유 객체)
        event = controller_instance.last_event
        sim_final_positions = current_state.scene_positions
        sim_final_held = current_state.held_object
        if event and event.metadata and "objects" in event.metadata:
            sim_final_positions = {
                obj["objectId"]: tuple(obj["position"].values())
                for obj in event.metadata.get("objects", [])
                if "position" in obj
            }
            agent_meta = event.metadata.get("agent")
            if agent_meta and "position" in agent_meta:
                sim_final_positions["agent"] = tuple(agent_meta["position"].values())
            elif (
                "agent" in current_state.scene_positions
            ):  # 이전 에이전트 위치 사용 (Fallback)
                sim_final_positions["agent"] = current_state.scene_positions["agent"]

            sim_final_held_list = (
                agent_meta.get("inventoryObjects", []) if agent_meta else []
            )
            sim_final_held = (
                sim_final_held_list[0]["objectId"] if sim_final_held_list else None
            )
            log.debug(f"[{task_name_str}] State after exec: Held='{sim_final_held}'")
        else:
            log.warning(
                f"[{task_name_str}] Invalid metadata after execution. Using previous state info."
            )

        # 4. 실행 결과 기록 (CompletedEntry)
        sim_start_time = simulation_time_accumulator
        sim_end_time = sim_start_time + subtask_elapsed_time
        # subtask 객체에 시뮬레이션 관련 정보 기록 (속성 존재 확인 불필요, dataclass 사용 가정)
        current_completed_entry = CompletedEntry(
            scheduled_subtask, sim_start_time, sim_end_time
        )
        current_completed_entry.subtask.start_time_simulation = sim_start_time
        current_completed_entry.subtask.end_time_simulation = sim_end_time
        current_completed_entry.subtask.execution_status = execution_status
        current_completed_entry.subtask.start_time_scheduled = getattr(
            next_sched_state.subtask, "start_time", None
        )
        current_completed_entry.subtask.end_time_scheduled = getattr(
            next_sched_state.subtask, "end_time", None
        )
        result_schedule.append(current_completed_entry)
        simulation_time_accumulator = sim_end_time

        # 5. 실행 실패 시 루프 중단
        if not execution_status:
            log.error(
                f"[{task_name_str}] Execution failed for '{scheduled_subtask.name}'. Stopping task."
            )
            should_stop_loop = True
            return None, result_schedule, simulation_time_accumulator, should_stop_loop

        # 6. 스케줄러 상태 기반으로 다음 상태 업데이트 (시뮬레이션 시간/결과 반영)
        next_state_after_step = SchedulerState(
            subtask=scheduled_subtask,
            completed_subtasks=result_schedule,
            remaining_subtasks=next_sched_state.remaining_subtasks,
            constraints=next_sched_state.constraints,
            current_time=simulation_time_accumulator,  # 누적된 *시뮬레이션* 시간 사용
            scene_positions=sim_final_positions,  # 시뮬레이션 결과 *위치* 사용
            held_object=sim_final_held,  # 시뮬레이션 결과 *보유 객체* 사용
        )
        log.debug(
            f"[{task_name_str}] State updated. New Time: {next_state_after_step.current_time:.2f}, Remaining: {[s.name for s in next_state_after_step.remaining_subtasks]}"
        )

        # 7. Monitor 태스크인 경우 Agent 업데이트
        if scheduled_subtask.type == "Monitor":
            log.debug(f"[{task_name_str}] Calling agent.bayesian_estimate...")
            try:
                updated_state_agent, monitored_info = agent_instance.bayesian_estimate(
                    next_state_after_step
                )
                next_state_after_step = (
                    updated_state_agent  # 에이전트가 업데이트한 상태 사용
                )
                # 모니터링 정보 기록 (속성 존재 확인 불필요)
                result_schedule[-1].subtask.monitored_subtask = monitored_info
                log.info(
                    f"[{task_name_str}] Agent Bayesian estimation completed. Monitored: {monitored_info}"
                )
            except Exception as agent_e:
                log.error(f"[{task_name_str}] Agent error: {agent_e}", exc_info=True)
                log.warning(f"[{task_name_str}] Continuing without agent update.")

        # 8. 종료 조건 확인 (남은 태스크 없음)
        if not next_state_after_step.remaining_subtasks:
            log.info(
                f"[{task_name_str}] All subtasks completed after step {step_count}."
            )
            should_stop_loop = True

        return (
            next_state_after_step,
            result_schedule,
            simulation_time_accumulator,
            should_stop_loop,
        )

    except Exception as step_e:
        log.error(
            f"[{task_name_str}] Error during simulation step {step_count}: {step_e}",
            exc_info=True,
        )
        return (
            None,
            result_schedule,
            simulation_time_accumulator,
            True,
        )  # 에러 발생 시 루프 중단


def _process_simulation_results(
    result_schedule: List[CompletedEntry],
    task_data_dict: Dict,
    task_name_str: str,
    computation_start_time: float,
    simulation_time_accumulator: float,
    final_status_from_loop: str,
) -> Dict[str, Any]:
    """완료된 스케줄을 처리하고 최종 결과 지표를 반환합니다."""
    total_computation_time = time.time() - computation_start_time

    # 결과가 없는 경우 처리
    if not result_schedule:
        log.warning(f"[{task_name_str}] Simulation ended with no completed entries.")
        return {
            "status": "Failed (No Progress)",
            "simulation_makespan": float("inf"),
            "scheduler_makespan": float("inf"),
            "success_rate": 0.0,
            "computation_time": total_computation_time,
            "scene_name": SCENE_NAME,
            "task_name": task_name_str,
        }

    # compose_plans 호출 및 결과 처리
    task_name_for_compose = task_data_dict.get("Task", task_name_str)
    try:
        plans, success_rate, final_sim_makespan, final_sched_makespan = compose_plans(
            result_schedule, task_name_for_compose
        )
        # Makespan 값이 None일 경우 대체값 사용
        final_sim_makespan = (
            final_sim_makespan
            if final_sim_makespan is not None
            else simulation_time_accumulator
        )
        final_sched_makespan = (
            final_sched_makespan if final_sched_makespan is not None else float("inf")
        )

    except Exception as compose_e:
        log.error(
            f"[{task_name_str}] Error during compose_plans: {compose_e}", exc_info=True
        )
        success_rate = 0.0
        final_sim_makespan = simulation_time_accumulator
        final_sched_makespan = float("inf")
        final_status_from_loop = "Failed (Result Processing Error)"  # 상태 덮어쓰기

    # 최종 결과 딕셔너리 생성
    result_dict = {
        "simulation_makespan": (
            final_sim_makespan if final_sim_makespan > 0 else float("inf")
        ),
        "scheduler_makespan": (
            final_sched_makespan if final_sched_makespan > 0 else float("inf")
        ),
        "success_rate": success_rate,
        "computation_time": total_computation_time,
        "scene_name": SCENE_NAME,
        "task_name": task_name_str,
        "status": final_status_from_loop,  # 루프 종료 시 결정된 상태 사용
    }
    log.info(
        f"--- Sim finished: '{task_name_str}' --- Status: {result_dict['status']}, "
        f"SimMakespan: {result_dict['simulation_makespan']:.2f}, Rate: {result_dict['success_rate']:.2f}, "
        f"CompTime: {result_dict['computation_time']:.2f}s"
    )
    return result_dict


# --- 주 시뮬레이션 실행 함수 ---
def run_schedule_and_get_result(
    task_path: Path,
    scheduler_instance: Scheduler,
    agent_instance: Agent,
    controller_instance: Any,
    scene_name: str,
    initial_scene_positions_run: Dict,  # 파라미터 유지 (일관성)
) -> Optional[Dict[str, Any]]:
    """단일 태스크에 대한 전체 시뮬레이션 루프를 실행하고 결과를 반환합니다."""
    computation_start_time = time.time()
    simulation_time_accumulator = 0.0
    result_schedule: List[CompletedEntry] = []
    final_status = "Unknown"  # 루프 종료 시 결정될 최종 상태

    try:
        # 1. 태스크 상태 초기화
        current_state, task_data_dict, task_name_str = _initialize_task_state(
            task_path, controller_instance, scene_name
        )
        if current_state is None or task_data_dict is None:
            log.error(
                f"[{task_name_str or task_path.stem}] Failed to initialize task state."
            )
            # 초기화 실패 시 즉시 실패 결과 반환
            return {
                "status": "Failed (Initialization)",
                "simulation_makespan": float("inf"),
                "scheduler_makespan": float("inf"),
                "success_rate": 0.0,
                "computation_time": time.time() - computation_start_time,
                "scene_name": scene_name,
                "task_name": task_name_str or task_path.stem,
            }

        log.info(f"--- Starting Sim: '{task_name_str}' ---")

        # 2. 시뮬레이션 루프 실행
        step_count = 0
        stop_loop = False
        while not stop_loop:
            step_count += 1
            # 최대 스텝 수 초과 확인
            if step_count > MAX_STEPS_PER_TASK:
                log.error(
                    f"[{task_name_str}] Max steps ({MAX_STEPS_PER_TASK}) exceeded."
                )
                final_status = "Failed (Timeout)"
                break  # 타임아웃 시 루프 종료

            # 단일 스텝 실행
            current_state, result_schedule, simulation_time_accumulator, stop_loop = (
                _run_simulation_step(
                    step_count,
                    current_state,
                    scheduler_instance,
                    agent_instance,
                    controller_instance,
                    task_name_str,
                    result_schedule,
                    simulation_time_accumulator,
                )
            )

            # 스텝 실행 중 에러 발생 또는 종료 조건 충족 시
            if stop_loop:
                if current_state is None:  # 에러 발생
                    # 마지막 실행 결과 기반으로 상태 추론
                    if (
                        result_schedule
                        and not result_schedule[-1].subtask.execution_status
                    ):
                        final_status = "Failed (Execution)"
                    else:
                        final_status = "Failed (Planning/State Error)"
                elif not current_state.remaining_subtasks:  # 정상 종료
                    final_status = "Completed"
                # 다른 이유로 stop_loop=True 가 된 경우 (e.g., 스케줄러가 None 반환하고 태스크 남음)
                elif final_status == "Unknown":
                    final_status = "Failed (Planning Error)"  # 기본 계획 에러로 설정

                break  # 에러 또는 정상 종료 시 루프 탈출

        # 3. 결과 처리 및 반환
        return _process_simulation_results(
            result_schedule,
            task_data_dict,
            task_name_str,
            computation_start_time,
            simulation_time_accumulator,
            final_status,
        )

    except Exception as main_run_e:
        # _initialize_task_state 또는 _process_simulation_results 등에서 발생할 수 있는 예외 처리
        log.critical(
            f"[{task_path.stem}] Critical error in main simulation runner: {main_run_e}",
            exc_info=True,
        )
        return None  # 심각한 오류 시 None 반환


# ==============================================================================
# Optuna 관련 함수 및 클래스 (Optuna Related Functions & Classes)
# ==============================================================================


class CSVSaveCallback:
    """Optuna 트라이얼 결과를 CSV 파일에 저장하는 콜백 클래스."""

    def __init__(self, csv_path: Path, header: List[str]):
        self.csv_path = csv_path
        self.header = header
        self._header_written = False  # 헤더 작성 여부 플래그
        # 멀티 프로세싱(n_jobs > 1) 사용 시 Lock 필요
        # import threading
        # self.lock = threading.Lock()

    def _ensure_header(self) -> bool:
        """CSV 파일 헤더가 존재하도록 보장합니다. 없으면 새로 씁니다."""
        # with self.lock: # n_jobs > 1 일 경우 사용
        if not self._header_written:
            write_header = False
            if not self.csv_path.exists():
                write_header = True  # 파일 없으면 쓰기
            elif self.csv_path.stat().st_size == 0:
                write_header = True  # 파일 비어있으면 덮어쓰기

            if write_header:
                try:
                    with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(self.header)
                    self._header_written = True
                    log.info(
                        f"Initialized/Wrote header to CSV log file: {self.csv_path}"
                    )
                except IOError as e:
                    log.error(f"Failed to write header to CSV log file: {e}")
                    return False  # 헤더 쓰기 실패
            else:
                # 파일이 존재하고 비어있지 않으면 헤더가 있는 것으로 간주
                self._header_written = True
        return True  # 헤더 존재 또는 쓰기 성공

    def __call__(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial):
        """완료된 트라이얼 데이터를 CSV 파일에 추가합니다."""
        if not self._ensure_header():
            log.warning(
                f"Skipping CSV write for trial {trial.number} due to header issue."
            )
            return

        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # 데이터 행 준비 (None, NaN, Inf 값 처리)
                value_str = ""
                if (
                    trial.value is not None
                    and not math.isnan(trial.value)
                    and not math.isinf(trial.value)
                ):
                    value_str = trial.value

                state_str = trial.state.name
                dt_start_str = (
                    trial.datetime_start.isoformat() if trial.datetime_start else ""
                )
                dt_complete_str = (
                    trial.datetime_complete.isoformat()
                    if trial.datetime_complete
                    else ""
                )
                duration_str = trial.duration.total_seconds() if trial.duration else ""

                # 파라미터 및 사용자 속성 안전하게 가져오기
                params = trial.params
                user_attrs = trial.user_attrs
                avg_makespan = user_attrs.get("avg_completed_makespan", "")
                if avg_makespan == float("inf") or avg_makespan is None:
                    avg_makespan = ""  # Inf/None은 빈 문자열로

                # [수정됨] CSV 행 생성 시 파라미터 이름 변경 (zeta 사용, gamma/delta 제거)
                row = [
                    trial.number,
                    value_str,
                    state_str,
                    dt_start_str,
                    dt_complete_str,
                    duration_str,
                    params.get("alpha", ""),
                    params.get("beta", ""),
                    params.get("zeta", ""),
                    user_attrs.get("num_completed", ""),
                    user_attrs.get("num_failed", ""),
                    avg_makespan,
                ]
                writer.writerow(row)
        except IOError as e:
            log.error(f"Failed to append trial {trial.number} to CSV: {e}")
        except Exception as e:
            log.error(
                f"Unexpected error writing trial {trial.number} to CSV: {e}",
                exc_info=True,
            )


def _run_single_task_for_trial(
    task_path: Path, trial_number: int, params: Dict[str, float]
) -> Optional[Dict[str, Any]]:
    """주어진 하이퍼파라미터로 단일 태스크 시뮬레이션을 실행합니다."""
    # 전역 리소스 확인
    if (
        CONTROLLER_INSTANCE is None
        or NAV_GRAPH is None
        or INITIAL_SCENE_POSITIONS is None
    ):
        log.error(f"T{trial_number}, Task {task_path.stem}: Global resources missing.")
        return None  # 실패 반환

    try:
        # [수정됨] 핸들러 인스턴스 생성 및 주입 (dag_bayesian.py와 동일하게)
        action_handler = ActionHandler(NAV_GRAPH)
        constraint_handler = ConstraintHandler(action_handler)
        # [수정됨] HeuristicManager 생성 시 params 전달 (가중치 설정용)
        heuristic_manager = HeuristicManager(constraint_handler, action_handler)
        # HeuristicManager 인스턴스에 현재 trial의 파라미터 설정
        # (주의: HeuristicManager가 파라미터를 업데이트하는 메소드를 제공하거나,
        #  __init__에서 받을 수 있도록 수정 필요. 여기서는 멤버 직접 설정 가정)
        heuristic_manager.alpha = params.get("alpha", 1.0)
        heuristic_manager.beta = params.get("beta", 1.5)
        heuristic_manager.zeta = params.get("zeta", 0.1)
        log.debug(
            f"T{trial_number} Heuristic weights set: a={heuristic_manager.alpha:.3f}, b={heuristic_manager.beta:.3f}, z={heuristic_manager.zeta:.3f}"
        )

        # [수정됨] Agent 생성 시 ConstraintHandler 주입
        agent = Agent(constraint_handler=constraint_handler)

        # 스케줄러 생성
        scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, NAV_GRAPH)
        # [수정됨] Scheduler 내부 핸들러/계산기 설정
        scheduler.action_handler = action_handler
        scheduler.constraint_handler = constraint_handler
        scheduler.cost_calculator = (
            heuristic_manager  # 업데이트된 가중치를 가진 인스턴스
        )

        # 시뮬레이션 실행
        task_result = run_schedule_and_get_result(
            task_path,
            scheduler,
            agent,
            CONTROLLER_INSTANCE,
            SCENE_NAME,
            INITIAL_SCENE_POSITIONS,
        )
        return task_result

    except Exception as e:
        # 태스크 처리 중 심각한 오류 발생 시
        log.critical(
            f"Critical error processing task {task_path.stem} in trial {trial_number}: {e}",
            exc_info=True,
        )
        # 실패 정보를 담은 딕셔너리 반환
        return {
            "task_name": task_path.stem,
            "status": "Critical Failure in Trial Loop",
            "simulation_makespan": float("inf"),
            "scheduler_makespan": float("inf"),
            "success_rate": 0.0,
            "computation_time": 0.0,
            "scene_name": SCENE_NAME,
        }


def _calculate_task_objective(
    task_result: Dict, trial_number: int, task_name: str
) -> Tuple[float, bool]:
    """단일 태스크 결과에 대한 목적 함수 값(페널티 포함)을 계산합니다."""
    penalty = 0.0
    # 결과 딕셔너리에서 값 추출 (없으면 기본값 사용)
    sim_makespan = task_result.get("simulation_makespan", float("inf"))
    success_rate = task_result.get("success_rate", 0.0)
    computation_time = task_result.get("computation_time", float("inf"))
    status = task_result.get("status", "Failed")  # 상태 없으면 실패로 간주

    is_valid_run = True  # 실행이 유효했는지 (페널티 없는지)

    # 페널티 조건 확인
    if status != "Completed":
        log.warning(
            f"T{trial_number}, Task {task_name}: Invalid - Status '{status}'. Applying penalty."
        )
        # 실패 유형별 페널티 차등 적용
        if status == "Failed (Execution)":
            penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_EXEC_FAIL
        elif status == "Failed (Timeout)":
            penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_TIMEOUT
        else:
            penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_DEFAULT  # 그 외 실패
        is_valid_run = False
    elif success_rate < MIN_SUCCESS_RATE:
        log.warning(
            f"T{trial_number}, Task {task_name}: Invalid - Rate {success_rate:.2f} < {MIN_SUCCESS_RATE}. Applying penalty."
        )
        penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_LOW_SUCCESS
        is_valid_run = False
    elif computation_time > MAX_COMPUTATION_TIME_PER_TASK:
        log.warning(
            f"T{trial_number}, Task {task_name}: Invalid - CompTime {computation_time:.2f}s > {MAX_COMPUTATION_TIME_PER_TASK}s. Applying penalty."
        )
        penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_HIGH_COMP_TIME
        is_valid_run = False
    elif sim_makespan == float("inf") or sim_makespan is None:
        # 'Completed' 상태지만 makespan이 유효하지 않은 경우 (엣지 케이스)
        log.warning(
            f"T{trial_number}, Task {task_name}: Invalid - Makespan is Inf/None despite 'Completed' status. Applying penalty."
        )
        penalty = PENALTY_BASE_MAKESPAN * PENALTY_MULTIPLIER_DEFAULT
        is_valid_run = False

    # 최종 목적 함수 값 계산: 유효하면 makespan, 아니면 기본 페널티 + 추가 페널티
    # makespan이 inf/None인 경우도 기본 페널티 적용
    current_task_objective = (
        sim_makespan
        if is_valid_run and sim_makespan != float("inf")
        else PENALTY_BASE_MAKESPAN
    ) + penalty

    return current_task_objective, is_valid_run


def objective(trial: optuna.Trial) -> float:
    """Optuna 목적 함수: 모든 튜닝 태스크에 대해 시뮬레이션을 실행하고 평균 목적 함수 값을 계산합니다."""
    # [수정됨] 하이퍼파라미터 제안 (alpha, beta, zeta) 및 범위 조정
    params = {
        "alpha": trial.suggest_float(
            "alpha", 0.1, 5.0, log=False
        ),  # 이동 시간 영향력 (log scale 제거 고려)
        "beta": trial.suggest_float(
            "beta", 0.1, 5.0, log=False
        ),  # 긴급도 영향력 (log scale 제거 고려)
        "zeta": trial.suggest_float(
            "zeta", 0.01, 2.0, log=False
        ),  # 남은 작업량 영향력 (범위 조정 필요)
        # "gamma", "delta" 제거
    }
    # [수정됨] 로그 메시지 업데이트
    log.info(
        f"\n--- Starting Trial {trial.number} | Params: "
        f"a={params['alpha']:.3f}, b={params['beta']:.3f}, z={params['zeta']:.3f} ---"
    )

    # 집계 변수 초기화
    total_objective_value = 0.0
    num_completed_tasks = 0
    num_failed_tasks = 0
    task_results_for_trial = []  # 개별 태스크 결과 저장용

    # 튜닝 대상 태스크 목록 확인
    if not TASK_PATHS_TO_TUNE:
        log.error("No tasks loaded for tuning. Returning infinite objective.")
        # Optuna는 float 반환 필요, 실패 시 큰 값 반환
        return float("inf")

    # 2. 각 태스크에 대해 시뮬레이션 실행 및 결과 집계
    for task_path in TASK_PATHS_TO_TUNE:
        task_result = _run_single_task_for_trial(task_path, trial.number, params)

        if task_result is None:  # 시뮬레이션 함수 자체에서 심각한 오류 발생
            log.error(
                f"T{trial.number}, Task {task_path.stem}: Simulation function failed critically. Max penalty."
            )
            total_objective_value += CRITICAL_FAILURE_PENALTY
            num_failed_tasks += 1
            task_results_for_trial.append(
                {"task_name": task_path.stem, "status": "Critical Failure"}
            )
            continue  # 다음 태스크로

        # 태스크 결과 저장 및 목적 함수 값 계산
        task_results_for_trial.append(task_result)
        task_objective, is_valid = _calculate_task_objective(
            task_result, trial.number, task_path.stem
        )
        total_objective_value += task_objective

        if is_valid:
            num_completed_tasks += 1
        else:
            num_failed_tasks += 1

    # 3. 최종 평균 목적 함수 값 계산
    num_tasks_run = len(TASK_PATHS_TO_TUNE)
    average_objective_value = (
        total_objective_value / num_tasks_run if num_tasks_run > 0 else float("inf")
    )

    # 4. 사용자 정의 속성 설정 (로깅 및 분석용)
    trial.set_user_attr("num_completed", num_completed_tasks)
    trial.set_user_attr("num_failed", num_failed_tasks)
    # 성공한 태스크들의 평균 makespan 계산
    completed_makespans = [
        res.get("simulation_makespan")
        for res in task_results_for_trial
        if res.get("status") == "Completed"
        and res.get("simulation_makespan") not in [None, float("inf")]
    ]
    avg_completed_makespan = (
        sum(completed_makespans) / len(completed_makespans)
        if completed_makespans
        else float("inf")
    )
    trial.set_user_attr("avg_completed_makespan", avg_completed_makespan)
    # 실패한 태스크 목록 저장 (JSON 문자열)
    failed_task_names = [
        res.get("task_name", "Unknown")
        for res in task_results_for_trial
        if res.get("status") != "Completed"
    ]
    try:
        trial.set_user_attr("failed_tasks", json.dumps(failed_task_names))
    except TypeError:  # JSON 직렬화 실패 시
        trial.set_user_attr("failed_tasks", "Error serializing failed tasks")

    log.info(
        f"Trial {trial.number} finished. Avg Objective: {average_objective_value:.2f} "
        f"(Completed OK: {num_completed_tasks}, Failed/Penalized: {num_failed_tasks} / Total: {num_tasks_run})"
        f" Avg Makespan (Completed): {avg_completed_makespan:.2f}"
    )

    # 5. Pruning 및 결과 보고
    # Optuna는 float 반환 필요, NaN/Inf 등 처리
    if (
        average_objective_value is None
        or math.isnan(average_objective_value)
        or math.isinf(average_objective_value)
    ):
        log.warning(
            f"Trial {trial.number}: Invalid objective value ({average_objective_value}). Reporting large value."
        )
        return 1e12  # 매우 큰 값 반환
    else:
        trial.report(average_objective_value, step=0)  # Optuna에 값 보고
        if trial.should_prune():
            log.info(f"Trial {trial.number} pruned.")
            raise optuna.TrialPruned()  # Pruning 예외 발생

    return average_objective_value


# ==============================================================================
# Optuna 스터디 실행 및 메인 로직 (Optuna Study Execution & Main Logic)
# ==============================================================================


def run_optuna_study(n_trials: int, timeout_seconds: Optional[int]):
    """Optuna 하이퍼파라미터 튜닝 스터디를 설정하고 실행합니다."""
    global CSV_FILENAME  # 전역 변수 수정 허용

    # 1. 전역 리소스 초기화 확인
    if not initialize_global_resources():
        log.critical("Exiting due to resource initialization failure.")
        return

    # 2. 스터디 및 저장소 설정
    start_time = time.time()
    study_name = f"scheduler_tuning_{SCENE_NAME}_{time.strftime('%Y%m%d_%H%M%S')}"
    storage_name = f"sqlite:///{study_name}.db"  # SQLite 데이터베이스 사용

    # 3. CSV 콜백 설정
    CSV_FILENAME = Path(f"{study_name}_results.csv")
    csv_callback = CSVSaveCallback(CSV_FILENAME, CSV_HEADER)
    if not csv_callback._ensure_header():  # 스터디 시작 전 헤더 확인/생성
        log.error("Failed to ensure CSV header. CSV logging might fail.")

    # 4. Optuna 스터디 생성 또는 로드
    log.info(f"Creating/Loading Optuna study: '{study_name}' Storage: '{storage_name}'")
    try:
        study = optuna.create_study(
            study_name=study_name,
            storage=storage_name,
            direction="minimize",  # 목적 함수 최소화
            sampler=optuna.samplers.TPESampler(
                seed=42, n_startup_trials=20, multivariate=True
            ),  # 샘플러 설정
            pruner=optuna.pruners.MedianPruner(
                n_startup_trials=20, n_warmup_steps=0, interval_steps=1
            ),  # 프루너 설정
            load_if_exists=True,  # 기존 스터디 있으면 로드
        )
    except Exception as e:
        log.critical(f"Failed to create or load Optuna study: {e}", exc_info=True)
        return

    # 5. 최적화 실행
    log.info(
        f"Starting optimization with {n_trials} trials (timeout={timeout_seconds}s)..."
    )
    try:
        study.optimize(
            objective,  # 목적 함수
            n_trials=n_trials,  # 최대 트라이얼 수
            timeout=timeout_seconds,  # 최대 실행 시간 (초)
            gc_after_trial=True,  # 트라이얼 후 가비지 컬렉션
            n_jobs=1,  # 병렬 실행 수 (1로 설정하여 리소스 경합 방지)
            callbacks=[csv_callback],  # CSV 저장 콜백 전달
        )
    except KeyboardInterrupt:
        log.warning("Optimization interrupted by user.")
    except optuna.exceptions.TrialPruned as e:
        # Pruned 예외는 정상적인 종료일 수 있으므로 info 레벨로 로깅
        log.info(f"Pruning stopped optimization early: {e}")
    except Exception as e:
        log.error(f"Optimization loop failed unexpectedly: {e}", exc_info=True)

    # 6. 튜닝 완료 후 결과 분석 및 출력
    end_time = time.time()
    log.info(f"\n--- Tuning Completed (Total Time: {end_time - start_time:.2f}s) ---")
    _analyze_and_print_results(study, study_name)


def _analyze_and_print_results(study: optuna.study.Study, study_name: str):
    """완료된 Optuna 스터디 결과를 분석하고 로그로 출력하며, 최종 데이터프레임을 저장합니다."""
    try:
        # 트라이얼 상태별 개수 집계
        pruned_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.PRUNED]
        )
        complete_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.COMPLETE]
        )
        fail_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.FAIL]
        )
        waiting_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.WAITING]
        )
        running_trials = study.get_trials(
            deepcopy=False, states=[optuna.trial.TrialState.RUNNING]
        )

        log.info(f"Study statistics for '{study_name}':")
        log.info(f"  Total trials: {len(study.trials)}")
        log.info(f"  Complete trials: {len(complete_trials)}")
        log.info(f"  Pruned trials: {len(pruned_trials)}")
        log.info(f"  Failed trials: {len(fail_trials)}")
        log.info(f"  Waiting trials: {len(waiting_trials)}")
        log.info(f"  Running trials: {len(running_trials)}")

        # 최적 트라이얼 정보 출력 (Complete 상태 트라이얼 있을 경우)
        if complete_trials:
            best_trial = study.best_trial
            log.info("Best trial found:")
            log.info(f"  Trial number: {best_trial.number}")
            log.info(f"  Value (Avg Objective): {best_trial.value:.4f}")
            log.info("  Best Params:")
            for key, value in best_trial.params.items():
                log.info(f"    {key}: {value:.4f}")
            log.info("  User Attributes for Best Trial:")
            for key, value in best_trial.user_attrs.items():
                # 긴 문자열 (e.g., failed_tasks JSON) 처리
                display_value = value
                if isinstance(value, str) and len(value) > 100:
                    display_value = value[:100] + "..."
                log.info(f"    {key}: {display_value}")
        else:
            log.warning(
                "No trials completed successfully. Cannot determine best trial."
            )

    except Exception as analysis_e:
        log.error(f"Error during results analysis: {analysis_e}", exc_info=True)

    # 최종 결과 데이터프레임 CSV 저장
    try:
        df = study.trials_dataframe(
            attrs=(
                "number",
                "value",
                "params",
                "state",
                "user_attrs",
                "datetime_start",
                "datetime_complete",
                "duration",
            )
        )
        # 콜백 CSV와 다른 이름 사용
        final_csv_filename = Path(f"{study_name}_final_dataframe.csv")
        df.to_csv(final_csv_filename, index=False, encoding="utf-8")
        log.info(f"Final tuning results dataframe saved to '{final_csv_filename}'")
    except Exception as e:
        log.error(f"Failed to save final tuning results dataframe: {e}")


if __name__ == "__main__":
    # --- 튜닝 실행 설정 ---
    # 튜닝할 트라이얼 수 (디버깅 시 작게 설정, 실제 튜닝 시 크게 설정)
    N_TRIALS_TO_RUN = 1
    # 최대 튜닝 시간 (초), None이면 시간 제한 없음
    TIMEOUT_TUNING_SECONDS = 3600 * 24 * 2  # 예: 2일

    # --- 메인 실행 ---
    try:
        # Optuna 스터디 실행
        run_optuna_study(
            n_trials=N_TRIALS_TO_RUN, timeout_seconds=TIMEOUT_TUNING_SECONDS
        )
    except Exception as main_e:
        # run_optuna_study 내부에서 처리되지 않은 최상위 예외
        log.critical(
            f"An unhandled error occurred during the tuning process: {main_e}",
            exc_info=True,
        )
    finally:
        # --- 리소스 정리 ---
        # 스크립트 종료 시 항상 컨트롤러 정지 시도
        cleanup_resources()
        log.info("--- Tuning Script Finished ---")
