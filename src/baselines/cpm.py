import argparse
import copy
import heapq
import os
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import networkx as nx
from networkx import DiGraph

from core.dataclass import ActionResult, CompletedEntry, SchedulerState, SimulationNode
from core.task import Duration, Execution, Subtask
from scheduler.action_handler import ActionHandler
from utils.io_utils import task_io

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from core.agent import Agent
from ithor.utils.math_utils import adjust_if_unreachable, load_navigation_graph
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from utils.common import create_module_logger
from utils.io_utils.result_saver import result_save
from utils.io_utils.task_io import (
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
)
from utils.task.task_util import TaskUtil
from utils.visualizers.visualizer import visualize


def parse_arguments() -> argparse.Namespace:
    """
    명령행 인자를 파싱합니다.
    """
    parser = argparse.ArgumentParser(description="Task Scheduler")
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
        default=True,
        action="store_true",
        help="시뮬레이션 실행 여부 (default: True)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: DEBUG)",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)",
    )
    return parser.parse_args()


def compute_nav_time(
    subtask: Subtask, current_state: SchedulerState
) -> Tuple[float, dict[str, Tuple[float, float, float]]]:
    """
    subtask의 첫 번째 primitive action이 NAVIGATE_TO일 경우, 해당 액션의 소요 시간을 계산합니다.

    Args:
        subtask: 현재 실행할 Subtask 객체
        current_state: 현재 SchedulerState 객체
        action_handler: 액션 실행 관련 정보를 제공하는 ActionHandler 객체

    Returns:
        NAVIGATE_TO 액션의 소요 시간 (없으면 0)

    Raises:
        ValueError: subtask의 첫 번째 액션이 NAVIGATE_TO가 아닐 경우
    """
    nav_time = 0.0

    if not subtask.execution or not subtask.execution.primitive_actions:
        return nav_time

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


def offline_subtask_execution(current_state: SchedulerState, next_subtask: Subtask):

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


def find_critical_path(
    subtasks: List[Subtask],
) -> List[Tuple[Subtask, float, bool]]:
    """
    edge를 가진 path들을 나열한다.
    이 path의 순열을 보장하고자 하는 최대 시간을 가진 critical_path로 본다.
    """
    # 시작 및 종료 노드 파악 (진입/진출 간선이 없는 노드)
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
        for name in path:
            subtask = name_to_subtask[name]

            # Get the next subtask name in the path, if it exists
            current_idx = path.index(name)
            next_name = path[current_idx + 1] if current_idx < len(path) - 1 else None

            # Check if there is a temporal constraint between current and next subtask
            outgoing_edges = list(constraints.out_edges(subtask.name, data=True))
            is_critical = None
            interval = None
            if outgoing_edges:
                for u, v, data in outgoing_edges:
                    if v == next_name:
                        is_critical = data["info"]["IsCritical"]
                        interval = data["info"].get("Interval")
                        break
            critical_path.append((subtask, interval, is_critical))

    return critical_path


def nav_and_wait_during_interval(
    current_state: SchedulerState,
    interval: float,
    next_subtask: Subtask,
    is_critical: bool,
) -> Tuple[List[CompletedEntry], SchedulerState]:
    """
    주어진 시간(interval) 동안 이동(NAVIGATE)과 대기(WAIT)를 위한 서브태스크를 생성합니다.

    next_subtask의 첫 번째 액션이 NAVIGATE_TO여야 하며,
    네비게이션 소요 시간이 interval보다 작을 경우,
    네비게이션 후 남은 시간만큼 대기하는 WAIT 서브태스크를 생성합니다.

    Args:
        current_state: 현재 스케줄러 상태 (시간, 위치 등 포함)
        interval: 현재 간선에 주어진 시간 간격
        next_subtask: 다음에 실행할 서브태스크. 첫번째 액션은 반드시 NAVIGATE_TO여야 함.
        is_critical: 해당 간선이 critical(필수)인지 여부

    Returns:
        - 생성된 CompletedEntry들의 리스트 (NAVIGATE, WAIT 서브태스크)
        - 업데이트된 SchedulerState (현재 시간 및 위치 갱신)

    Raises:
        ValueError: next_subtask의 첫 번째 액션이 NAVIGATE_TO가 아닐 경우
    """
    entries: List[CompletedEntry] = []
    current_time = current_state.current_time

    # Get the first NAVIGATE_TO action from the next subtask
    first_action = next_subtask.execution.primitive_actions[0]
    if not first_action.startswith("NAVIGATE_TO"):
        raise ValueError(
            f"[{next_subtask.name}] 첫 번째 액션이 NAVIGATE_TO가 아닙니다."
        )
    nav_action = first_action

    # Calculate navigation time
    nav_time, nav_positions = compute_nav_time(next_subtask, current_state)

    # If navigation time is less than remaining interval, create both NAVIGATE and WAIT subtasks
    if nav_time < interval:
        # Create NAVIGATE subtask
        nav_subtask = Subtask(
            task_name=next_subtask.task_name,
            name=f"NAVIGATE_TO_{nav_action.split()[1]}",
            repetition=1,
            subtask_type="NAVIGATE",
            execution=Execution(objects={}, primitive_actions=[nav_action]),
            duration=Duration(type="NAVIGATE", interval=nav_time),
            temporal_constraints=[],
        )
        nav_subtask.start_time_scheduled = current_time
        nav_subtask.end_time_scheduled = current_time + nav_time
        nav_entry = CompletedEntry(
            subtask=nav_subtask,
            schedule_start_time=current_time,
            schedule_end_time=current_time + nav_time,
        )
        entries.append(nav_entry)
        current_time += nav_time

    # Create WAIT subtask for remaining time
    if nav_time > interval:
        # 네비게이션 소요 시간이 interval보다 크면 네비게이션 실행 없이 대기만 한다.
        nav_time = 0
        nav_positions = current_state.scene_positions
    wait_time = interval - nav_time
    wait_subtask = Subtask(
        task_name=next_subtask.task_name,
        name=f"WAIT_{wait_time} to {next_subtask.name}",
        repetition=1,
        subtask_type="WAIT",
        execution=Execution(objects={}, primitive_actions=[f"WAIT {wait_time}"]),
        duration=Duration(type="WAIT", interval=wait_time),
        temporal_constraints=[],
    )
    wait_subtask.start_time_scheduled = current_time
    wait_subtask.end_time_scheduled = current_time + wait_time
    wait_entry = CompletedEntry(
        subtask=wait_subtask,
        schedule_start_time=current_time,
        schedule_end_time=current_time + wait_time,
    )
    entries.append(wait_entry)

    # Create new state instead of modifying the existing one
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


def get_final_entries(
    critical_path: List[Tuple[Subtask, float, bool]],
    subtasks_witout_edge: List[Subtask],
    init_state: SchedulerState,
) -> List[CompletedEntry]:
    """
    Critical Path와 제약(엣지)이 없는 서브태스크들을 고려하여 최종 스케줄 엔트리를 생성합니다.

    [1] 우선, critical_path에 포함된 각 서브태스크를 순서대로 실행(시뮬레이션)하여
        CompletedEntry에 기록하고 스케줄러 상태를 업데이트합니다.
    [2] 각 critical edge에 대해 지정된 interval 내에서 실행 가능한 비(非) critical 서브태스크들을
        탐색하여 추가 실행합니다.
        - 만약 interval 내에 실행 가능한 서브태스크(candidate)가 없다면,
          non-critical 인 경우 실행 시간이 가장 짧은 서브태스크를 실행하거나,
          critical인 경우 nav_and_wait_during_interval() 함수를 호출하여 남은 시간을 채웁니다.
    [3] 마지막으로, 남은 제약이 없는 서브태스크들을 순차적으로 실행하여 스케줄에 추가합니다.

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
        subtask.start_time_scheduled = current_state.current_time
        subtask.end_time_scheduled = (
            current_state.current_time + exec_info.cumulative_time
        )

        final_entry_schedule.append(
            CompletedEntry(
                subtask=subtask,
                schedule_start_time=current_state.current_time,
                schedule_end_time=current_state.current_time + exec_info.cumulative_time,

            )
        )
        current_state = update_state(current_state, subtask, exec_info)

        # interval이 없으면 다음 subtask로 넘어간다.
        if interval is None:
            continue

        # interval에 실행 가능한 subtask가 있으면 스케쥴.
        interval_time_used = 0.0
        while True:
            # 현재 상태에서 실행 가능한 모든 subtask의 예상 실행 시간 계산
            expected_time_dict: dict[Subtask, float] = {}
            for non_edge_subtask in subtasks_witout_edge:
                # 현재 상태에서 non_edge_subtask를 실행했을 때 execution_time을 dict로 저장.
                exeptected_exec_info = offline_subtask_execution(
                    current_state, non_edge_subtask
                )
                expected_execution_time = exeptected_exec_info.cumulative_time
                expected_time_dict[non_edge_subtask] = expected_execution_time
            # 남은 interval 시간 내에 실행 가능한 subtask만 후보로 선택
            remaining_interval = interval - interval_time_used

            candidate_subtasks = {
                subtask: time_used
                for subtask, time_used in expected_time_dict.items()
                if time_used <= remaining_interval
            }

            if not candidate_subtasks and remaining_interval >= 0:
                if expected_time_dict and not is_critical:
                    # For non-critical edges
                    # non edge subtask 가 있으면 그걸 실행하고 탐색 중단.
                    shortest_subtask = min(
                        expected_time_dict.items(), key=lambda item: item[1]
                    )[0]
                    shortest_exec_info = offline_subtask_execution(
                        current_state, shortest_subtask
                    )
                    shortest_subtask.start_time_scheduled = current_state.current_time
                    shortest_subtask.end_time_scheduled = (
                        current_state.current_time + shortest_exec_info.cumulative_time
                    )
                    shortest_entry = CompletedEntry(
                        subtask=shortest_subtask,
                        schedule_start_time=current_state.current_time,
                        schedule_end_time=current_state.current_time
                        + shortest_exec_info.cumulative_time,
                    )
                    final_entry_schedule.append(shortest_entry)
                    current_state = update_state(
                        current_state, shortest_subtask, shortest_exec_info
                    )
                    subtasks_witout_edge.remove(shortest_subtask)
                    break

                next_subtask = critical_path[i + 1][0]
                # nav time 이 interval보다 크면 빈 list를 반환한다.
                nav_wait_entries, current_state = nav_and_wait_during_interval(
                    current_state, remaining_interval, next_subtask, is_critical
                )
                final_entry_schedule.extend(nav_wait_entries)
                break

            # 가장 긴 실행 시간을 가진 subtask 선택
            best_subtask = max(candidate_subtasks.items(), key=lambda item: item[1])[0]
            # 선택된 subtask 실행
            best_exec_info = offline_subtask_execution(current_state, best_subtask)
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
            subtasks_witout_edge.remove(best_subtask)

    # 남은 subtask가 있으면 뒤에 연달아서 붙혀준다.
    for left_subtask in subtasks_witout_edge:
        left_exec_info = offline_subtask_execution(current_state, left_subtask)
        final_entry_schedule.append(
            CompletedEntry(
                subtask=left_subtask,
                schedule_start_time=current_state.current_time,
                schedule_end_time=current_state.current_time + left_exec_info.cumulative_time,
            )
        )
        left_subtask.start_time_scheduled = current_state.current_time
        left_subtask.end_time_scheduled = (
            current_state.current_time + left_exec_info.cumulative_time
        )
        current_state = update_state(current_state, left_subtask, left_exec_info)

    return final_entry_schedule


def main() -> None:
    approach_name = "cpm"
    args: argparse.Namespace = parse_arguments()
    scene_name: str = args.scene

    # 초기화: 컨트롤러, 네비게이션 그래프, 씬 정보
    controller = init_ai2thor_controller(scene_name)
    nav_graph = load_navigation_graph(controller)

    global action_handler, constraints

    
    scene_poses: Dict[str, Any] = load_scene_positions(f"{scene_name}_positions.json")
    action_handler = ActionHandler(nav_graph)

    # 사용자로부터 task 파일 선택 및 로드
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files, scene_name=scene_name) 
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = task_file_name
    if choice != 0:
        input_natural_language = task_io.get_natural_language_from_task_file(f"{choice}")
    
    # Task 및 constraint 생성 (태스크 분해 여부에 따라)
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, f"{scene_name}_physics_environment.json", args.decomposition
    )
    subtasks_witout_edge = [
        s
        for s in subtasks
        if all(
            s.name != str1 and s.name != str2
            for (str1, str2) in list(constraints.edges)
        )
    ]

    init_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

    # ===== 스케줄 계산 시작 =====
    start_time = time.time()
    # 1) Critical Path 계산
    critical_path = find_critical_path(subtasks)
    # 2) Critical Path 우선순위에 따른 path 스케줄 정렬
    # 3) # edge가 없는 subtasks 를 스케쥴에 삽입하여 최종 엔트리 리스트를 얻음
    final_scheduled_entries = get_final_entries(
        critical_path, subtasks_witout_edge, init_state
    )

    computation_time = time.time() - start_time

    # ===== (옵션) 시뮬레이션 실행 =====
    if args.simulation:
        approach_name = f"{approach_name}_simulation"
        simulation_time = 0.0
        for entry in final_scheduled_entries:
            subtask = entry.subtask
            subtask_time, execution_status = execute_subtask(
                controller, subtask, args.log_level
            )
            entry.sim_start_time = simulation_time
            entry.sim_end_time = simulation_time + subtask_time
            simulation_time += subtask_time
            entry.execution_status = execution_status

        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": final_scheduled_entries,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "constraints": constraints,
        }
        result_save(**result_args)



if __name__ == "__main__":
    main()
