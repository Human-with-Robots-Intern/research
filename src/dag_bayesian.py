import argparse
import time

from core.agent import Agent
from core.scheduler import Scheduler
from ithor.handlers.navigation_handler import build_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor
from utils.common import create_module_logger
from utils.config import BEAM_WIDTH, LOG_ROUND, SCENE_NAME, SIMULATION_DEPTH
from utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
    result_save,
)
from utils.task import TaskUtil
from utils.visualizers import visualize

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
        "--rag",
        default=False,
        action="store_true",
    )

    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    approach_name = "dag_bayesian"

    # Set up the AI2-THOR controller and navigation graph
    controller = init_ai2thor()
    nav_graph = build_navigation_graph(controller)
    scene_name = SCENE_NAME
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")

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

    # Visualize the task graph if enabled

    visualize(approach_name, input_natural_language, constraints)

    agent = Agent()

    scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, nav_graph=nav_graph)

    result_schedule = []

    current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)
    is_end = False

    computation_time = 0
    simulation_time = 0

    while not is_end:

        computation_time_start = time.time()
        next_state = scheduler.get_next_state(current_state)
        computation_time += time.time() - computation_time_start

        if next_state is None:
            log.error("No feasible solution found.")
            break

        # 터미널에서 src/dag_bayesian.py -s 실행시 사용됨
        subtask_time, execution_status = execute_subtask(controller, next_state.subtask)
        # 시뮬레이션에서 반환해주는 시간을 subtask 객체에 저장.
        next_state.completed_subtasks[-1].subtask.start_time_simulation = (
            simulation_time
        )
        next_state.completed_subtasks[-1].subtask.end_time_simulation = (
            simulation_time + subtask_time
        )

        simulation_time += subtask_time

        next_state.completed_subtasks[-1].subtask.execution_status = execution_status

        if next_state.subtask.type == "Monitor":
            next_state, monitored_subtask = agent.bayesian_estimate(next_state)
            next_state.completed_subtasks[-1].subtask.monitored_subtask = (
                monitored_subtask
            )

        current_state = next_state

        if not current_state.remaining_subtasks:
            is_end = True
    # print(f"planning time is : {computation_time:.2f}")

    for ce in current_state.completed_subtasks:
        if ce.subtask.name == "Init":
            continue
        log.info(
            f"{ce.subtask.name} ({round(ce.start_time, LOG_ROUND)} ~ {round(ce.end_time,LOG_ROUND)})"
        )
        log.info(f"Primitive actions: {ce.subtask.execution.primitive_actions}\n")
        # 지금 start time 과 end time은 scheduler가 계산 한 값이고 simulation을 했을때의 시간이 아니다.
        ce.subtask.start_time_scheduled = round(ce.start_time, LOG_ROUND)
        ce.subtask.end_time_scheduled = round(ce.end_time, LOG_ROUND)
        result_schedule.append(ce)

    if args.visualize:
        visualize(
            approach_name,
            input_natural_language,
            current_state.constraints,
            plan=result_schedule,
        )

    approach_name = f"{approach_name}_simulation"
    result_args = {
        "task_name": input_natural_language,
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": computation_time,
        "scene_name": scene_name,
        # "simulationTime": simulation_time,
    }
    result_save(**result_args)


if __name__ == "__main__":
    main()
