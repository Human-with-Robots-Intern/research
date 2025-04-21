import argparse
import math
import time
from collections import deque

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
    controller = init_ai2thor_controller()
    nav_graph = load_navigation_graph(controller)
    scene_poses = load_scene_positions(f"{SCENE_NAME}_positions.json")

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
    agent = Agent(constraint_handler=constraint_handler)

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

    # 초기 상태 생성
    current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

    # Visualize the task graph if enabled
    visualize(approach_name, input_natural_language, constraints)
    result_schedule = []
    is_end = False
    task_failed = False
    failure_reason = ""
    failed_task_entry = None
    loop_count = 0
    MAX_LOOPS = 2000  # Increased loop limit; may need tuning based on task complexity
    DEADLOCK_THRESHOLD = 5  # 동일 상태 반복 허용 횟수

    computation_time = 0
    simulation_time = 0

    # 교착 상태 감지를 위한 변수 (deque 사용)
    # 최근 DEADLOCK_THRESHOLD + 1 개의 상태 요약만 저장하여 메모리 사용량 제한
    previous_states_summary = deque(maxlen=DEADLOCK_THRESHOLD + 1)
    consecutive_same_state_count = 0

    while not is_end and not task_failed and loop_count < MAX_LOOPS:
        loop_count += 1
        log.debug(f"--- Main Loop Iteration {loop_count} ---\n")

        computation_time_start = time.time()
        # --- 상태 요약 생성 (튜플 형태 권장: 변경 불가능하고 해시 가능) ---
        # --- 수정: current_time은 직접 비교 대신 아래에서 isclose 사용 ---
        current_state_summary = (
            tuple(sorted([ce.subtask.name for ce in current_state.completed_subtasks])),
            tuple(sorted([r.name for r in current_state.remaining_subtasks])),
            # round(current_state.current_time, 3), # 부동소수점 비교 위해 반올림 (아래 isclose로 대체)
        )

        # --- 교착 상태 확인 ---
        # --- 수정: deque에 이전 상태가 있고, 시간 제외한 요약이 같으며, 시간도 거의 같은지 확인 ---
        if (
            previous_states_summary
            and current_state_summary
            == previous_states_summary[-1][0]  # 시간 제외 요약 비교
            and math.isclose(
                current_state.current_time,
                previous_states_summary[-1][1],
                rel_tol=1e-5,
                abs_tol=1e-5,
            )  # 시간 비교 (허용 오차 조정 가능)
        ):
            consecutive_same_state_count += 1
            log.warning(
                f"Consecutive identical state detected ({consecutive_same_state_count}/{DEADLOCK_THRESHOLD}). "
                f"State Summary (excluding time): {current_state_summary}, Time: {current_state.current_time:.3f}"
            )
            if consecutive_same_state_count >= DEADLOCK_THRESHOLD:
                log.error(
                    f"Deadlock detected: State repeated {DEADLOCK_THRESHOLD} times. Aborting."
                )
                task_failed = True
                failure_reason = "Deadlock detected (state repeating)."
                # 실패한 태스크 정보 설정 (마지막으로 완료 시도한 태스크 또는 현재 상태의 마지막 완료 태스크)
                failed_task_entry = (
                    potential_failed_entry
                    if "potential_failed_entry" in locals() and potential_failed_entry
                    else (
                        current_state.completed_subtasks[-1]
                        if current_state.completed_subtasks
                        else None
                    )
                )
                break
        else:
            consecutive_same_state_count = 0  # 상태 변경 시 카운터 리셋

        # 현재 상태 기록 (요약 + 시간)
        previous_states_summary.append(
            (current_state_summary, current_state.current_time)
        )
        # --- 수정 끝 ---
        # --- 교착 상태 확인 끝 ---

        # --- 수정: next_state 가져오기 전에 potential_failed_entry 초기화 ---
        potential_failed_entry = None  # 루프 시작 시 초기화
        # --- 수정 끝 ---
        next_state = scheduler.get_next_state(current_state)
        computation_time += time.time() - computation_time_start

        if next_state is None:
            # 1.3: 스케줄러 실패 시 로그 강화 (변경 없음 - 추가 정보 부족)
            log.error(f"Scheduler could not find a feasible next state. Aborting.")
            task_failed = True
            # --- 수정: 실패 시 failed_task_entry 설정 시도 ---
            # 스케줄러 실패 시 어떤 태스크가 문제였는지 특정하기 어려움. 마지막 완료 태스크를 기록.
            failure_reason = "Scheduler failed to find a feasible next state."
            failed_task_entry = (
                current_state.completed_subtasks[-1]
                if current_state.completed_subtasks
                else None
            )
            # --- 수정 끝 ---
            break  # 기존 로직 유지 (실패 처리)

        # --- 수정: next_state가 반환되었으므로, 이것이 다음 시도될 태스크 ---
        # 이 태스크가 실행/시뮬레이션 후 실패할 수 있으므로 potential_failed_entry로 설정
        potential_failed_entry = (
            next_state.completed_subtasks[-1] if next_state.completed_subtasks else None
        )
        # --- 수정 끝 ---

        actual_subtask_time = 0.0
        actual_execution_status = False
        # --- 재시도 로직 추가 ---
        max_retries = 2  # 최대 재시도 횟수
        retry_delay = 1  # 재시도 간격 (초)
        for attempt in range(max_retries + 1):
            try:
                actual_subtask_time, actual_execution_status = execute_subtask(
                    controller, next_state.subtask
                )
                log.info(
                    f"Executed (Attempt {attempt+1}): {next_state.subtask.name}, Duration: {actual_subtask_time:.2f}, Status: {actual_execution_status}"
                )
                # 성공 시 루프 탈출
                break
            except Exception as e:
                log.error(
                    f"Error during subtask execution simulation for '{next_state.subtask.name}': {e}",
                    exc_info=True,
                )
                failure_reason = (
                    f"Exception during simulation of '{next_state.subtask.name}'."
                )
                # --- 수정: 실패 시 potential_failed_entry 사용 ---
                failed_task_entry = potential_failed_entry  # 예외 발생 시 시도했던 태스크를 실패 태스크로 설정
                # --- 수정 끝 ---
                if failed_task_entry:
                    if hasattr(failed_task_entry.subtask, "execution_status"):
                        failed_task_entry.subtask.execution_status = False
                    else:
                        log.warning(
                            f"Failed task entry '{failed_task_entry.subtask.name}' lacks 'execution_status'."
                        )

                task_failed = True
                break  # 예외 발생 시 외부 루프로 break
        # --- 재시도 로직 끝 ---

        # task_failed 플래그가 설정되었다면 메인 루프를 빠져나가야 함
        if task_failed:
            break

        # --- 성공 시 기존 로직 계속 ---
        # --- 수정: 성공 시 completed_task_entry 설정 ---
        # 성공했으므로 potential_failed_entry가 완료된 태스크임
        completed_task_entry = potential_failed_entry
        # --- 수정 끝 ---

        if next_state.subtask.type == "Monitor":
            try:
                _, monitored_subtask_info = agent.bayesian_estimate(next_state)
                if monitored_subtask_info:
                    completed_task_entry.subtask.monitored_subtask = (
                        monitored_subtask_info
                    )
                    log.info(
                        f"Bayesian estimation successful for {next_state.subtask.name}"
                    )

                    updated_sub_name = monitored_subtask_info.get(
                        "updated_subtask_name"  # Agent가 반환하는 이름은 이미 lowercase임
                    )
                    updated_mean = monitored_subtask_info.get("updated_expected_time")
                    if updated_sub_name and updated_mean is not None:
                        # --- 수정: remaining_subtasks 업데이트 로직 명확화 (Agent가 지식만 업데이트하도록 변경되었으므로 주석 처리 또는 로깅 강화) ---
                        log.info(
                            f"Agent knowledge updated for '{updated_sub_name}' to mean={updated_mean:.2f}. "
                            f"Scheduler will use this updated knowledge via HeuristicManager if needed. "
                            f"Direct update of remaining_subtasks duration in dag_bayesian is removed/disabled."
                        )
                        # found_match_for_update = False
                        # for r_sub in next_state.remaining_subtasks:
                        #     # 정확한 이름 일치 (대소문자 무시) 확인
                        #     if r_sub.name.lower() == updated_sub_name:
                        #         found_match_for_update = True
                        #         if r_sub.duration:
                        #             log.debug(
                        #                 f"Updating remaining subtask '{r_sub.name}' duration from "
                        #                 f"{r_sub.duration.interval} to {updated_mean:.2f} based on exact match."
                        #             )
                        #             r_sub.duration.interval = updated_mean # 직접 업데이트 제거
                        #         else:
                        #             log.warning(
                        #                 f"Cannot update duration for remaining subtask '{r_sub.name}' as it has no Duration object."
                        #             )
                        #         break  # 정확히 일치하는 것을 찾으면 루프 중단
                        # if not found_match_for_update:
                        #     log.warning(
                        #         f"Bayesian estimation updated knowledge for '{updated_sub_name}', "
                        #         f"but no exactly matching remaining subtask found for duration update."
                        #     )
                        # --- 수정 끝 ---
                    else:
                        log.warning(
                            f"Bayesian estimation did not return updated name/mean for {next_state.subtask.name}"
                        )

            except ValueError as e:
                log.error(f"Critical error during Bayesian estimation: {e}. Aborting.")
                failure_reason = f"Critical error during Bayesian estimation for '{next_state.subtask.name}'."
                # --- 수정: 실패 시 completed_task_entry 사용 ---
                failed_task_entry = completed_task_entry  # 베이지안 추정 실패 시 완료된 Monitor 태스크를 실패로 간주할 수 있음
                # --- 수정 끝 ---
                task_failed = True
                break

        actual_end_time = current_state.current_time + actual_subtask_time
        next_state.current_time = actual_end_time
        current_state = next_state

        if not current_state.remaining_subtasks:
            log.info("All subtasks completed.")
            is_end = True

        # 1.4: 최대 루프 도달 시 로그 및 실패 처리 (상수 값만 변경됨)
        if loop_count >= MAX_LOOPS:
            log.error(f"Maximum loop iterations ({MAX_LOOPS}) reached. Aborting.")
            task_failed = True
            failure_reason = (
                "Maximum iterations reached (potential infinite loop or stuck state)."
            )
            # --- 수정: 실패 시 completed_task_entry 또는 current_state의 마지막 완료 태스크 사용 ---
            failed_task_entry = (
                completed_task_entry
                if "completed_task_entry" in locals() and completed_task_entry
                else (
                    current_state.completed_subtasks[-1]
                    if current_state.completed_subtasks
                    else None
                )
            )
            # --- 수정 끝 ---

    log.info("=" * 20 + " Execution Summary " + "=" * 20)
    if task_failed:
        log.error(f"Task execution failed: {failure_reason}")
    else:
        log.info("Task execution finished successfully.")

    # --- 1.2: 결과 저장 로직 수정 ---
    result_schedule = []
    processed_names = set()  # 중복 추가 방지

    # 실패 여부와 관계없이 current_state의 완료된 태스크 목록을 기반으로 결과 생성
    if current_state:
        for ce in current_state.completed_subtasks:
            # Init 제외하고 아직 처리되지 않은 이름만 추가
            if ce.subtask.name != "Init" and ce.subtask.name not in processed_names:
                result_schedule.append(ce)
                processed_names.add(ce.subtask.name)

    # --- 수정: 실패한 태스크를 명시적으로 추가 (이미 위에서 추가되지 않았다면) ---
    # 실패한 태스크가 있고, Init이 아니며, 아직 결과에 없다면 추가
    if task_failed and failed_task_entry and failed_task_entry.subtask.name != "Init":
        if failed_task_entry.subtask.name not in processed_names:
            # 실패 상태를 명확히 설정 (이미 루프에서 설정되었을 수 있음)
            if hasattr(failed_task_entry.subtask, "execution_status"):
                failed_task_entry.subtask.execution_status = False
            else:
                log.warning(
                    f"Failed task entry '{failed_task_entry.subtask.name}' lacks 'execution_status' attribute. Cannot mark as failed explicitly."
                )
            result_schedule.append(failed_task_entry)
            processed_names.add(failed_task_entry.subtask.name)
        # 만약 failed_task_entry가 이미 result_schedule에 있다면, 상태만 업데이트
        elif hasattr(failed_task_entry.subtask, "execution_status"):
            for entry in result_schedule:
                if entry.subtask.name == failed_task_entry.subtask.name:
                    entry.subtask.execution_status = False
                    break
    # --- 수정 끝 ---

    log.info("--- Final Schedule ---")
    total_simulated_time = 0.0
    last_end_time = 0.0
    for ce in result_schedule:
        # getattr을 사용하여 execution_status가 없는 경우 기본값 True 사용
        status_str = (
            "Success" if getattr(ce.subtask, "execution_status", True) else "Failed"
        )
        # 시작/종료 시간 로깅 추가
        log.info(
            f"- {ce.subtask.name:<30} | Status: {status_str:<7} | Start: {ce.start_time:>6.2f} | End: {ce.end_time:>6.2f} | Duration: {(ce.end_time - ce.start_time):>6.2f}"
        )
        # Init 제외하고 성공한 태스크의 duration만 합산 (실패 태스크 시간은 제외)
        if status_str == "Success" and ce.subtask.name != "Init":
            total_simulated_time += ce.end_time - ce.start_time
        if ce.end_time > last_end_time:
            last_end_time = ce.end_time

    log.info("-" * 60)
    # --- 수정: simulation_time을 결과 스케줄의 마지막 종료 시간 또는 계산된 총 시간으로 설정 ---
    # simulation_time = total_simulated_time # 이전: 성공한 태스크 시간 합계
    simulation_time = last_end_time  # 수정: 마지막 태스크 완료 시간
    log.info(f"Total simulated time (last end time): {simulation_time:.2f}s")
    # --- 수정 끝 ---

    # result_save 호출 전 인자 확인
    result_args = {
        "task_name": (
            input_natural_language if input_natural_language else "Unknown Task"
        ),
        "approach_name": approach_name,
        "result_schedule": result_schedule,  # 수정된 스케줄 전달
        "computation_time": computation_time,
        "scene_name": SCENE_NAME if SCENE_NAME else "Unknown Scene",
        "simulation_time": simulation_time,  # 수정된 시간 전달
        "task_failed": task_failed,
        "failure_reason": failure_reason if task_failed else "N/A",
    }
    # 누락된 키가 있는지 확인 (디버깅용)
    # required_keys = ["task_name", "approach_name", "result_schedule", "computation_time", "scene_name", "simulation_time", "task_failed", "failure_reason"]
    # for key in required_keys:
    #     if key not in result_args:
    #         log.error(f"Missing key '{key}' in result_args before calling result_save!")
    #     elif result_args[key] is None and key != "failure_reason": # failure_reason은 None일 수 있음
    #          log.warning(f"Key '{key}' is None in result_args.")

    result_save(**result_args)

    if SAVE_KNOWLEDGE_ON_EXIT:
        try:
            agent.save_knowledge_to_file()
        except Exception as e:
            log.error(f"Failed to save agent knowledge: {e}", exc_info=True)


if __name__ == "__main__":
    main()
