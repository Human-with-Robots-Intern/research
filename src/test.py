import argparse

from core.agent import Agent
from core.scheduler import Scheduler
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.task import (
    build_tasks_and_constraints,
    get_init_state,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)

log = create_module_logger(module_name=__name__, is_file_handler=True)


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
        "-v",
        "--visualize",
        help="Enable visualization of the task plan",
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
    parser.add_argument(
        "-s",
        "--simulation",
        action="store_true",
    )
    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    if args.simulation:
        controller = init_ai2thor()

    task_files = list_task_files()
    task_file_name = get_user_task_choice(task_files, choice=1)

    # Load the chosen task data
    task_data = load_task_data_from_file(task_file_name)

    # Build tasks and constraints
    subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)

    # Visualize the task graph if enabled
    if args.visualize:
        visualize(task_file_name, constraints)

    agent = Agent()

    scheduler = Scheduler(agent)

    result_schedule = []
    current_state = get_init_state(subtasks, constraints)
    is_end = False
    while not is_end:
        # 다음 상태를 먼저 구해온다
        next_state = scheduler.get_next_state(current_state)

        # 만약 next_state가 None이면, 더 이상 진행 불가하므로 에러 처리
        if next_state is None:
            log.error("No feasible solution found.")
            break

        # 지금의 current_state를 바탕으로 시뮬레이션 실행
        if args.simulation:
            execute_subtask(controller, current_state.subtask)

        # current_state를 next_state로 넘기고
        current_state = next_state

        # 스케줄 결과에 현재 서브태스크를 추가
        result_schedule.append(current_state.subtask)

        # 시각화 실행
        visualize(task_file_name, current_state.constraints, result_schedule)

        # 남은 서브태스크가 없으면 종료
        if not current_state.remaining_subtasks:
            is_end = True


if __name__ == "__main__":
    main()
