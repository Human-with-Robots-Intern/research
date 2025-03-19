import argparse
import time

from ai2thor.platform import CloudRendering

from core.agent import Agent
from core.scheduler import Scheduler
from ithor.handlers.navigation_handler import build_navigation_graph
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger
from utils.constants import BEAM_WIDTH, LOG_ROUND, SIMULATION_DEPTH
from utils.result_saver import result_save
from utils.task import (
    build_tasks_and_constraints,
    get_init_state,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)
from utils.task.task_io import load_scene_positions
from utils.viz.visualizer import visualize

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
        default=True,
        action="store_true",
    )
    parser.add_argument(
        "-s",
        "--simulation",
        default=True,
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
    scene_poses = load_scene_positions("FloorPlan1_positions.json")

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name = get_user_task_choice(task_files, choice=11)
    task_data = load_task_data_from_file(task_file_name)

    # Build tasks and constraints
    subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)

    # Visualize the task graph if enabled
    if args.visualize:
        visualize(approach_name, task_file_name, constraints)

    agent = Agent()

    scheduler = Scheduler(BEAM_WIDTH, SIMULATION_DEPTH, nav_graph=nav_graph)

    result_schedule = []

    current_state = get_init_state(subtasks, constraints, scene_poses)
    is_end = False

    computation_time_start = time.time()
    total_simulation_execute_time = 0
    simulationTime = 0
    while not is_end:

        next_state = scheduler.get_next_state(current_state)

        if next_state is None:
            log.error("No feasible solution found.")
            break

        if args.simulation:
            execute_time_start = time.time()
            subtask_time, is_subtask_success = execute_subtask(
                controller, next_state.subtask
            )
            execute_time = time.time() - execute_time_start
            total_simulation_execute_time += execute_time

            simulationTime += subtask_time
            next_state.completed_subtasks[-1].subtask.is_subtask_success = (
                is_subtask_success
            )

        if next_state.subtask.type == "Monitor":
            next_state = agent.bayesian_estimate(next_state)

        current_state = next_state

        result_schedule.append(current_state.subtask)

        if not current_state.remaining_subtasks:
            is_end = True
    computation_time = (
        time.time() - computation_time_start - total_simulation_execute_time
    )

    for ce in current_state.completed_subtasks:
        log.info(
            f"{ce.subtask.name} ({round(ce.start_time, LOG_ROUND)} ~ {round(ce.end_time,LOG_ROUND)})"
        )
        log.info(f"Primitive actions: {ce.subtask.execution.primitive_actions}\n")
        ce.subtask.start_time = round(ce.start_time, LOG_ROUND)
        ce.subtask.end_time = round(ce.end_time, LOG_ROUND)

        result_schedule.append(ce.subtask)

    visualize(
        approach_name, task_file_name, current_state.constraints, plan=result_schedule
    )

    result_save(
        task_file_name, approach_name, result_schedule, computation_time, simulationTime
    )


if __name__ == "__main__":
    main()
