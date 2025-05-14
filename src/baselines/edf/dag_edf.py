import argparse
import heapq
import time
from pathlib import Path
from typing import List, Optional, Tuple

import networkx as nx

from simulation.runner_ai2thor import execute_subtask
from utils.common.logger import create_module_logger
from utils.io_utils import task_io
from utils.io_utils.result_saver import result_save

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
)  # 프로젝트 루트 경로
ASSETS_PATH = PROJECT_ROOT / Path("assets")  # assets 폴더 경로
from dataclass import CompletedEntry, SchedulerState, SimulationNode

from core.task import *
from ithor.utils.math_utils import load_navigation_graph
from scheduler.action_handler import ActionHandler
from simulation.runner_ai2thor import init_ai2thor_controller
from utils.config.constants import RESULT_PATH
from utils.io_utils.task_io import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
)
from utils.task.task_util import TaskUtil


def is_executable(subtask: Subtask, current_state: SchedulerState) -> bool:
    """
    subtask가 dependency 때문에 실행 가능한지 여부 반환
    """
    constraints = current_state.constraints
    incoming = list(constraints.in_edges(subtask.name))
    if incoming:  # dependency가 있는 경우
        # 단순히 첫번째 dependency가 완료되었는지 여부로 판단
        pred_name = incoming[0][0]
        completed = {entry.subtask.name for entry in current_state.completed_entries}
        return pred_name in completed
    return True  # dependency가 없으면 실행 가능


def compute_nav_time(
    subtask: Subtask, current_state: SchedulerState, action_handler: ActionHandler
) -> float:
    """
    subtask 내 첫 번째 NAVIGATE_TO primitive action의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(
        deadline=current_state.current_time,
        simulation_subtask=subtask,
        state=current_state,
        execution_time=0.0
    )
    nav_time = 0.0

    # 모든 subtask의 첫 action은 NAVIGATE_TO 로 시작되어야 한다. 아니라면 문제가 있는것. 확인하라
    if not subtask.execution.primitive_actions[0].startswith("NAVIGATE_TO"):
        raise ("first action is not NAVIGATE_TO")

    for act in subtask.execution.primitive_actions or []:
        if act.startswith("NAVIGATE_TO"):
            nav_info = action_handler.get_actions_info(temp_node, [act])
            if nav_info:
                nav_time = nav_info.action_duration
            break

    return nav_time


def offline_subtask_execution(
    subtask: Subtask, current_state: SchedulerState, action_handler: ActionHandler
) -> float:
    """
    현재 subtask의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(
        deadline=current_state.current_time,
        simulation_subtask=subtask,
        state=current_state,
        execution_time=0.0
    )
    actions = subtask.execution.primitive_actions or []
    exec_info = action_handler.get_actions_info(temp_node, actions) if actions else None

    # exec_info를 추출하는데 실패할경우 None을 return
    return exec_info if exec_info else None


def compute_deadline_for_subtask(
    subtask: Subtask,
    current_state: SchedulerState,
    nav_time: float,
    execution_time: float,
) -> float:
    """
    subtask에 대한 deadline을 timeslot 유형과 dependency 조건에 따라 계산한다.

    [규칙]
        1. 기본규칙
            deadline = current_time + execution_time(이동시간 포함)
        2. subtask가 non critical in edge만 있으면 (이동의 시작시간을 deadline으로 설정해서 실제 행위의 시작이 constraint를 만족하도록 설정.):
            deadline = max(선행 subtask의 end_time + edge의 interval)-nav_time
        3. subtask가 critical in edge를 포함한다면:
            deadline = critical edge의(선행 subtask의 end_time + edge interval)-nav_time

    """
    # 가독성을 위한 변수 선언
    constraints = current_state.constraints
    current_time = current_state.current_time

    # 현재 subtask가 가진 edge들의 list
    incoming_edges = list(constraints.in_edges(subtask.name, data=True))
    # 현재 subtask가 critical edge를 가지는지
    critical_edges = [
        (u, v, data)
        for u, v, data in incoming_edges
        if data.get("info", {}).get("IsCritical", False)
    ]
    # 기본 deadline
    deadline = current_time + execution_time

    if incoming_edges:
        # 규칙 2
        non_critical_deadlines = [
            next(
                (
                    entry.schedule_end_time
                    for entry in current_state.completed_entries
                    if entry.subtask.name == u
                ),
                current_time,
            )
            + data["info"]["Interval"]
            for u, v, data in incoming_edges
        ]
        # 두 non-critical-edge가 있으면 그중 느린쪽에 맞추면 해결됨. critical이 존재하면 아래에서 덮어 써짐.
        deadline = max(non_critical_deadlines)-nav_time

    if critical_edges:
        # 규칙 3
        critical_deadlines = [
            next(
                (
                    entry.schedule_end_time
                    for entry in current_state.completed_entries
                    if entry.subtask.name == u
                ),
                current_time,
            )
            + data["info"]["Interval"]
            for u, v, data in critical_edges
        ]
        # 어짜피 두 critical edge가 있으면 둘중 하나는 포기해야하므로 급한거 먼저 처리하도록 구성. 그러나 critical이 두개 있는경우는 없음
        deadline = min(critical_deadlines)-nav_time

    return deadline


def get_next_subtask_edf(current_state: SchedulerState, action_handler: ActionHandler) -> Optional[Subtask]:
    """
    각 실행 가능한 subtask에 대해 deadline을 산출한 후, deadline이 가장 짧은 subtask를 선택한다.
    """
    import heapq

    queue = []
    for subtask in current_state.remaining_subtasks:
        if not is_executable(subtask, current_state):
            continue

        nav_time = compute_nav_time(subtask, current_state, action_handler)
        exec_info = offline_subtask_execution(subtask, current_state, action_handler)
        execution_time = exec_info.cumulative_time 
        deadline = compute_deadline_for_subtask(subtask, current_state, nav_time, execution_time)
        sim_node = SimulationNode(
            deadline=deadline, simulation_subtask=subtask, state=current_state, execution_time=execution_time
        )
        heapq.heappush(queue, sim_node)
        # remaining_subtask들의 deadline 정보를 삽입
        subtask.deadline = deadline

    if queue:
        chosen_node = heapq.heappop(queue)
        chosen_node.simulation_subtask.duration.interval = chosen_node.execution_time
        return chosen_node.simulation_subtask

    return None


def update(
    current_state: SchedulerState, next_subtask: Subtask, action_handler: ActionHandler
) -> SchedulerState:
    """
    1) next_subtask 실행 시간 시뮬레이션 후 subtask.duration.interval 에 반영
    2) After 제약(interval=X)이 있으면, designated_start = predecessor.end_time + X
        - current_time < designated_start => NAVIGATE_TO + WAIT subtask를 CompletedEntry로 추가
    3) next_subtask 실행 CompletedEntry 추가
    """
    # -------------------------------
    # 1) 실제 실행 시간 시뮬레이션
    # -------------------------------
    current_time = current_state.current_time

    #get_next_subtask_edf 함수에서 이미 실행 시간을 계산해서 반환해줌
    real_exec_time = next_subtask.duration.interval

    # subtask의 duration.interval은 이미 최신 실행 시간으로 반영되어 있음

    # -------------------------------
    # 2) After 제약(interval=X) 처리
    # -------------------------------
    constraints = current_state.constraints
    incoming_edges = list(constraints.in_edges(next_subtask.name, data=True))
    designated_start = current_time  # 기본적으로는 지금 바로 시작

    # 현재 edge 가 critical이면 critical subtask의 predecessor를 찾아서 그 subtask 기준으로 연산해야함.
    # 아니면 아무거나 써도 됨.

    wait_entries = []
    # incoming_edge 가 있으면 deadline 규칙에 따라 연산된 deadline 시간에 subtask 시작
    if incoming_edges:
        designated_start = next_subtask.deadline

    new_current_time = current_time
    nav_time = compute_nav_time(next_subtask, current_state, action_handler)
    # 만약 current_time < designated_start 라면 => 대기 필요
    if new_current_time < designated_start:
        # NAVIGATE_TO는 TaskUtil.refine_primitive_actions()에 의해 첫 번째 액션으로 보장됨
        nav_action = next_subtask.execution.primitive_actions[0]
        # NAVIGATE_TO에 걸리는 시간 계산
        
        # NAVIGATE_TO CompletedEntry
        nav_entry = CompletedEntry(
            subtask=Subtask(
                task_name=next_subtask.task_name,
                name=f"NAVIGATE_TO_{nav_action.split()[1]}",
                repetition=1,
                subtask_type="NAVIGATE",
                execution=Execution(objects={}, primitive_actions=[nav_action]),
                duration=Duration(type="NAVIGATE", interval=nav_time),
                temporal_constraints=[],
            ),
            schedule_start_time=new_current_time,
            schedule_end_time=new_current_time + nav_time,
            actual_first_nav_duration=nav_time,
        )
        wait_entries.append(nav_entry)
        new_current_time += nav_time
        # 남은 시간(= designated_start - new_current_time) 만큼 WAIT
        remaining_wait = designated_start - new_current_time
        if remaining_wait > 0:
            wait_entry = CompletedEntry(
                subtask=Subtask(
                    task_name=next_subtask.task_name,
                    name=f"WAIT {remaining_wait} for {next_subtask.name}",
                    repetition=1,
                    subtask_type="WAIT",
                    execution=Execution(
                        objects={}, primitive_actions=[f"WAIT {remaining_wait}"]
                    ),
                    duration=Duration(type="WAIT", interval=remaining_wait),
                    temporal_constraints=[],
                ),
                schedule_start_time=new_current_time,
                schedule_end_time=designated_start,
                actual_first_nav_duration=0,
            )
            wait_entries.append(wait_entry)
            new_current_time = designated_start
    # -------------------------------
    # 3) next_subtask 실행
    # -------------------------------
    subtask_entry = CompletedEntry(
        subtask=next_subtask,
        schedule_start_time=new_current_time,
        schedule_end_time=new_current_time + real_exec_time,
        actual_first_nav_duration= 0 if wait_entries else nav_time,
        schedule_nav_time=nav_time,
    )
    new_current_time += real_exec_time

    # -------------------------------
    # 완료 목록 및 state 갱신
    # -------------------------------
    new_completed = current_state.completed_entries + wait_entries + [subtask_entry]
    new_remaining = [
        st for st in current_state.remaining_subtasks if st.name != next_subtask.name
    ]

    updated_state = SchedulerState(
        subtask=next_subtask,
        completed_entries=new_completed,
        remaining_subtasks=new_remaining,
        constraints=constraints,
        current_time=new_current_time,
        scene_positions=current_state.scene_positions,
        held_object=current_state.held_object,
        agent_location=current_state.agent_location
    )
    return updated_state


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

    # 현재 미사용중인 argument들은 주석처리되었다.
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
    parser.add_argument(
        "-s",
        "--simulation",
        default=True,
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
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)",
    )
    return parser.parse_args()


def main():
    # Set up the AI2-THOR controller and navigation graph
    approach_name = "dag_edf"
    
    args = parse_arguments()
    scene_name = args.scene

    controller = init_ai2thor_controller(scene_name)
    nav_graph = load_navigation_graph(controller)
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")
    action_handler = ActionHandler(nav_graph, log_level=args.log_level)

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files, scene_name=scene_name) 
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = task_file_name
    if choice != 0:
        input_natural_language = task_io.get_natural_language_from_task_file(f"{choice}")
    # Build tasks and constraints
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(task_data, scene_file_name = f"{scene_name}_physics_environment.json")

    computation_time = 0
    current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)
    result_schedule = []
    
    # Phase 1: Complete scheduling
    for _ in range(len(subtasks)):
        subtask_scheduling_time_start = time.time()
        next_subtask = get_next_subtask_edf(current_state, action_handler)

        if next_subtask is None:
            break
        current_state = update(current_state, next_subtask, action_handler)
        subtask_scheduling_time = time.time() - subtask_scheduling_time_start
        computation_time += subtask_scheduling_time

    result_schedule = current_state.completed_entries
    result_schedule.pop(0)  # Remove the init entry

    # Phase 2: Execute simulation if requested
    if args.simulation:
        approach_name = f"{approach_name}_simulation"
        simulation_current_time = 0.0   
        # Execute each subtask in the schedule
        for entry in result_schedule:
            subtask_time, execution_status, sim_nav_time = execute_subtask(
                controller, entry.subtask, args.log_level
            )
            # Update the entry with simulation times and execution status
            entry.sim_start_time = simulation_current_time
            entry.sim_end_time = simulation_current_time + subtask_time
            entry.execution_status = execution_status
            entry.sim_nav_time = sim_nav_time
            simulation_current_time += subtask_time

    output_path = RESULT_PATH / input_natural_language / "metadata"
    output_path.mkdir(parents=True, exist_ok=True)
    
    result_args = {
        "task_name": input_natural_language,
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": computation_time,
        "scene_name": scene_name,
        "constraints": constraints,
    }

    result_save(**result_args)


if __name__ == "__main__":
    main()
