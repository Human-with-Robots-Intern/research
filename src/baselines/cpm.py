from __future__ import annotations

import argparse
import copy
import heapq
import os
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from src.models.dataclass import (
    ActionResult,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from src.models.task import Duration, Execution, Subtask


# ROS imports

from src.scheduler.action_handler import ActionHandler
from src.utils.io_utils import task_io

from src.core.agent import Agent
from ithor.utils.math_utils import adjust_if_unreachable, load_navigation_graph
from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.utils.common import create_module_logger
from src.utils.io_utils.result_saver import result_save
from src.utils.io_utils.task_io import (
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
)
from src.utils.task.task_util import TaskUtil


class ExecutionPredictionInfo(NamedTuple):
    """Stores execution prediction information for a subtask."""

    predicted_exec_time: float
    nav_time_to_succ: float
    predicted_exec_info: ActionResult


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the CPM scheduler."""
    parser = argparse.ArgumentParser(
        description="Critical Path Method (CPM) Task Scheduler"
    )
    parser.add_argument(
        "-d",
        "--decomposition",
        default=True,
        action="store_true",
        help="태스크 분해 여부 (default: True)",
    )

    parser.add_argument(
        "-r",
        "--reset",
        default=True,
        action="store_true",
        help="리셋 실행 여부 (default: True)",
    )
    parser.add_argument(
        "-s",
        "--simulation",
        default=False,
        action="store_true",
        help="시뮬레이션 실행 여부 (default: False)",
    )
    parser.add_argument(
        "--ros",
        default=True,
        action="store_true",
        help="ROS 실행 여부 (default: False)",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: WARNING)",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan301",
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)",
    )
    return parser.parse_args()


def compute_nav_time(
    subtask: Subtask, current_state: SchedulerState
) -> Tuple[float, Dict[str, Tuple[float, float, float]]]:
    """
    subtask의 첫 번째 primitive action이 NAVIGATE_TO일 경우, 해당 액션의 소요 시간을 계산합니다.

    Args:
        subtask: 현재 실행할 Subtask 객체
        current_state: 현재 SchedulerState 객체
        action_handler: 액션 실행 관련 정보를 제공하는 ActionHandler 객체

    Returns:
        Tuple containing:
        - Navigation time (0.0 if no navigation needed)
        - Navigation positions dictionary

    Raises:
        ValueError: subtask의 첫 번째 액션이 NAVIGATE_TO가 아닐 경우
    """
    nav_time = 0.0
    nav_positions = {}

    if not subtask.execution or not subtask.execution.primitive_actions:
        return nav_time, nav_positions

    first_action = subtask.execution.primitive_actions[0]
    if not first_action.startswith("NAVIGATE_TO"):
        raise ValueError(f"[{subtask.name}] 첫 번째 액션이 NAVIGATE_TO가 아닙니다.")

    # SimulationNode를 생성하여 해당 액션만 시뮬레이션
    temp_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=current_state,
    )
    nav_info = action_handler.get_actions_info(temp_node, [first_action])
    if nav_info:
        nav_time = nav_info.cumulative_time
        nav_positions = nav_info.scene_positions

    return nav_time, nav_positions


def offline_subtask_execution(
    current_state: SchedulerState, next_subtask: Subtask
) -> ActionResult:
    """
    Simulate subtask execution offline to predict execution time and results.

    Args:
        current_state: Current scheduler state
        next_subtask: Subtask to simulate execution for

    Returns:
        ActionResult containing execution information

    Raises:
        ValueError: If no action information is available
    """
    temp_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=current_state,
    )
    actions = next_subtask.execution.primitive_actions or []
    exec_info = action_handler.get_actions_info(temp_node, actions) if actions else None

    if not exec_info:
        raise ValueError(f"[{next_subtask.name}] 액션 정보가 없습니다.")

    return exec_info


def update_state(
    current_state: SchedulerState, next_subtask: Subtask, exec_info: ActionResult
) -> SchedulerState:
    """
    Update scheduler state after executing a subtask.

    Args:
        current_state: Current scheduler state
        next_subtask: Completed subtask
        exec_info: Execution result information

    Returns:
        Updated scheduler state
    """
    subtask_duration = exec_info.cumulative_time
    subtask_entry = CompletedEntry(
        subtask=next_subtask,
        schedule_start_time=current_state.current_time,
        schedule_end_time=current_state.current_time + subtask_duration,
    )

    new_completed = current_state.completed_entries + [subtask_entry]
    new_remaining = [
        st for st in current_state.remaining_subtasks if st.name != next_subtask.name
    ]
    next_state = SchedulerState(
        subtask=next_subtask,
        completed_entries=new_completed,
        remaining_subtasks=new_remaining,
        constraints=constraints,
        current_time=current_state.current_time + subtask_duration,
        scene_positions=exec_info.scene_positions,
        held_object=current_state.held_object,
        agent_location=current_state.agent_location,
    )
    return next_state


def find_critical_path(subtasks: List[Subtask]) -> List[Tuple[Subtask, float, bool]]:
    """
    Find the critical path in the task graph.

    Args:
        subtasks: List of all subtasks

    Returns:
        List of tuples containing (subtask, interval, is_critical) for each node in critical path
    """
    start_nodes = [n for n in constraints.nodes if constraints.in_degree(n) == 0]
    end_nodes = [n for n in constraints.nodes if constraints.out_degree(n) == 0]
    # 모든 경로 파악
    all_paths: List[List[str]] = []
    for start in start_nodes:
        for end in end_nodes:
            all_paths.extend(nx.all_simple_paths(constraints, start, end))
    # Create a mapping from subtask names to subtask objects
    name_to_subtask = {subtask.name: subtask for subtask in subtasks}
    # Convert string paths to subtask paths
    critical_path: List[Tuple[Subtask, float, bool]] = []

    for path in all_paths:
        for i, name in enumerate(path):
            subtask = name_to_subtask[name]
            next_name = path[i + 1] if i < len(path) - 1 else None
            interval = None
            is_critical = None

            if next_name:
                edge_data = next(
                    (
                        data
                        for u, v, data in constraints.out_edges(name, data=True)
                        if v == next_name
                    ),
                    None,
                )
                if edge_data:
                    is_critical = edge_data["info"]["IsCritical"]
                    interval = edge_data["info"].get("Interval")

            critical_path.append((subtask, interval, is_critical))

    return critical_path


def nav_and_wait_during_interval(
    current_state: SchedulerState,
    interval: float,
    next_subtask: Subtask,
    is_critical: bool,
) -> Tuple[List[CompletedEntry], SchedulerState]:
    """
    Create navigation and wait subtasks during a given time interval.

    Args:
        interval: 채워야 할 시간 간격
        next_subtask: 준비할 다음 Subtask 객체
        is_critical: 이 세그먼트가 중요한 경로 세그먼트인지 여부

    Returns:
        Tuple containing:
        - List of created navigation/wait entries
        - Updated scheduler state

    Raises:
        ValueError: next_subtask의 첫 번째 액션이 NAVIGATE_TO가 아닐 경우
    """
    entries: List[CompletedEntry] = []
    current_time = current_state.current_time

    first_action = next_subtask.execution.primitive_actions[0]
    if not first_action.startswith("NAVIGATE_TO"):
        raise ValueError(
            f"[{next_subtask.name}] 첫 번째 액션이 NAVIGATE_TO가 아닙니다."
        )
    # Calculate navigation time
    nav_time, nav_positions = compute_nav_time(next_subtask, current_state)

    if 0.0 < nav_time <= interval:
        # Create NAVIGATE subtask
        nav_subtask = Subtask(
            task_name=next_subtask.task_name,
            name=f"NAVIGATE_TO_{first_action.split()[1]}",
            repetition=1,
            subtask_type="NAVIGATE",
            execution=Execution(objects={}, primitive_actions=[first_action]),
            duration=Duration(type="NAVIGATE", interval=nav_time),
            temporal_constraints=[],
        )

        nav_entry = CompletedEntry(
            subtask=nav_subtask,
            schedule_start_time=current_time,
            schedule_end_time=current_time + nav_time,
        )
        entries.append(nav_entry)
        current_time += nav_time

        # Create wait subtask if needed
    wait_time = interval - nav_time
    if wait_time > 0:
        wait_subtask = Subtask(
            task_name=next_subtask.task_name,
            name=f"WAIT {wait_time} to {next_subtask.name}",
            repetition=1,
            subtask_type="WAIT",
            execution=Execution(
                objects={}, primitive_actions=[f"WAIT {wait_time}"]
            ),
            duration=Duration(type="WAIT", interval=wait_time),
            temporal_constraints=[],
        )
        wait_entry = CompletedEntry(
            subtask=wait_subtask,
            schedule_start_time=current_time,
            schedule_end_time=current_time + wait_time,
        )
        entries.append(wait_entry)

        new_state = SchedulerState(
            subtask=current_state.subtask,
            completed_entries=current_state.completed_entries,
            remaining_subtasks=current_state.remaining_subtasks,
            constraints=current_state.constraints,
            current_time=current_time + wait_time,
            scene_positions=nav_positions,
            held_object=current_state.held_object,
            agent_location=current_state.agent_location,
        )
        return entries, new_state

    return entries, current_state


def get_final_entries(
    critical_path: List[Tuple[Subtask, float, bool]],
    subtasks_without_edge: List[Subtask],
    init_state: SchedulerState,
) -> List[CompletedEntry]:
    """
    Generate final schedule entries considering critical path and unconstrained subtasks.

    Args:
        critical_path: 각 원소가 (Subtask, interval, is_critical) 형태로 구성된 critical path 리스트
        subtasks_without_edge: 제약(엣지)에 포함되지 않은 서브태스크 리스트
        init_state: 초기 스케줄러 상태
    Returns:
        최종적으로 스케줄된 CompletedEntry들의 리스트
    """
    current_state = init_state
    final_entry_schedule: List[CompletedEntry] = []

    for i, (subtask, interval, is_critical) in enumerate(critical_path):
        # 우선 schedule_order에 있는 subtask를 돌면서 simulate_subtask_execution을 해준다.
        exec_info = offline_subtask_execution(current_state, subtask)
        nav_time, _ = compute_nav_time(subtask, current_state)

        final_entry_schedule.append(
            CompletedEntry(
                subtask=subtask,
                schedule_start_time=current_state.current_time,
                schedule_end_time=current_state.current_time
                + exec_info.cumulative_time,
                schedule_nav_time=nav_time,
            )
        )
        current_state = update_state(current_state, subtask, exec_info)

        if interval is None:
            continue
        # interval에 실행 가능한 subtask가 있으면 스케쥴링.
        interval_time_used = 0.0
        while True:
            # Calculate execution predictions for all non-edge subtasks
            expected_ne_subtask_info: Dict[Subtask, ExecutionPredictionInfo] = {}
            for non_edge_subtask in subtasks_without_edge:
                predicted_exec_info = offline_subtask_execution(
                    current_state, non_edge_subtask
                )
                predicted_exec_time = predicted_exec_info.cumulative_time
                predicted_next_state = update_state(
                    current_state, non_edge_subtask, predicted_exec_info
                )
                # Get the succeeding subtask from critical path
                succ_subtask = (
                    critical_path[i + 1][0] if i + 1 < len(critical_path) else None
                )
                nav_time_to_succ = (
                    compute_nav_time(succ_subtask, predicted_next_state)[0]
                    if succ_subtask
                    else 0.0
                )

                expected_ne_subtask_info[non_edge_subtask] = ExecutionPredictionInfo(
                    predicted_exec_time=predicted_exec_time,
                    nav_time_to_succ=nav_time_to_succ,
                    predicted_exec_info=predicted_exec_info,
                )
            # 남은 interval 시간 내에 실행 가능한 subtask만 후보로 선택
            remaining_interval = interval - interval_time_used
            candidate_subtasks = {
                st: info.predicted_exec_time
                for st, info in expected_ne_subtask_info.items()
                if info.predicted_exec_time
                <= remaining_interval - info.nav_time_to_succ
            }

            if not candidate_subtasks and remaining_interval >= 0:
                if (
                    expected_ne_subtask_info and not is_critical
                ):  # Check if expected_info_dict is not empty
                    # non critical edge가 활성화 되어 있고 실행 가능한 subtask는 있으면 그 중 제일 짧은걸 실행시킨다.
                    shortest_subtask = min(
                        expected_ne_subtask_info.items(),
                        key=lambda item: item[1].predicted_exec_time,
                    )[0]
                    shortest_exec_info = expected_ne_subtask_info[
                        shortest_subtask
                    ].predicted_exec_info
                    shortest_nav_time = expected_ne_subtask_info[
                        shortest_subtask
                    ].nav_time_to_succ

                    shortest_entry = CompletedEntry(
                        subtask=shortest_subtask,
                        schedule_start_time=current_state.current_time,
                        schedule_end_time=current_state.current_time
                        + shortest_exec_info.cumulative_time,
                        schedule_nav_time=shortest_nav_time,
                    )
                    final_entry_schedule.append(shortest_entry)
                    current_state = update_state(
                        current_state, shortest_subtask, shortest_exec_info
                    )
                    subtasks_without_edge.remove(shortest_subtask)
                    break
                if i + 1 < len(critical_path):
                    next_subtask_in_cp = critical_path[i + 1][0]
                    nav_wait_entries, current_state = nav_and_wait_during_interval(
                        current_state,
                        remaining_interval,
                        next_subtask_in_cp,
                        is_critical,
                    )
                    final_entry_schedule.extend(nav_wait_entries)
                break

            # Execute longest fitting subtask
            best_subtask = max(candidate_subtasks.items(), key=lambda item: item[1])[0]
            best_exec_info = expected_ne_subtask_info[best_subtask].predicted_exec_info
            interval_time_used += best_exec_info.cumulative_time

            final_entry_schedule.append(
                CompletedEntry(
                    subtask=best_subtask,
                    schedule_start_time=current_state.current_time,
                    schedule_end_time=current_state.current_time
                    + best_exec_info.cumulative_time,
                )
            )

            best_subtask.start_time_scheduled = current_state.current_time
            best_subtask.end_time_scheduled = (
                current_state.current_time + best_exec_info.cumulative_time
            )
            current_state = update_state(current_state, best_subtask, best_exec_info)
            subtasks_without_edge.remove(best_subtask)

    # Schedule remaining unconstrained subtasks
    for left_subtask in subtasks_without_edge:
        left_exec_info = offline_subtask_execution(current_state, left_subtask)
        final_entry_schedule.append(
            CompletedEntry(
                subtask=left_subtask,
                schedule_start_time=current_state.current_time,
                schedule_end_time=current_state.current_time
                + left_exec_info.cumulative_time,
            )
        )
        left_subtask.start_time_scheduled = current_state.current_time
        left_subtask.end_time_scheduled = (
            current_state.current_time + left_exec_info.cumulative_time
        )
        current_state = update_state(current_state, left_subtask, left_exec_info)

    return final_entry_schedule


def main() -> None:
    """Main execution function for the CPM scheduler."""
    
    approach_name = "cpm"
    args: argparse.Namespace = parse_arguments()
    scene_name: str = args.scene

    global action_handler, constraints
    # Initialize controller, navigation graph, and scene
    if args.ros:
        controller = None
        nav_graph = {(0, 0, 0): {(0, 0, 0)}}
        action_handler = ActionHandler(nav_graph, log_level=args.log_level)
    else:
        controller = init_ai2thor_controller(scene_name)
        nav_graph = load_navigation_graph(controller)
        action_handler = ActionHandler(nav_graph, log_level=args.log_level)

    scene_poses: Dict[str, Any] = load_scene_positions(f"{scene_name}_positions.json")


    # Load task data
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files, scene_name=scene_name)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = task_file_name
    # if choice != 0:
    #     input_natural_language = task_io.get_natural_language_from_task_file(
    #         f"{choice}"
    #     )

    # Build tasks and constraints
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data,
        scene_file_name=f"{scene_name}_physics_environment.json",
        enable_decomposition=args.decomposition,
    )

    # Find subtasks without edge constraints
    subtasks_without_edge = [
        s
        for s in subtasks
        if all(
            s.name != str1 and s.name != str2
            for (str1, str2) in list(constraints.edges)
        )
    ]

    init_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

    # Calculate schedule
    start_time = time.time()
    critical_path = find_critical_path(subtasks)
    final_scheduled_entries = get_final_entries(
        critical_path, subtasks_without_edge, init_state
    )
    computation_time = time.time() - start_time

    # Run simulation if enabled
    if args.simulation:
        approach_name = f"{approach_name}_simulation"
        simulation_time = 0.0

        for entry in final_scheduled_entries:
            subtask = entry.subtask
            subtask_time, execution_status, sim_nav_time = execute_subtask(
                controller, subtask, args.log_level
            )
            entry.sim_start_time = simulation_time
            entry.sim_end_time = simulation_time + subtask_time
            simulation_time += subtask_time
            entry.execution_status = execution_status
            entry.sim_nav_time = sim_nav_time

        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": final_scheduled_entries,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "constraints": constraints,
            "initial_plan_data": task_data,
        }
        result_save(**result_args)
        print("end")
    if args.ros:
        from src.ros.ttp_ws.ttp_client.ttp_client.ros_communicate import communicate, init_ros_communication, shutdown_ros_communication
        from src.ros.ttp_ws.ttp_client.ttp_client.translate import InstructionTranslator
        translator = InstructionTranslator()
        init_ros_communication()
        try:
            for entry in final_scheduled_entries:
                subtask = entry.subtask
                primitive_actions = subtask.execution.primitive_actions
                if not primitive_actions:
                    continue
                for primitive_action in primitive_actions:
                    primitive_action_parts = primitive_action.split(" ")
                    if primitive_action_parts[0].lower() == "wait":
                        time.sleep(float(primitive_action_parts[1]))
                        continue
                    translated_primitive_action = translator.translate(primitive_action)
                    success = communicate(translated_primitive_action)
                    if not success:
                        print(f"Action '{primitive_action}' failed. Stopping task.")
                        # 여기서 루프를 중단할지 여부는 정책에 따라 결정할 수 있습니다.
                        # 여기서는 바깥 루프까지 중단하도록 처리합니다.
                        break
                else:  # 내부 루프가 break 없이 완료된 경우
                    continue
                break  # 내부 루프가 break로 중단된 경우 외부 루프도 중단
        finally:
            shutdown_ros_communication()


if __name__ == "__main__":
    main()
