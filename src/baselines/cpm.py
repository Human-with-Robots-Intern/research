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

from core.dataclass import ActionResult, CompletedEntry, SimulationNode, SchedulerState
from core.task import Subtask, Execution
from scheduler.action_handler import ActionHandler
from utils.io_utils import task_io

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller

from core.agent import Agent
from ithor.utils.math_utils import adjust_if_unreachable, load_navigation_graph
from utils.common import create_module_logger
from utils.config.constants import (

    SCENE_NAME,
)
from utils.io_utils.result_saver import result_save
from utils.io_utils.task_io import (
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
    load_scene_positions,
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
        "-v",
        "--visualize",
        default=True,
        action="store_true",
        help="시각화 실행 여부 (default: True)",
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
    help="로그 출력 수준 설정 (default: DEBUG)"
    )
    return parser.parse_args()

def find_critical_path(    
    subtasks: List[Subtask],
    init_state: SchedulerState,
) -> Tuple[List[Subtask]]:
    """
    모든 가능한 경로 중 각 subtask의 duration.interval 및 temporal constraint interval의 합이 가장 큰 경로를
    critical path로 선택합니다.
    
    Args:
        edges: 태스크 간 관계를 나타내는 간선 리스트
        subtasks: Subtask 객체 리스트
    
    Returns:
        (critical_path): 최대 시간 소요 경로와 보유 객체
    """

    # 시작 및 종료 노드 파악 (진입/진출 간선이 없는 노드)
    start_nodes = [n for n in constraints.nodes if constraints.in_degree(n) == 0]
    end_nodes = [n for n in constraints.nodes if constraints.out_degree(n) == 0]

    # 모든 경로 파악
    all_paths: List[List[str]] = []
    for start in start_nodes:
        for end in end_nodes:
            all_paths.extend(nx.all_simple_paths(constraints, start, end))

    max_time = -1
    critical_path: List[Subtask] = []

    # 각 경로에 대해 소요 시간을 계산
    for path in all_paths:
        path_time = 0
        current_time = init_state.current_time
        current_state = copy.deepcopy(init_state)       
        current_path: List[Subtask] = []

        for i, task_name in enumerate(path):
            next_subtask = next((s for s in subtasks if s.name == task_name), None)            
            if next_subtask:
                exec_info = offline_subtask_execution(current_state, next_subtask)
                current_state = update_state(current_state, next_subtask, exec_info)                
                subtask_duration = exec_info.time_used                
                # 현재 subtask와 path의 다음 subtask 간의 temporal constraint interval을 고려하여 대기 시간 계산
                incoming_edges = list(constraints.in_edges(next_subtask.name, data=True)) 
                if incoming_edges:
                    interval = next(
                        data['info']["Interval"]
                        for u, v, data in incoming_edges
                        if u == path[i - 1]
                    )
                                    
                    if interval > 0:
                        path_time += interval
                path_time += subtask_duration
                current_path.append(next_subtask)
                
        if path_time > max_time:
            max_time = path_time
            critical_path = current_path

    return critical_path

def schedule_with_cp_priority(
    critical_path: List[Subtask],
    subtasks: List[Subtask],
) -> List[Tuple[Subtask, float]]:
    """
    주어진 태스크 간 간선 관계와 critical path 정보를 바탕으로,
    CP 내의 태스크 우선순위를 반영한 위상 정렬 방식으로 스케줄 순서를 결정합니다.
    
    Args:
        constraints: 태스크 간 관계를 나타내는 DiGraph 객체
        critical_path: critical path 상의 태스크 순서 리스트
    
    Returns:
        위상 정렬에 따른 태스크 실행 순서 리스트. 각 원소는 (노드 이름, interval) 
    """
    edges = list(constraints.edges)
    graph: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = defaultdict(int)
    nodes: set = set()

    # 그래프 구성 및 노드 집합 생성
    for (u, v) in edges:
        graph[u].append(v)
        nodes.add(u)
        nodes.add(v)

    for node in nodes:
        in_degree[node] = 0

    for (u, v) in edges:
        in_degree[v] += 1

    # critical path 내 태스크의 우선순위 맵 (인덱스 낮을수록 우선순위 높음)
    cp_priority: Dict[str, int] = {task: idx for idx, task in enumerate(critical_path)}
    INF_PRIORITY = len(critical_path) + 999

    def get_priority(task_name: str) -> int:
        return cp_priority.get(task_name, INF_PRIORITY)

    # 우선순위 큐 초기화: 진입차수가 0인 노드를 cp 우선순위에 따라 삽입
    priority_queue: List[Tuple[int, int, str]] = []
    idx = 0
    for node in nodes:
        if in_degree[node] == 0:
            heapq.heappush(priority_queue, (get_priority(node), idx, node))
            idx += 1

    schedule:  List[str] = []
    while priority_queue:
        _, _, current = heapq.heappop(priority_queue)
        schedule.append(current)
        for next_node in graph[current]:
            in_degree[next_node] -= 1
            if in_degree[next_node] == 0:
                heapq.heappush(priority_queue, (get_priority(next_node), idx, next_node))
                idx += 1

    name_to_subtask: Dict[str, Subtask] = {s.name: s for s in subtasks}
    #[subtask, interval, is_critical]
    schedule_with_interval: List[Tuple[Subtask, float]] = []
    for i in range(len(schedule)):
        # 다음 노드와 이어진 edge 가 있으면 저장하는 코드
        interval = None
        if i < len(schedule) - 1 and constraints.has_edge(schedule[i], schedule[i+1]):
            edge_data = constraints.get_edge_data(schedule[i], schedule[i+1])
            # edge_data에서 'info' dict와 "Interval" 키가 존재하는지 확인            
            interval = edge_data['info'].get("Interval")
        schedule_with_interval.append((name_to_subtask[schedule[i]], interval))

    return schedule_with_interval

def last_calculte_schedule_and_time(
    schedule_order: List[str],
    subtasks: List[Subtask],   
    constraints: DiGraph, 
    nav_graph: nx.Graph,
    scene_poses: Dict[str, Any],
    held_object: Any = None,   # 현재 보유 객체
    
) -> Tuple[float, List[CompletedEntry]]:
    # 이 함수는 아래 함수에 흡수 통합 될 예정이다.
    """
    스케줄 순서에 따라 각 subtask의 시작 및 종료 시간을 계산합니다.
    temporal constraint가 존재하는 경우에는 compute_nav_time()을 사용하여 추가 대기 시간을 반영합니다.
    
    Args:
        schedule_order: 태스크 실행 순서 리스트
        subtasks: Subtask 객체 리스트
        held_object: 현재 보유 객체
        nav_graph: 네비게이션 그래프
        scene_positions: 씬 내 위치 정보
    
    Returns:
        (total_time, result_schedule_with_time): 전체 소요 시간과 시간 정보가 포함된 CompletedEntry 리스트
    """
    total_time = 0.0
    scheduled_entries: List[CompletedEntry] = []

   
    init_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)

    for task_name in schedule_order:
        subtask = next((s for s in subtasks if s.name == task_name), None)
        if not subtask:
            continue

        # temporal constraint에 따른 대기 시간 계산
        for temp_constraint in subtask.temporal_constraints:
            if getattr(temp_constraint, "interval", 0) > 0:
                # 선행 태스크가 끝난 시간 이후 interval만큼 대기 필요
                prior_entry = next(
                    (entry for entry in scheduled_entries if entry.subtask.name == temp_constraint.subtask),
                    None,
                )
                if prior_entry:
                    earliest_start = prior_entry.end_time + temp_constraint.interval
                    if earliest_start > total_time:
                        waiting_gap = earliest_start - total_time
                        # NAVIGATE_TO 액션을 통한 이동 시간 계산
                        nav_time = compute_nav_time(subtask, current_state)
                        # gap 동안 이동과 대기를 합산
                        if nav_time > waiting_gap:
                            total_time += waiting_gap
                        else:
                            total_time += nav_time
                            remaining_wait = waiting_gap - nav_time
                            if remaining_wait > 0:
                                total_time += remaining_wait
                        current_state = current_state._replace(current_time=total_time)

        # subtask 실행: 단순 duration.interval을 이용하여 시간 누적
        start_time = total_time
        exec_time = float(subtask.duration.interval)
        total_time += exec_time
        end_time = total_time

        subtask.start_time_scheduled = start_time
        subtask.end_time_scheduled = end_time

        scheduled_entries.append(CompletedEntry(subtask, start_time, end_time))
        current_state = current_state._replace(current_time=total_time)

    return total_time, scheduled_entries

def compute_nav_time(
    subtask: Subtask, current_state: SchedulerState
) -> float:
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
        nav_time = nav_info.time_used

    return nav_time

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

def update_state(current_state: SchedulerState, next_subtask: Subtask, exec_info:ActionResult) -> SchedulerState:
 
    subtask_duration = exec_info.time_used
    subtask_entry = CompletedEntry(
                    subtask=next_subtask,
                    start_time=current_state.current_time,
                    end_time=current_state.current_time + subtask_duration,
                    )
    
    new_completed = current_state.completed_subtasks + [subtask_entry]
    new_remaining = [
        st for st in current_state.remaining_subtasks if st.name != next_subtask.name
    ]

    next_state = SchedulerState(
        subtask=next_subtask,
        completed_subtasks=new_completed,
        remaining_subtasks=new_remaining,
        constraints=constraints,
        current_time= current_state.current_time + subtask_duration,
        scene_positions=exec_info.scene_positions,
        held_object=current_state.held_object,
        agent_location=current_state.agent_location,
    )

    return next_state

def get_final_entries(
                    schedule_order: List[Tuple[Subtask,float,bool]], 
                    subtasks_witout_edge: List[Subtask], 
                    init_state:SchedulerState
                    ) -> List[Subtask]:
    # schedule_order에는 subtask 사이에 edge 가 존재한다
    # critical edge에는 총 subtask execution time <= critical edge interval이 될때까지 subtask를 집어 넣고
    # non-critical edge 에는 subtask execution time > non-critical edge interval 이 될 때 까지 subtask를 집어넣고
    # 남은 subtask들은 전부 맨 뒤로 삽입.
    current_state = init_state
    final_entry_schedule: List[CompletedEntry] = []

    for subtask, interval in schedule_order:
        # 우선 schedule_order에 있는 subtask를 돌면서 simulate_subtask_execution을 해준다.
        exec_info = offline_subtask_execution(current_state, subtask)
        current_state = update_state(current_state, subtask, exec_info)
        subtask.start_time_scheduled = current_state.current_time
        subtask.end_time_scheduled = current_state.current_time + exec_info.time_used

        final_entry_schedule.append(
            CompletedEntry( 
                subtask=subtask,
                start_time=current_state.current_time,
                end_time=current_state.current_time + exec_info.time_used,))

        if interval is None:
            continue
        # interval에 실행 가능한 subtask가 있으면 스케쥴.
        while interval > 0 :
            expected_time_dict: dict[Subtask, float] = {}
            for non_edge_subtask in subtasks_witout_edge:
                # 현재 상태에서 non_edge_subtask를 실행했을 때 execution_time을 dict로 저장.
                exeptected_exec_info = offline_subtask_execution(current_state, non_edge_subtask)
                expected_execution_time =exeptected_exec_info.time_used
                expected_time_dict[non_edge_subtask] = expected_execution_time

            candidates = {k: v for k, v in expected_time_dict.items() if v <= interval}

            if candidates:
                best_subtask = max(candidates.items(), key=lambda item: item[1])[0]
            else:
                best_subtask = None
                break

            if best_subtask:
                best_exec_info = offline_subtask_execution(current_state, non_edge_subtask)
                current_state = update_state(current_state, best_subtask, best_exec_info)
                final_entry_schedule.append(
                    CompletedEntry( 
                        subtask=best_subtask,
                        start_time=current_state.current_time,
                        end_time=current_state.current_time + best_exec_info.time_used,))
                best_subtask.start_time_scheduled = current_state.current_time
                best_subtask.end_time_scheduled = current_state.current_time + expected_time_dict[best_subtask]
                interval -= expected_time_dict[best_subtask]
                subtasks_witout_edge.remove(best_subtask)
    # 남은 subtask가 있으면 뒤에 연달아서 붙혀준다.
    for left_subtask in subtasks_witout_edge:
        left_exec_info = offline_subtask_execution(current_state, left_subtask)
        current_state = update_state(current_state, left_subtask, left_exec_info)
        final_entry_schedule.append(
            CompletedEntry( 
                subtask=left_subtask,
                start_time=current_state.current_time,
                end_time=current_state.current_time + left_exec_info.time_used,))
        left_subtask.start_time_scheduled = current_state.current_time
        left_subtask.end_time_scheduled = current_state.current_time + left_exec_info.time_used

    return final_entry_schedule
            
def main() -> None:
    approach_name = "cpm"
    args: argparse.Namespace = parse_arguments()   
    
    
    # 초기화: 컨트롤러, 네비게이션 그래프, 씬 정보
    controller = init_ai2thor_controller()
    nav_graph = load_navigation_graph(controller)

    global action_handler, constraints   
     
    scene_name: str = SCENE_NAME
    scene_poses: Dict[str, Any] = load_scene_positions(f"{scene_name}_positions.json")
    action_handler = ActionHandler(nav_graph)
    

    # 사용자로부터 task 파일 선택 및 로드
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language: str = task_io.get_natural_language_from_task_file(f"{choice}")

    
    # Task 및 constraint 생성 (태스크 분해 여부에 따라)
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(task_data, args.decomposition)    
    subtasks_witout_edge = [s for s in subtasks 
                            if all(s.name != str1 and s.name != str2 for (str1, str2) in list(constraints.edges))]
    
    init_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)
    
    # ===== 스케줄 계산 시작 =====
    start_time = time.time()
    # 1) Critical Path 계산
    critical_path = find_critical_path(subtasks, init_state)
    # 2) Critical Path 우선순위에 따른 path 스케줄 정렬
    schedule_order = schedule_with_cp_priority(critical_path, subtasks)
    # 3) # edge가 없는 subtasks 를 스케쥴에 삽입하여 최종 엔트리 리스트를 얻음
    final_scheduled_entries = get_final_entries(schedule_order, subtasks_witout_edge, init_state)


    computation_time = time.time() - start_time
    
    # ===== (옵션) 시뮬레이션 실행 =====
    if args.simulation:
        approach_name = f"{approach_name}_simulation"

        simulation_time = 0.0
        for entry in final_scheduled_entries:
            subtask = entry.subtask
            subtask_time, execution_status = execute_subtask(controller, subtask, args.log_level)
            subtask.start_time_simulation = simulation_time
            subtask.end_time_simulation = simulation_time + subtask_time
            simulation_time += subtask_time
            subtask.execution_status = execution_status

        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": final_scheduled_entries,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "constraints": constraints,
        }
        result_save(**result_args)

    # 시각화 옵션이 활성화된 경우
    if args.visualize:
        visualize(approach_name, input_natural_language, constraints, final_scheduled_entries)

if __name__ == "__main__":
    main()
