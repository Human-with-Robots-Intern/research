import argparse
import heapq
import os
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import networkx as nx

from core.dataclass import CompletedEntry, SimulationNode, SchedulerState
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

log = create_module_logger(module_name=__name__, module_log=True)


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
    return parser.parse_args()


def find_critical_path(
    edges: List[Tuple[str, str]],
    subtasks: List[Subtask],
    held_object: Any,
) -> Tuple[List[str], Any]:
    """
    모든 가능한 경로 중 각 subtask의 duration.interval 및 temporal constraint interval의 합이 가장 큰 경로를
    critical path로 선택합니다.
    
    Args:
        edges: 태스크 간 관계를 나타내는 간선 리스트
        subtasks: Subtask 객체 리스트
        held_object: 현재 보유 객체 (변경 없이 그대로 전달)
        nav_graph: 네비게이션 그래프
    
    Returns:
        (critical_path, held_object): 최대 시간 소요 경로와 보유 객체
    """
    G = nx.DiGraph()
    G.add_edges_from(edges)

    # 시작 및 종료 노드 파악 (진입/진출 간선이 없는 노드)
    start_nodes = [n for n in G.nodes if G.in_degree(n) == 0]
    end_nodes = [n for n in G.nodes if G.out_degree(n) == 0]

    all_paths: List[List[str]] = []
    for start in start_nodes:
        for end in end_nodes:
            all_paths.extend(nx.all_simple_paths(G, start, end))

    max_time = -1
    critical_path: List[str] = []

    # 각 경로에 대해 소요 시간을 계산
    for path in all_paths:
        path_time = 0
        for task_name in path:
            subtask = next((s for s in subtasks if s.name == task_name), None)
            if subtask:
                path_time += subtask.duration.interval
                # 각 temporal constraint의 interval도 합산
                for temp_constraint in subtask.temporal_constraints:
                    path_time += temp_constraint.interval
        if path_time > max_time:
            max_time = path_time
            critical_path = path

    return critical_path, held_object


def schedule_with_cp_priority(
    edges: List[Tuple[str, str]], critical_path: List[str]
) -> List[str]:
    """
    주어진 태스크 간 간선 관계와 critical path 정보를 바탕으로,
    CP 내의 태스크 우선순위를 반영한 위상 정렬 방식으로 스케줄 순서를 결정합니다.
    
    Args:
        edges: 태스크 간 관계 (간선 리스트)
        critical_path: critical path 상의 태스크 순서 리스트
    
    Returns:
        위상 정렬에 따른 태스크 실행 순서 리스트
    """
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

    schedule: List[str] = []
    while priority_queue:
        _, _, current = heapq.heappop(priority_queue)
        schedule.append(current)
        for next_node in graph[current]:
            in_degree[next_node] -= 1
            if in_degree[next_node] == 0:
                heapq.heappush(priority_queue, (get_priority(next_node), idx, next_node))
                idx += 1

    return schedule


def last_calculte_schedule_and_time(
    schedule_order: List[str],
    subtasks: List[Subtask],
    held_object: Any,
    nav_graph: nx.Graph,
    scene_positions: Dict[str, Any],
) -> Tuple[float, List[CompletedEntry]]:
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

    action_handler = ActionHandler(nav_graph)
    current_state = SchedulerState(
        subtask=None,
        completed_subtasks=[],
        remaining_subtasks=[],
        constraints=nx.DiGraph(),
        current_time=0.0,
        scene_positions=scene_positions,
        held_object=None,
        agent_location=None,
    )

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
                        nav_time = compute_nav_time(subtask, current_state, action_handler)
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
    subtask: Subtask, current_state: SchedulerState, action_handler: ActionHandler
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




def main() -> None:
    approach_name = "cpm"
    args: argparse.Namespace = parse_arguments()
    held_object: Any = None

    # 초기화: 컨트롤러, 네비게이션 그래프, 씬 정보
    controller = init_ai2thor_controller()
    nav_graph = load_navigation_graph(controller)
    scene_name: str = SCENE_NAME
    scene_positions: Dict[str, Any] = load_scene_positions(f"{scene_name}_positions.json")

    # 사용자로부터 task 파일 선택 및 로드
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language: str = task_io.get_natural_language_from_task_file(f"{choice}")
    

    # Task 및 constraint 생성 (태스크 분해 여부에 따라)
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(task_data, args.decomposition)
    edge_list = list(constraints.edges)

    
    # ===== 스케줄 계산 시작 =====
    start_time = time.time()

    # 1) Critical Path 계산
    critical_path, held_object = find_critical_path(edge_list, subtasks, held_object, nav_graph)

    # 2) Critical Path 우선순위에 따른 스케줄 정렬
    schedule_order = schedule_with_cp_priority(edge_list, critical_path)

    # 3) 최종 스케줄 및 전체 소요 시간 계산
    total_time, scheduled_entries = last_calculte_schedule_and_time(
        schedule_order, subtasks, held_object, nav_graph, scene_positions
    )    

    computation_time = time.time() - start_time
    # 시각화 옵션이 활성화된 경우
    
    # ===== (옵션) 시뮬레이션 실행 =====
    if args.simulation:
        approach_name = f"{approach_name}_simulation"

        simulation_time = 0.0
        for entry in scheduled_entries:
            subtask = entry.subtask
            subtask_time, execution_status = execute_subtask(controller, subtask)
            subtask.start_time_simulation = simulation_time
            subtask.end_time_simulation = simulation_time + subtask_time
            simulation_time += subtask_time
            subtask.execution_status = execution_status

        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": scheduled_entries,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "constraints": constraints,
        }
        result_save(**result_args)

    # 결과 출력
    print(f"total_time = {total_time}")
    print("Schedule with time:")
    for entry in scheduled_entries:
        print(f" - {entry.subtask.name}: {entry.start_time} ~ {entry.end_time}")

        
    if args.visualize:
        visualize(approach_name, input_natural_language, constraints, scheduled_entries)


if __name__ == "__main__":
    main()
