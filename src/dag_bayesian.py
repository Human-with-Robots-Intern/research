import argparse
import time

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
    task_file_name, choice = get_user_task_choice(task_files, is_rag=args.rag)
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

    computation_time = 0
    simulation_time = 0

    while not is_end and not task_failed and loop_count < MAX_LOOPS:
        loop_count += 1
        log.debug(f"--- Main Loop Iteration {loop_count} ---\n")

        computation_time_start = time.time()
        next_state = scheduler.get_next_state(current_state)
        computation_time += time.time() - computation_time_start

        if next_state is None:
            # 1.3: 스케줄러 실패 시 로그 강화
            log.error(
                f"Scheduler could not find a feasible next state from state at time "
                f"{current_state.current_time:.2f}. Aborting."
            )
            task_failed = True
            failure_reason = "Scheduler could not find a feasible path."
            break  # 기존 로직 유지 (실패 처리)

        potential_failed_entry = next_state.completed_subtasks[-1]

        actual_subtask_time = 0.0
        actual_execution_status = False
        try:
            actual_subtask_time, actual_execution_status = execute_subtask(
                controller, next_state.subtask
            )
            log.info(
                f"Executed: {next_state.subtask.name}, Duration: {actual_subtask_time:.2f}, Status: {actual_execution_status}"
            )

            completed_task_entry = potential_failed_entry
            completed_task_entry.subtask.start_time_simulation = simulation_time
            completed_task_entry.subtask.end_time_simulation = (
                simulation_time + actual_subtask_time
            )
            completed_task_entry.subtask.execution_status = actual_execution_status
            simulation_time += actual_subtask_time

            if not actual_execution_status:
                log.error(
                    f"Subtask '{next_state.subtask.name}' failed execution in simulation. Aborting."
                )
                failure_reason = (
                    f"Subtask '{next_state.subtask.name}' failed execution."
                )
                failed_task_entry = completed_task_entry
                task_failed = True
                break

        except Exception as e:
            log.error(
                f"Error during subtask execution simulation for '{next_state.subtask.name}': {e}",
                exc_info=True,
            )
            failure_reason = (
                f"Exception during simulation of '{next_state.subtask.name}'."
            )
            failed_task_entry = potential_failed_entry
            if failed_task_entry:
                failed_task_entry.subtask.execution_status = False
            task_failed = True
            break

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
                        found_match_for_update = False
                        for r_sub in next_state.remaining_subtasks:
                            # 정확한 이름 일치 (대소문자 무시) 확인
                            if r_sub.name.lower() == updated_sub_name:
                                found_match_for_update = True
                                if r_sub.duration:
                                    log.debug(
                                        f"Updating remaining subtask '{r_sub.name}' duration from "
                                        f"{r_sub.duration.interval} to {updated_mean:.2f} based on exact match."
                                    )
                                    r_sub.duration.interval = updated_mean
                                else:
                                    log.warning(
                                        f"Cannot update duration for remaining subtask '{r_sub.name}' as it has no Duration object."
                                    )
                                break  # 정확히 일치하는 것을 찾으면 루프 중단
                        if not found_match_for_update:
                            log.warning(
                                f"Bayesian estimation updated knowledge for '{updated_sub_name}', "
                                f"but no exactly matching remaining subtask found for duration update."
                            )
                    else:
                        log.warning(
                            f"Bayesian estimation did not return updated name/mean for {next_state.subtask.name}"
                        )

            except ValueError as e:
                log.error(
                    f"Critical error during Bayesian estimation (ValueError): {e}. Aborting."
                )
                failure_reason = f"ValueError during Bayesian estimation for '{next_state.subtask.name}'."
                failed_task_entry = completed_task_entry
                task_failed = True
                break
            except Exception as e:
                log.error(
                    f"Unexpected critical error during Bayesian estimation: {e}",
                    exc_info=True,
                )
                failure_reason = f"Unexpected exception during Bayesian estimation for '{next_state.subtask.name}'."
                failed_task_entry = completed_task_entry
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
            failed_task_entry = (
                completed_task_entry if "completed_task_entry" in locals() else None
            )

    log.info("=" * 20 + " Execution Summary " + "=" * 20)
    if task_failed:
        log.error(f"Task execution failed: {failure_reason}")
    else:
        log.info("Task execution finished successfully.")

    # --- 1.2: 결과 저장 로직 수정 ---
    result_schedule = []
    if current_state:
        for ce in current_state.completed_subtasks:
            # 실패 시에는 성공한 태스크만 기록 (Init 제외)
            is_successful = getattr(
                ce.subtask, "execution_status", True
            )  # 상태 없으면 True 간주
            if ce.subtask.name != "Init" and (not task_failed or is_successful):
                result_schedule.append(ce)

    # 실패한 태스크가 있고, 결과 스케줄의 마지막 항목이 아니면 추가
    if task_failed and failed_task_entry and failed_task_entry.subtask.name != "Init":
        if (
            not result_schedule
            or result_schedule[-1].subtask.name != failed_task_entry.subtask.name
        ):
            # 실패 상태를 명확히 하기 위해 execution_status 확인/설정 (이미 루프에서 설정되었을 수 있음)
            if hasattr(failed_task_entry.subtask, "execution_status"):
                failed_task_entry.subtask.execution_status = False
            else:
                # status 속성이 없다면 로깅 또는 기본값 설정 (여기선 로깅만)
                log.warning(
                    f"Failed task entry '{failed_task_entry.subtask.name}' lacks 'execution_status' attribute."
                )
            result_schedule.append(failed_task_entry)
    # --- 결과 저장 로직 수정 끝 ---

    for ce in result_schedule:
        status_str = (
            "Success" if getattr(ce.subtask, "execution_status", True) else "Failed"
        )
        log.info(f"{ce.subtask.name} ... Status: {status_str} ...")

    result_args = {
        "task_name": input_natural_language,
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": computation_time,
        "scene_name": SCENE_NAME,
        "simulation_time": simulation_time,
        "task_failed": task_failed,
        "failure_reason": failure_reason,
    }
    result_save(**result_args)

    if SAVE_KNOWLEDGE_ON_EXIT:
        try:
            agent.save_knowledge_to_file()
        except Exception as e:
            log.error(f"Failed to save agent knowledge: {e}", exc_info=True)


if __name__ == "__main__":
    main()
