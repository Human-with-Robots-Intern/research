import argparse
import gc
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ai2thor.platform import CloudRendering

from ithor.handlers.action import Action
from ithor.utils.math_utils import load_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.core import Agent, Scheduler
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from src.utils.get_state import save_scene_state
from src.utils.ros_executor import RosExecutor
from utils.common.logger import create_module_logger
from utils.config import LOG_ROUND
from utils.io_utils import (
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
    result_save,
)
from utils.io_utils.task_io import (
    get_user_scene_choice,
    load_scene_positions,
    load_task_data_from_sampled_set,
)
from utils.task import TaskUtil

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
        "--ablation-name",
        type=str,
        default=None,
        help="The name of the ablation configuration.",
    )
    parser.add_argument(
        "--init_prior_mean",
        type=float,
        default=100,
        help="베이지안 추정을 위한 초기 평균값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--case",
        type=str,
        default="tasks_3_constraints_2",
        help="The name of the case.",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default="06_heat_the_potato_using_microwave_and_cook_egg_and_wash_all_fork_and_spoon.json",
        help="실행할 태스크 instruction 문자열 또는 번호 (default: None)",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        help="input scene name (default: FloorPlan1)",
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
    parser.add_argument(
        "--cloud-rendering",
        default=False,
        action="store_true",
        help="Use CloudRendering platform for AI2-THOR.",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default=None,
        help="Path to the log file for this specific run.",
    )

    parser.add_argument(
        "--init_prior_variance",
        type=float,
        default=900,
        help="베이지안 추정을 위한 초기 분산값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--alpha_heuristic",
        type=float,
        default=None,
        help="Heuristic alpha 값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--beta_heuristic",
        type=float,
        default=None,
        help="Heuristic beta 값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--gamma_heuristic",
        type=float,
        default=None,
        help="Heuristic gamma 값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--factor_alpha",
        type=float,
        default=None,
        help="Factor alpha 값 (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--beam_width",
        type=int,
        default=5,
        help="Scheduler beam width (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--beam_depth",
        type=int,
        default=5,
        help="Scheduler beam depth (simulation_depth) (기본값: constants.py 값)",
    )
    parser.add_argument(
        "--disable_monitoring",
        action="store_true",
        help="Disable Bayesian monitoring.",
    )
    parser.add_argument(
        "--trajectory_log_path",
        type=str,
        default=None,
        help="Path to save per-action trajectory logs for downstream evaluation.",
    )
    return parser.parse_args()


def _sanitize_filename(value: str) -> str:
    """Return a filesystem-safe slug."""

    if not value:
        return "task"
    slug = re.sub(r"[^0-9a-zA-Z_\-]+", "_", value)
    slug = slug.strip("_")
    return slug or "task"


def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()
    approach_name = "dag_bayesian"

    # Dynamically override constants based on command-line arguments
    from src.utils.config import constants

    init_prior_mean = (
        args.init_prior_mean
        if args.init_prior_mean is not None
        else constants.INIT_PRIOR_MEAN
    )
    init_prior_variance = (
        args.init_prior_variance
        if args.init_prior_variance is not None
        else constants.INIT_PRIOR_VARIANCE
    )

    if args.init_prior_mean is not None:
        constants.set_init_prior_mean(args.init_prior_mean)
    else:
        constants.set_init_prior_mean(init_prior_mean)
    if args.init_prior_variance is not None:
        constants.set_init_prior_variance(args.init_prior_variance)
    else:
        constants.set_init_prior_variance(init_prior_variance)
    if args.alpha_heuristic is not None:
        constants.set_alpha_heuristic(args.alpha_heuristic)
    if args.beta_heuristic is not None:
        constants.set_beta_heuristic(args.beta_heuristic)
    if args.gamma_heuristic is not None:
        constants.set_gamma_heuristic(args.gamma_heuristic)
    if args.factor_alpha is not None:
        constants.set_factor_alpha(args.factor_alpha)
    if args.beam_width is not None:
        constants.set_beam_width(args.beam_width)
    if args.beam_depth is not None:
        constants.set_simulation_depth(args.beam_depth)
    if args.disable_monitoring:
        constants.set_monitoring_enabled(False)

    logger = create_module_logger(
        module_name=approach_name,
        log_file_path=Path(args.log_path) if args.log_path else None,
        level=logging.ERROR,
    )
    scene_name = args.scene
    controller = None
    ros_executor = None  # ros_executor를 None으로 미리 초기화

    platform_obj = None  # Set up the AI2-THOR controller and navigation graph

    if args.cloud_rendering:
        platform_obj = CloudRendering

    try:
        if scene_name is None:
            scene_data = get_user_scene_choice()
            scene_name = scene_data.file_name.split("_")[0]

        if args.ros:
            controller = None
            nav_graph = {(0, 0, 0): {(0, 0, 0)}}
            action_handler = ActionHandler(nav_graph, real_world_mode=True)
        else:
            controller = init_ai2thor_controller(scene_name, platform=platform_obj)
            nav_graph = load_navigation_graph(controller)
            action_handler = ActionHandler(nav_graph, real_world_mode=False)

        trajectory_log_path: Optional[Path] = (
            Path(args.trajectory_log_path).expanduser()
            if args.trajectory_log_path
            else None
        )

        action_interface: Optional[Action] = None
        task_files = list_task_files(scene_name=scene_name)

        if args.case:
            # Load task data
            input_natural_language = re.match(r"\d+_(.*)", args.instruction).group(1)
            task_data = load_task_data_from_sampled_set(
                args.case, scene_name, args.instruction
            )
            approach_name_final = (
                f"{approach_name}_{args.ablation_name}"
                if args.ablation_name
                else approach_name
            )
            save_scene_state(
                controller=controller,
                output_path=Path(f"assets/results/states{int(init_prior_mean)}"),
                case_name=args.case,
                scene_name=scene_name,
                instruction=args.instruction.split(".json")[0],
                approach_name=f"{approach_name_final}",
                state_label="init",
            )
            if trajectory_log_path is None:
                instr_stem = Path(args.instruction).stem
                approach_suffix = (
                    f"{approach_name}_{args.ablation_name}"
                    if args.ablation_name
                    else approach_name
                )
                trajectory_log_path = (
                    Path(f"assets/results/states{int(init_prior_mean)}")
                    / args.case
                    / instr_stem
                    / scene_name
                    / approach_suffix
                    / "trajectory_log.json"
                )

            trajectory_log_path.parent.mkdir(parents=True, exist_ok=True)
            if trajectory_log_path.exists():
                trajectory_log_path.unlink()
            action_interface = Action(
                controller,
                logger=logger,
                trajectory_log_json_path=trajectory_log_path,
            )

        elif args.instruction:
            # Load the chosen task data
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
            save_scene_state(
                controller=controller,
                output_path=Path(f"assets/results/states{int(init_prior_mean)}"),
                case_name=args.case,
                scene_name=scene_name,
                instruction=input_natural_language,
                approach_name=approach_name,
                state_label="init",
            )
            if task_data is None:
                # It was a natural language instruction or an invalid number choice.
                # In both cases, we treat it as a natural language instruction.
                task_data = {"instruction": instruction}

            if trajectory_log_path is None:
                instruction_slug = _sanitize_filename(input_natural_language)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                trajectory_log_path = (
                    Path("assets/results/tune")
                    / instruction_slug
                    / f"{timestamp}_trajectory_log.json"
                )
            trajectory_log_path.parent.mkdir(parents=True, exist_ok=True)
            if trajectory_log_path.exists():
                trajectory_log_path.unlink()
            action_interface = Action(
                controller,
                logger=logger,
                trajectory_log_json_path=trajectory_log_path,
            )

        else:
            task_file_name, choice = get_user_task_choice(task_files)
            task_data = load_task_data_from_file(task_file_name)
            input_natural_language = task_file_name
            if choice != 0:
                input_natural_language = task_file_name
            if trajectory_log_path is None:
                instruction_slug = _sanitize_filename(Path(task_file_name).stem)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                trajectory_log_path = (
                    Path("assets/results/tune")
                    / instruction_slug
                    / f"{timestamp}_trajectory_log.json"
                )
            trajectory_log_path.parent.mkdir(parents=True, exist_ok=True)
            if trajectory_log_path.exists():
                trajectory_log_path.unlink()
            action_interface = Action(
                controller,
                logger=logger,
                trajectory_log_json_path=trajectory_log_path,
            )

        if action_interface is None:
            raise RuntimeError(
                "Failed to initialize action interface for simulation run."
            )

        # Build tasks and constraints
        # subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        #     task_data, scene_file_name=scene_data.file_name,
        # )

        subtasks, constraints, bayesian_load = TaskUtil.build_tasks_and_constraints(
            task_data,
            scene_file_name=f"{scene_name}_physics_environment.json",
        )

        # Initialize the agent and scheduler
        constraint_handler = ConstraintHandler(action_handler)
        agent = Agent(constraint_handler, bayesian_load)
        cost_calculator = HeuristicManager(action_handler)
        scheduler = Scheduler(
            action_handler=action_handler,
            constraint_handler=constraint_handler,
            heuristic_manager=cost_calculator,
            beam_width=constants.BEAM_WIDTH,
            simulation_depth=constants.SIMULATION_DEPTH,
        )
        scene_poses: Dict[str, Any] = load_scene_positions(
            f"{scene_name}_positions.json"
        )
        # current_state = TaskUtil.get_init_state(
        #     subtasks, constraints, scene_data.object_positions
        # )
        current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

        is_end = False

        total_compute_time, total_sim_time = 0, 0

        ros_executor = (
            RosExecutor(trajectory_log_path=trajectory_log_path) if args.ros else None
        )

        while not is_end:

            next_state, computation_elapsed_time = scheduler.get_next_state(
                current_state
            )
            total_compute_time += computation_elapsed_time

            if next_state is None:
                logger.error("No feasible solution found.")
                break

            if args.simulation:
                sim_elapsed_time, execution_status, sim_nav_time = execute_subtask(
                    controller, next_state.subtask, logger, action_interface
                )
                # 시뮬레이션에서 흐른 시간과 실행 상태를 저장.
                last_entry = next_state.completed_entries[-1]
                last_entry.sim_start_time = total_sim_time
                last_entry.sim_end_time = total_sim_time + sim_elapsed_time
                last_entry.execution_status = execution_status
                last_entry.sim_nav_time = sim_nav_time
                total_sim_time += sim_elapsed_time
                intervallist = []
                for name1 in current_state.constraints.in_edges._adjdict.keys():
                    for name2 in current_state.constraints.in_edges._adjdict[
                        name1
                    ].keys():
                        if current_state.constraints.in_edges._adjdict[name1][name2][
                            "info"
                        ]["IsCritical"]:
                            intervallist.append(
                                {
                                    name2: current_state.constraints.in_edges._adjdict[
                                        name1
                                    ][name2]["info"]["Interval"]
                                }
                            )
                # 모니터 끄려면 이 안쪽을 주석화.
                if (
                    not args.disable_monitoring
                    and next_state.subtask.subtask_type == "Monitor"
                ):
                    next_state, monitored_subtask = agent.bayesian_estimate(next_state)
                    next_state.completed_entries[-1].monitored_subtask = (
                        monitored_subtask
                    )
                current_state = next_state
                if not current_state.remaining_subtasks:
                    is_end = True
                intervallist = []
                for name1 in current_state.constraints.in_edges._adjdict.keys():
                    for name2 in current_state.constraints.in_edges._adjdict[
                        name1
                    ].keys():
                        if current_state.constraints.in_edges._adjdict[name1][name2][
                            "info"
                        ]["IsCritical"]:
                            intervallist.append(
                                {
                                    name2: current_state.constraints.in_edges._adjdict[
                                        name1
                                    ][name2]["info"]["Interval"]
                                }
                            )
                last_entry = current_state.completed_entries[-1]
                if last_entry.subtask.name != "Init":
                    logger.info(
                        f"{last_entry.subtask.name} ({round(last_entry.sim_start_time, LOG_ROUND)} ~ {round(last_entry.sim_end_time,LOG_ROUND)})"
                    )
                    logger.info(
                        f"Primitive actions: {last_entry.subtask.execution.primitive_actions}\n"
                    )
                    last_entry.start_time_scheduled = round(
                        last_entry.sim_start_time, LOG_ROUND
                    )
                    last_entry.end_time_scheduled = round(
                        last_entry.sim_end_time, LOG_ROUND
                    )

            if args.ros and ros_executor:
                ros_start_offset = ros_executor.total_ros_time
                success, elapsed_time, action_logs = ros_executor.execute_subtask(
                    next_state.subtask
                )

                last_entry = next_state.completed_entries[-1]
                last_entry.sim_start_time = ros_start_offset
                last_entry.sim_end_time = ros_start_offset + elapsed_time
                last_entry.execution_status = success
                last_entry.primitive_action_log = action_logs

                if not success:
                    break

                if (
                    not args.disable_monitoring
                    and next_state.subtask.subtask_type == "Monitor"
                ):
                    next_state, monitored_subtask = agent.bayesian_estimate(next_state)
                    next_state.completed_entries[-1].monitored_subtask = (
                        monitored_subtask
                    )

                current_state = next_state
                if not current_state.remaining_subtasks:
                    is_end = True
    finally:
        if ros_executor and args.ros:
            try:
                ros_executor.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down ROS executor: {e}")
        if controller:
            try:
                controller.stop()
            except Exception as e:
                logger.error(f"Error stopping controller: {e}")
        # Force garbage collection to free memory
        gc.collect()

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
                "init_prior_mean": args.init_prior_mean,
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
            "init_prior_mean": init_prior_mean,
            # "simulationTime": total_sim_time,
        }
        if args.case:
            approach_name = "dag_bayesian"
            meta_data = {
                "init_prior_name": constants.INIT_PRIOR_MEAN,
                "init_prior_variance": constants.INIT_PRIOR_VARIANCE,
                "alpha_heuristic": constants.ALPHA_HEURISTIC,
                "beta_heuristic": constants.BETA_HEURISTIC,
                "gamma_heuristic": constants.GAMMA_HEURISTIC,
                "factor_alpha": constants.FACTOR_ALPHA,
                "beam_width": constants.BEAM_WIDTH,
                "beam_depth": constants.SIMULATION_DEPTH,
                "disable_monitoring": not constants.MONITORING_ENABLED,
            }
            result_args.update(
                {
                    "task_name": args.instruction.split(".json")[0],
                    "approach_name": f"{approach_name}_{args.ablation_name}",
                    "case_name": args.case,
                    "dag_bayesian_meta_data": meta_data,
                }
            )
        approach_name_final = (
            f"{approach_name}_{args.ablation_name}"
            if args.ablation_name
            else approach_name
        )
        save_scene_state(
            controller=controller,
            output_path=Path(f"assets/results/states{int(init_prior_mean)}"),
            case_name=args.case,
            scene_name=scene_name,
            instruction=args.instruction.split(".json")[0],
            approach_name=f"{approach_name_final}",
            state_label="end",
        )
        result_save(**result_args)


if __name__ == "__main__":
    main()
