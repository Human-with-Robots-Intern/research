import argparse
import math
import time
from collections import deque
from typing import List, Optional

from core.agent import Agent
from core.scheduler import Scheduler
from ithor.handlers.navigation_handler import load_navigation_graph
from scheduler.action_handler import ActionHandler
from scheduler.constraint_handler import ConstraintHandler
from scheduler.heuristic_manager import HeuristicManager
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.utils.common import create_module_logger
from src.utils.config import (
    BEAM_WIDTH,
    LOG_ROUND,
    SAVE_KNOWLEDGE_ON_EXIT,
    SCENE_NAME,
    SIMULATION_DEPTH,
)
from src.utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
    result_save,
)
from src.utils.task import TaskUtil
from src.utils.visualizers import visualize

log = create_module_logger(module_name=__name__, module_log=True)

# --- 추가: 설정값 로드 (config 파일 사용 권장 주석 추가) ---
# TODO: Move these constants to config.py for better management
MAX_LOOPS = 2000
DEADLOCK_THRESHOLD = 5
RETRY_COUNT = 2  # 예시: 재시도 횟수
RETRY_DELAY = 1  # 예시: 재시도 간격(초)
# --- 추가 끝 ---


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

    parser.add_argument(
        "-d",
        "--decomposition",
        help="Enable or disable decomposition",
        default=True,
        action="store_true",
    )

    parser.add_argument(
        "-r",
        "--reset",
        default=True,
        help="Reset the knowledge base to Gaussian",
        action="store_true",
    )

    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    approach_name = "dag_bayesian"

    # Set up the AI2-THOR controller and navigation graph
    try:
        controller = init_ai2thor_controller()
        nav_graph = load_navigation_graph(controller)
        scene_poses = load_scene_positions(f"{SCENE_NAME}_positions.json")
    except FileNotFoundError as e_load:
        log.critical(
            f"Failed to load navigation graph or scene positions: {e_load}. Aborting."
        )
        return
    except Exception as e_init_thor:
        log.critical(
            f"Error during AI2THOR setup: {e_init_thor}. Aborting.", exc_info=True
        )
        return

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)

    # task_file_name을 입력 자연어로 번역
    input_natural_language = (
        get_natural_language_from_task_file(f"{choice}")
        if choice is not None
        else task_file_name
    )

    # Build tasks and constraints
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, args.decomposition
    )

    # 핸들러 및 Agent 인스턴스 생성
    action_handler = ActionHandler(nav_graph or {})
    constraint_handler = ConstraintHandler(action_handler)
    agent = Agent(
        constraint_handler=None
    )  # Scheduler가 내부 ConstraintHandler 사용 가정 시 None 전달? 또는 별도 생성? -> 구조 확인 필요
    # agent 초기화에 constraint_handler가 필수라면, Scheduler 내부 인스턴스 접근 방법 필요 (현재 불가)
    # Placeholder: agent 초기화 방식 원본 코드 확인 필요
    log.warning(
        "Agent initialization might need adjustment depending on ConstraintHandler dependency and Scheduler structure."
    )

    # HeuristicManager 생성 (Agent의 knowledge 사용 위해 agent 주입)
    heuristic_manager = HeuristicManager(
        constraint_handler, action_handler, agent=agent
    )

    # Scheduler 인스턴스 생성 (핸들러들 주입)
    scheduler = Scheduler(
        search_width=BEAM_WIDTH,
        simulation_depth=SIMULATION_DEPTH,
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=heuristic_manager,
    )
    log.info("Scheduler initialized using internal handlers.")
    # *** 경고 ***: Scheduler 내부의 HeuristicManager는 여기서 생성된 agent의 지식에 접근하지 못할 수 있음.
    log.warning(
        "Scheduler's internal HeuristicManager likely cannot access Agent knowledge updates."
    )

    # 초기 상태 생성
    try:
        current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)
    except Exception as e_init_state:
        log.critical(
            f"Failed to create initial state: {e_init_state}. Aborting.", exc_info=True
        )
        return

    # Visualize the task graph if enabled
    visualize(approach_name, input_natural_language, constraints)
    result_schedule = []
    is_end = False
    task_failed = False
    failure_reason = ""
    potential_failed_entry = None
    last_successful_entry = None
    loop_count = 0
    computation_time = 0
    simulation_time = 0

    # 교착 상태 감지를 위한 변수 (deque 사용)
    # 최근 DEADLOCK_THRESHOLD + 1 개의 상태 요약만 저장하여 메모리 사용량 제한
    previous_states_summary = deque(maxlen=DEADLOCK_THRESHOLD + 1)
    consecutive_same_state_count = 0

    log.info("Starting main execution loop...")
    while not is_end and not task_failed and loop_count < MAX_LOOPS:
        loop_count += 1
        log.debug(
            f"--- Main Loop Iteration {loop_count}/{MAX_LOOPS} | Time: {current_state.current_time:.2f} ---"
        )

        computation_time_start = time.time()
        # --- 수정: 상태 요약에 scene_positions 및 held_object 추가 ---
        # scene_positions 딕셔너리를 정렬된 (키, (좌표 튜플)) 튜플로 변환하여 해시 가능하게 만듦
        # scene_positions의 값은 딕셔너리({'position': [...]}) 또는 리스트/튜플일 수 있음
        scene_positions_summary = tuple(
            sorted(
                (
                    k,
                    # 값의 타입에 따라 처리: 딕셔너리이면 position 키 참조, 리스트/튜플이면 튜플 변환, 아니면 값 자체 사용
                    (
                        tuple(v["position"])
                        if isinstance(v, dict) and "position" in v
                        else tuple(v) if isinstance(v, (list, tuple)) else v
                    ),
                )
                for k, v in current_state.scene_positions.items()
            )
        )
        current_state_summary = (
            tuple(sorted([ce.subtask.name for ce in current_state.completed_subtasks])),
            tuple(sorted([r.name for r in current_state.remaining_subtasks])),
            scene_positions_summary,  # 씬 상태 요약 추가
            current_state.held_object,  # 들고 있는 객체 추가
        )
        # --- 수정 끝 ---

        # --- 교착 상태 확인 ---
        # WARNING: Exact state summary comparison might be sensitive to float precision in scene_positions.
        current_matching_previous_state = None
        for prev_summary, prev_time in previous_states_summary:
            if (
                current_state_summary == prev_summary  # 확장된 요약 비교
                and math.isclose(
                    current_state.current_time,
                    prev_time,
                    rel_tol=1e-5,  # 상대 허용 오차
                    abs_tol=1e-5,  # 절대 허용 오차
                )
            ):
                current_matching_previous_state = (prev_summary, prev_time)
                break

        if current_matching_previous_state:
            consecutive_same_state_count += 1
            log.warning(
                f"Consecutive identical state detected ({consecutive_same_state_count}/{DEADLOCK_THRESHOLD}). "
                f"State repeated {consecutive_same_state_count} times. Time: {current_state.current_time:.3f}"
            )
            if consecutive_same_state_count >= DEADLOCK_THRESHOLD:
                log.error(
                    f"Deadlock detected: State repeated {DEADLOCK_THRESHOLD} times. Aborting."
                )
                task_failed = True
                failure_reason = "Deadlock detected (state repeating)."
                break
        else:
            consecutive_same_state_count = 0  # 상태 변경 시 카운터 리셋

        # 현재 상태 기록 (요약 + 시간)
        previous_states_summary.append(
            (current_state_summary, current_state.current_time)
        )
        # --- 수정 끝 ---\
        # --- 교착 상태 확인 끝 ---\

        # 다음 상태 결정 (Scheduler 호출)
        computation_time_start = time.time()
        next_state = scheduler.get_next_state(current_state)
        computation_time += time.time() - computation_time_start

        if next_state is None:
            log.error(f"Scheduler could not find a feasible next state. Aborting.")
            task_failed = True
            failure_reason = "Scheduler failed to find a feasible next state."
            break

        # --- 수정: next_state가 반환되었으므로, 이것이 다음 시도될 태스크 ---
        # 이 태스크가 실행/시뮬레이션 후 실패할 수 있으므로 potential_failed_entry로 설정
        potential_failed_entry = (
            next_state.completed_subtasks[-1] if next_state.completed_subtasks else None
        )
        # --- 수정 끝 ---

        actual_subtask_time = 0.0
        actual_execution_status = False
        executed_subtask = next_state.subtask if next_state else None
        if not executed_subtask:
            log.error("Scheduler returned state without subtask. Aborting.")
            task_failed = True
            failure_reason = "Invalid state from scheduler (no subtask)."
            break

        log.info(f"Attempting to execute subtask: '{executed_subtask.name}'")
        execution_exception = None
        for attempt in range(RETRY_COUNT + 1):
            try:
                actual_subtask_time, actual_execution_status = execute_subtask(
                    controller, executed_subtask
                )
                log.info(
                    f"  Attempt {attempt+1}: Duration={actual_subtask_time:.2f}, Status={'Success' if actual_execution_status else 'Failure'}"
                )
                if actual_execution_status:
                    break
                if attempt < RETRY_COUNT:
                    log.warning(f"    Execution failed. Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
            except Exception as e_exec:
                log.error(
                    f"  Exception during execution (Attempt {attempt+1}): {e_exec}",
                    exc_info=True,
                )
                execution_exception = e_exec
                actual_execution_status = False
                break

        if not actual_execution_status:
            log.error(
                f"Subtask '{executed_subtask.name}' execution FAILED after {RETRY_COUNT+1} attempts."
            )
            task_failed = True
            failure_reason = f"Subtask '{executed_subtask.name}' failed execution."
            if execution_exception:
                failure_reason += f" Reason: {execution_exception}"
            break

        log.info(f"Subtask '{executed_subtask.name}' executed successfully.")
        completed_task_entry = potential_failed_entry
        if completed_task_entry:
            try:
                completed_task_entry.start_time = current_state.current_time
                completed_task_entry.end_time = (
                    current_state.current_time + actual_subtask_time
                )
                setattr(
                    completed_task_entry.subtask,
                    "duration.interval",
                    actual_subtask_time,
                )
                setattr(completed_task_entry.subtask, "execution_status", True)
                last_successful_entry = completed_task_entry
            except Exception as e_entry_update:
                log.error(f"Error updating completed entry data: {e_entry_update}")
        else:
            log.error(
                "Internal inconsistency: completed_task_entry is None after success."
            )
            task_failed = True
            failure_reason = "Internal error after execution."
            break

        if executed_subtask.type == "Monitor":
            try:
                log.info(
                    f"Performing Bayesian estimation for Monitor task: '{executed_subtask.name}'"
                )
                _, monitored_subtask_info = agent.bayesian_estimate(next_state)
                if monitored_subtask_info:
                    log.info(
                        f"  Bayesian estimation successful. Info: {monitored_subtask_info}"
                    )
                else:
                    log.warning("  Bayesian estimation did not return update info.")
            except ValueError as e_bayes_val:
                log.error(
                    f"CRITICAL error during Bayesian estimation: {e_bayes_val}. Aborting."
                )
                task_failed = True
                failure_reason = f"Critical Bayesian estimation error: {e_bayes_val}"
                break
            except Exception as e_bayes_generic:
                log.error(
                    f"Unexpected error during Bayesian estimation: {e_bayes_generic}. Continuing without update.",
                    exc_info=True,
                )

        actual_end_time = current_state.current_time + actual_subtask_time
        log.warning(
            "Updating current_time based on actual execution, but using predicted scene state from scheduler. Accuracy depends on simulation fidelity."
        )
        try:
            if hasattr(next_state, "_replace"):
                current_state = next_state._replace(current_time=actual_end_time)
            elif hasattr(next_state, "__dict__"):
                current_state = next_state
                current_state.current_time = actual_end_time
            else:
                raise TypeError(
                    f"Cannot update time for next_state of type {type(next_state)}"
                )
        except Exception as e_state_update:
            log.error(
                f"Error updating current state after execution: {e_state_update}. State might be inconsistent.",
                exc_info=True,
            )
            task_failed = True
            failure_reason = "Internal error: Failed to update state after execution."
            break

        if not current_state.remaining_subtasks:
            log.info("All subtasks completed.")
            is_end = True

        if loop_count >= MAX_LOOPS:
            log.error(f"Maximum loop iterations ({MAX_LOOPS}) reached. Aborting.")
            task_failed = True
            failure_reason = f"Maximum iterations reached ({MAX_LOOPS})."
            break

    log.info("=" * 20 + " Execution Summary " + "=" * 20)
    if task_failed:
        log.error(f"Task execution FAILED: {failure_reason}")
        failed_at_task = potential_failed_entry
        log.error(
            f"  Failed during/after subtask: {failed_at_task.subtask.name if failed_at_task else 'Unknown'}"
        )
        log.error(
            f"  Last successful subtask: {last_successful_entry.subtask.name if last_successful_entry else 'None'}"
        )
        log.error(f"  Failure occurred at time: {current_state.current_time:.2f}")
    else:
        log.info("Task execution finished successfully.")

    result_schedule = []
    processed_names = set()
    if current_state:
        for ce in current_state.completed_subtasks:
            if ce.subtask.name != "Init" and ce.subtask.name not in processed_names:
                result_schedule.append(ce)
                processed_names.add(ce.subtask.name)

    if (
        task_failed
        and potential_failed_entry
        and potential_failed_entry.subtask.name != "Init"
    ):
        if potential_failed_entry.subtask.name not in processed_names:
            log.debug(
                f"  Explicitly adding failed task '{potential_failed_entry.subtask.name}' to final schedule."
            )
            setattr(potential_failed_entry.subtask, "execution_status", False)
            result_schedule.append(potential_failed_entry)
        else:
            for entry in result_schedule:
                if entry.subtask.name == potential_failed_entry.subtask.name:
                    log.debug(
                        f"  Updating status of task '{entry.subtask.name}' to FAILED."
                    )
                    setattr(entry.subtask, "execution_status", False)
                    break

    log.info("--- Final Schedule ---")
    total_simulated_time = 0.0
    last_end_time = 0.0
    for ce in result_schedule:
        status_str = (
            "Success" if getattr(ce.subtask, "execution_status", True) else "Failed"
        )
        log.info(
            f"- {ce.subtask.name:<30} | Status: {status_str:<7} | Start: {ce.start_time:>6.2f} | End: {ce.end_time:>6.2f} | Duration: {(ce.end_time - ce.start_time):>6.2f}"
        )
        if status_str == "Success" and ce.subtask.name != "Init":
            total_simulated_time += ce.end_time - ce.start_time
        if ce.end_time > last_end_time:
            last_end_time = ce.end_time

    log.info("-" * 60)
    simulation_time = last_end_time
    log.info(f"Total simulated time (last end time): {simulation_time:.2f}s")

    result_args = {
        "task_name": input_natural_language or "Unknown Task",
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": computation_time,
        "scene_name": SCENE_NAME or "Unknown Scene",
        "simulation_time": simulation_time,
        "task_failed": task_failed,
        "failure_reason": failure_reason if task_failed else "N/A",
    }
    try:
        result_save(**result_args)
    except Exception as e_save:
        log.error(f"Failed to save results: {e_save}", exc_info=True)

    if SAVE_KNOWLEDGE_ON_EXIT:
        try:
            agent.save_knowledge_to_file()
        except Exception as e:
            log.error(f"Failed to save agent knowledge: {e}", exc_info=True)

    log.info("Execution finished.")


if __name__ == "__main__":
    main()
