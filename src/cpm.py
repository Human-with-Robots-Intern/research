import networkx as nx
import heapq
from collections import defaultdict
import argparse

from core.agent import Agent
from core.scheduler import Scheduler
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.constants import LOG_ROUND
from utils.task import (
    build_tasks_and_constraints,
    get_init_state,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)
import json
from utils.constants import KNOWLEDGE_PATH

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
        # default=True,
        action="store_true",
    )
    return parser.parse_args()

def main():
    """Main entry point for the Task Scheduler."""
    args = parse_arguments()

    if args.simulation:
        controller = init_ai2thor()

    task_files = list_task_files()
    task_file_name = get_user_task_choice(task_files, choice = 16)

    # Load the chosen task data
    task_data = load_task_data_from_file(task_file_name)

    # Build tasks and constraints
    subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)
    edges = list(constraints.edges)

    # Visualize the task graph if enabled
    if args.visualize:
        visualize(task_file_name, constraints)

    agent = Agent()

    scheduler = Scheduler()

    result_schedule = []

    critical_path = find_critical_path(edges, subtasks)

    # 스케줄링 실행
    result_schedule = schedule_with_cp_priority(edges, critical_path)

    # 스케쥴링 끝난 거 앞에서 부터 시간 계산하기. 만약에 dependency가 지켜지지 않으면 wait넣기
    total_time, schedule_subtask_time = last_calculte_schedule_and_time(result_schedule, subtasks)

    print("=== Combined single-scheduler with CP priority ===")
    for step in result_schedule:
        print(" -", step)

def paths(edges):
    # 방향 그래프 생성
    G = nx.DiGraph(edges)

    # 시작 노드 찾기 (들어오는 간선이 없는 노드)
    start_nodes = [node for node in G.nodes if G.in_degree(node) == 0]

    # 끝 노드 찾기 (나가는 간선이 없는 노드)
    end_nodes = [node for node in G.nodes if G.out_degree(node) == 0]

    # 모든 경로 찾기
    all_paths = []
    for start in start_nodes:
        for end in end_nodes:
            paths = list(nx.all_simple_paths(G, source=start, target=end))
            all_paths.extend(paths)

    return all_paths

def find_critical_path(edges, subtasks):
    all_paths = paths(edges)
    total_time = []
    for path in all_paths:
        # 각 path의 실행시간 더하기 (subtask 시간 + interval(with nav))
        path_total_time = 0.0
        start_location = None
        # path에 있는 subtask를 실행하는 시간을 더해서 해당 path의 실행 시간 구하기
        for i in range(len(path)):
            subtask = next((subtask for subtask in subtasks if subtask.name == path[i]), None)
            subtask_total_time, last_location = subtask_time(subtask, start_location)
            start_location = last_location
            # # 이 subtask로 인해 추가되는 시간
            path_total_time += subtask_total_time
            # dependency의 interval 더해주기
            temporal_constraints = subtask.temporal_constraints
            for obj in temporal_constraints:
                    if hasattr(obj, 'interval') and obj.interval:
                        if obj.interval:
                            path_total_time += obj.interval
        total_time.append(path_total_time)
    # all_paths와 total_time에서 total_time이 있는 idx와 같은 위치의 all_paths 값을 불러와서 critical_path에 저장하기
    critical_path = all_paths[total_time.index(max(total_time))]

    return critical_path

def subtask_time(subtask, start_location):
    # subtask 안에서 nav하는 시간
    nav_time, last_location = subtask_nav_time(subtask, start_location)
    # subtask 실행시간
    subtask_interval = subtask.duration.interval
    # 이 subtask로 인해 추가되는 시간
    subtask_total_time = nav_time + subtask_interval
    return subtask_total_time, last_location

def subtask_nav_time(subtask, start_location):
    # 1) Ensure we have a known robot location
    if start_location is None:
        #start_location = "agent"
        start_location = subtask.execution.primitive_actions[0].split(" ")[1]
        start_location = start_location.split("_")[0]

    nav_time = 0.0
    current_source = start_location

    # 2) If no primitive_actions or no NAVIGATE_TO, no nav time needed
    if not subtask.execution or not subtask.execution.primitive_actions:
        return 0.0, start_location

    # 3) Accumulate travel time for each NAVIGATE_TO
    target_loc = current_source
    for action in subtask.execution.primitive_actions:
        if action.startswith("NAVIGATE_TO"):
            # e.g. "NAVIGATE_TO Kitchen"
            target_loc = action.split("NAVIGATE_TO")[1].strip()
            step_time = specific_nav_time(source=current_source, target=target_loc)
            nav_time += step_time
            current_source = target_loc
    
    return nav_time, target_loc

def load_navigation_time():
    with open(KNOWLEDGE_PATH / "FloorPlan1_physics_navigation_time.json", "r") as f:
        navigation_times = json.load(f)
    return navigation_times

def specific_nav_time(source: str, target: str) -> float:
    """
    Look up the travel time from 'source' to 'target' in navigation_times.
    If not found, return 0.0 and log a warning.

    Note: If you need partial matching or fuzzy matching,
            adapt the dictionary access logic accordingly.
    """
    navigation_time = load_navigation_time()
    # 공백이 있으면 obj stop_time 이렇게 되어있는거고, stop_time 이 결국 총 nav time 이 될 듯
    if " " in source:
        source = source.split(" ")[0]
    if " " in target:
        return float(target.split(" ")[1])
    
    matched_source_key = next(
        (k for k in navigation_time if k.startswith(source)), None
    )
    if not matched_source_key:
        log.warning(f"No source key matched for '{source}' in navigation times.")
        return 0.0

    matched_target_key = next(
        (k for k in navigation_time[matched_source_key] if target in k),
        None,
    )
    if not matched_target_key:
        log.warning(
            f"No target key matched for '{target}' under '{matched_source_key}'."
        )
        return 0.0

    move_time = navigation_time[matched_source_key].get(
        matched_target_key, None
    )
    if move_time is None:
        log.warning(
            f"Navigation time from '{matched_source_key}' to '{matched_target_key}' not found."
        )
        return 0.0
    return move_time

def schedule_with_cp_priority(edges, critical_path):
    """
    edges         : List[Tuple[str, str]] 
                   - (선행작업, 후행작업)
    critical_path : List[str]
                   - 가장 우선순위가 높은 순서대로 나열된 Critical Path 상의 작업들
                   
    return        : List[str]
                   - 모든 작업을 '의존성'을 지키며, Critical Path 작업은 
                     가능한 한 먼저 실행하도록 우선순위를 적용한 스케줄 순서
    """
    # 1) 그래프(인접 리스트)와 진입차수(in_degree) 구성
    graph = defaultdict(list)   # graph[A] = [B, C, ...] => A가 끝나야 시작 가능한 작업들
    in_degree = defaultdict(int)
    tasks = set()

    # 모든 간선/노드 등록
    for src, dst in edges:
        graph[src].append(dst)
        tasks.add(src)
        tasks.add(dst)

    # 모든 노드 초기 진입차수 설정(없는 노드도 0으로)
    for t in tasks:
        in_degree[t] = 0
    for src, dst in edges:
        in_degree[dst] += 1

    # 2) Critical Path 작업에 대한 우선순위 맵핑
    #    - critical_path의 인덱스가 작을수록 높은 우선순위
    #    - critical_path에 없는 작업은 뒤쪽 우선순위를 매긴다
    cp_index_map = {}
    for i, t in enumerate(critical_path):
        cp_index_map[t] = i
    
    # critical_path에 속하지 않은 작업들은 충분히 큰 우선순위(= CP 마지막 뒤)로 설정
    NOT_IN_CP_PRIORITY = len(critical_path) + 100
    
    def get_cp_priority(task):
        return cp_index_map[task] if task in cp_index_map else NOT_IN_CP_PRIORITY

    # 3) 우선순위 큐(최소 힙) 초기화
    #    - (우선순위, 일련번호, 작업명) 형태로 저장하여 우선순위 -> FIFO 순서로 작업
    pq = []
    counter = 0  # tie-breaker (동일 우선순위일 때 먼저 들어온 것 우선)

    # 진입차수가 0인 작업을 우선순위 큐에 넣는다
    for t in tasks:
        if in_degree[t] == 0:
            heapq.heappush(pq, (get_cp_priority(t), counter, t))
            counter += 1

    # 4) 스케줄링
    schedule = []
    while pq:
        cp_pri, _, task = heapq.heappop(pq)
        schedule.append(task)

        # task가 끝났으므로, task를 선행으로 두던 후행들의 in_degree를 감소
        for nxt in graph[task]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                heapq.heappush(pq, (get_cp_priority(nxt), counter, nxt))
                counter += 1

    return schedule

def last_calculte_schedule_and_time(result_schedule, subtasks):
    # 스케쥴링 한 것 따라서 시간 순차적으로 더하기. 더할 때 dependency를 체크해서 아직 시간이 도달하지 않았다면 nav와 wait subtask 생성하기.
    total_time = 0
    schedule_subtask_and_time = {}
    start_location = "agent"
    # subtask 하나 씩 구하기
    for i in range(len(result_schedule)):
        subtask = next((subtask for subtask in subtasks if subtask.name == result_schedule[i]), None)
        temporal_constraints = subtask.temporal_constraints
        for obj in temporal_constraints:
            if hasattr(obj, 'interval') and obj.interval:
                if obj.interval:
                    # 앞에서 부터 숫자 더해서 start subtask 까지 더하고 거기에 interval을 추가. 현재 total time이랑 비교해서 interval이 더 크면 nav시간 구해서 nav subtask랑 wait subtask를 만들어서 추가.
                    start_subtask_name = obj.subtask
                    # start subtask + interval
                    start_subtask_end_time = 0
                    for key in schedule_subtask_and_time:
                        start_subtask_end_time += schedule_subtask_and_time[key]
                        if key == start_subtask_name:  # 원하는 키까지 더했으면 종료
                            break
                    start_time_of_end_subtask = start_subtask_end_time + obj.interval

                    if start_time_of_end_subtask > total_time:
                        start_subtask = next((subtask for subtask in subtasks if subtask.name == start_subtask_name), None)
                        nav_start_location = start_subtask.execution.primitive_actions[0].split(" ")[1]
                        nav_start_location = nav_start_location.split("_")[0]

                        nav_end_location = subtask.execution.primitive_actions[0].split(" ")[1]
                        nav_end_location = nav_end_location.split("_")[0]
                        # nav 시간 구하기. schedule_subtask_and_time에 nav_{result_schedule[i]} 넣기
                        nav_time = specific_nav_time(nav_start_location, nav_end_location)
                        schedule_subtask_and_time.update({f"nav_{result_schedule[i]}": nav_time})
                        # interval-nav시간 만큼 schedule_subtask_and_time에 wait_{result_schedule[i]} 넣기
                        wait_time = obj.interval - nav_time
                        schedule_subtask_and_time.update({f"wait_{result_schedule[i]}": wait_time})
                        # 전체 시간 update
                        total_time += (nav_time + wait_time)
                        # 그리고 start_location을 end subtask의 시작 위치로 만들어줘야 함.
                        start_location = nav_end_location
  
        # subtask 
        subtask_total_time, last_location = subtask_time(subtask, start_location)
        start_location = last_location
        total_time += subtask_total_time
        schedule_subtask_and_time.update({subtask.name : subtask.duration.interval})
    
    return total_time, schedule_subtask_and_time




if __name__ == "__main__":
    main()