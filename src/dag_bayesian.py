import argparse
from pathlib import Path
import time
from typing import Any, Dict

from ithor.handlers.navigation_handler import load_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.core import Agent, Scheduler
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from utils.common.logger import create_module_logger
from utils.config import LOG_ROUND
from utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
    result_save,
)
from utils.io_utils.task_io import get_user_scene_choice, load_scene_positions
from utils.task import TaskUtil
from src.utils.ros_executor import RosExecutor

log = create_module_logger(__name__, module_log=True)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

    parser.add_argument(
        "-r",
        "--reset",
        default=True,
        help="Reset the knowledge base to Gaussian",
        action="store_true",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: INFO)",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        help="input scene name (default: FloorPlan1)",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default=25,
        help="실행할 태스크 instruction 문자열 또는 번호 (default: None)",
    )
    parser.add_argument(
        "--simulation",
        default=True,
        action="store_true",
        help="Simulation 모드 사용 여부 (default: False)",
    )
    parser.add_argument(
        "--ros",
        default=False,
        action="store_true",
        help="ROS 통신 사용 여부 (default: False)",
    )
    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    approach_name = "dag_bayesian"
    scene_name = args.scene

    # Set up the AI2-THOR controller and navigation graph
    if scene_name is None:
        scene_data = get_user_scene_choice()
        scene_name = scene_data.file_name.split("_")[0]

    if args.ros:
        controller = None
        nav_graph = {(0, 0, 0): {(0, 0, 0)}}
        action_handler = ActionHandler(nav_graph, log_level=args.log_level)
    else:
        controller = init_ai2thor_controller(scene_name)
        nav_graph = load_navigation_graph(controller)
        action_handler = ActionHandler(nav_graph, log_level=args.log_level)

    # Load the chosen task data
    task_files = list_task_files(scene_name=scene_name)

    if args.instruction:
        instruction = args.instruction
        input_natural_language = instruction
        task_data = None
        try:
            choice = int(instruction)
            if 1 <= choice <= len(task_files):
                task_file_name = task_files[choice - 1]
                task_data = load_task_data_from_file(task_file_name)
                input_natural_language = Path(task_file_name).stem
        except ValueError:
            # It's a natural language instruction, not a number
            pass

        if task_data is None:
            # It was a natural language instruction or an invalid number choice.
            # In both cases, we treat it as a natural language instruction.
            task_data = {"instruction": instruction}
    else:
        task_file_name, choice = get_user_task_choice(task_files)
        task_data = load_task_data_from_file(task_file_name)
        input_natural_language = task_file_name
        if choice != 0:
            input_natural_language = task_file_name


    # Build tasks and constraints
    # subtasks, constraints = TaskUtil.build_tasks_and_constraints(
    #     task_data, scene_file_name=scene_data.file_name,
    # )
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, scene_file_name=f"{scene_name}_physics_environment.json",
    )

    # Initialize the agent and scheduler
    constraint_handler = ConstraintHandler(action_handler)
    agent = Agent(constraint_handler)
    cost_calculator = HeuristicManager(action_handler)
    scheduler = Scheduler(
        action_handler=action_handler,
        constraint_handler=constraint_handler,
        heuristic_manager=cost_calculator,
    )
    scene_poses: Dict[str, Any] = load_scene_positions(f"{scene_name}_positions.json")
    # current_state = TaskUtil.get_init_state(
    #     subtasks, constraints, scene_data.object_positions
    # )
    current_state = TaskUtil.get_init_state(
        subtasks, constraints, scene_poses
    )

    is_end = False

    total_compute_time, total_sim_time = 0, 0
    
    ros_executor = RosExecutor() if args.ros else None
    
    try:
        while not is_end:

            next_state, computation_elapsed_time = scheduler.get_next_state(current_state)
            total_compute_time += computation_elapsed_time

            if next_state is None:
                log.error("No feasible solution found.")
                break
            
            if args.simulation:
                sim_elapsed_time, execution_status, sim_nav_time = execute_subtask(
                    controller, next_state.subtask, args.log_level
                )
                # 시뮬레이션에서 흐른 시간과 실행 상태를 저장.
                last_entry = next_state.completed_entries[-1]
                last_entry.sim_start_time = total_sim_time
                last_entry.sim_end_time = total_sim_time + sim_elapsed_time
                last_entry.execution_status = execution_status
                last_entry.sim_nav_time = sim_nav_time
                total_sim_time += sim_elapsed_time
                if next_state.subtask.subtask_type == "Monitor":
                    # ? 정말 constraint가 잘 전파된 것이 맞나?
                    next_state, monitored_subtask = agent.bayesian_estimate(next_state)
                    next_state.completed_entries[-1].monitored_subtask = monitored_subtask
                current_state = next_state
                if not current_state.remaining_subtasks:
                    is_end = True

                last_entry = current_state.completed_entries[-1]
                if last_entry.subtask.name != "Init":
                    log.info(
                        f"{last_entry.subtask.name} ({round(last_entry.sim_start_time, LOG_ROUND)} ~ {round(last_entry.sim_end_time,LOG_ROUND)})"
                    )
                    log.info(f"Primitive actions: {last_entry.subtask.execution.primitive_actions}\n")
                    last_entry.start_time_scheduled = round(last_entry.sim_start_time, LOG_ROUND)
                    last_entry.end_time_scheduled = round(last_entry.sim_end_time, LOG_ROUND)
            
            if args.ros and ros_executor:
                ros_start_offset = ros_executor.total_ros_time
                success, elapsed_time, action_logs = ros_executor.execute_subtask(next_state.subtask)
                
                last_entry = next_state.completed_entries[-1]
                last_entry.sim_start_time = ros_start_offset
                last_entry.sim_end_time = ros_start_offset + elapsed_time
                last_entry.execution_status = success
                last_entry.primitive_action_log = action_logs

                if not success:
                    break

                if next_state.subtask.subtask_type == "Monitor":
                    next_state, monitored_subtask = agent.bayesian_estimate(next_state)
                    next_state.completed_entries[-1].monitored_subtask = monitored_subtask
                
                current_state = next_state
                if not current_state.remaining_subtasks:
                    is_end = True
    finally:
        if ros_executor:
            ros_executor.shutdown()
            
    if args.ros:
        result_schedule = [
            entry
            for entry in current_state.completed_entries
            if entry.subtask.name != "Init"
        ]
        approach_name = f"{approach_name}_ros"
        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": result_schedule,
            "computation_time": total_compute_time,
            "scene_name": scene_name,
            "constraints": current_state.constraints,
            "initial_plan_data": task_data,
        }
        result_save(**result_args)

    if args.simulation:
        result_schedule = [
            entry
            for entry in current_state.completed_entries
            if entry.subtask.name != "Init"
        ]
        approach_name = f"{approach_name}_simulation"
        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": result_schedule,
            "computation_time": total_compute_time,
            "scene_name": scene_name,
            "constraints": current_state.constraints,
            "initial_plan_data": task_data,
            # "simulationTime": total_sim_time,
        }
        result_save(**result_args)

if __name__ == "__main__":
    main()
