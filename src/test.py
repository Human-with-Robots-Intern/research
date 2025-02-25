import argparse
import time

from core.agent import Agent
from core.scheduler import Scheduler
from ithor.handlers.navigation_handler import build_navigation_graph
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.constants import BEAM_WIDTH, LOG_ROUND, SIMULATION_DEPTH
from utils.task import (
    build_tasks_and_constraints,
    get_init_state,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)
from utils.task.task_io import load_scene_positions
from func_for_gantt import func_for_gantt

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
        default=False,
        action="store_true",
    )
    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    # tasks 파일 안의 json파일 개수 세기.
    # json 파일의 개수만큼 for문 돌리기.
    # i번째 json 파일을 실행.

    # Load the chosen task data
    task_files = list_task_files()
    for i in range(len(task_files)):
        j = i+1
        # 코드 실제 실행 시간 기준이 언제 인지. 일단은 파일 불러오기 전으로 함.
        task_opening_time = time.time()
        task_file_name = get_user_task_choice(task_files, choice=j)
        task_data = load_task_data_from_file(task_file_name)


        # Set up the AI2-THOR controller and navigation graph
        controller = init_ai2thor()
        nav_graph = build_navigation_graph(controller)
        scene_poses = load_scene_positions("FloorPlan1_positions.json")

        # Build tasks and constraints
        subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)

        # Visualize the task graph if enabled
        if args.visualize:
            visualize(task_file_name, constraints)

        agent = Agent()

        scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, nav_graph)

        result_schedule = []
        final_schedule = {}
        current_state = get_init_state(subtasks, constraints, scene_poses)
        is_end = False

        while not is_end:
            subtask_opening_time = time.time()
            next_state = scheduler.get_next_state(current_state)

            if next_state is None:
                log.error("No feasible solution found.")
                break
            ai2thor_time = 0
            if args.simulation:
                ai2thor_time = execute_subtask(controller, next_state.subtask)

            # TODO Simulation 수행 결과값을 얻어야 함. 지금은 스케쥴러에서 줌
            # if next_state.subtask.type == "Monitor":
            #     next_state = agent.bayesian_estimate(next_state, subtasks)

            current_state = next_state

            result_schedule.append(current_state.subtask)

            if not current_state.remaining_subtasks:
                is_end = True

            subtask_real_time = time.time() - subtask_opening_time
            
            final_schedule[result_schedule[-1].name] = [result_schedule[-1].duration.interval, ai2thor_time, subtask_real_time]

        visualize(task_file_name, current_state.constraints, result_schedule)
        task_real_time = time.time() - task_opening_time
        for ce in current_state.completed_subtasks:
            log.info(
                f"{ce.subtask.name} ({round(ce.start_time, LOG_ROUND)} ~ {round(ce.end_time,LOG_ROUND)})"
            )
            log.info(f"Primitive actions: {ce.subtask.execution.primitive_actions}")
            log.info("\n")

        # 결과 기록 json파일에 형식 맞춰서 write하기.
        func_for_gantt.write_gantt_file("ours.json", task_file_name, final_schedule, list(constraints.edges))
        print()


if __name__ == "__main__":
    main()
