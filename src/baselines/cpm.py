import argparse
import heapq
import json
import math
from collections import defaultdict
import time
from typing import Callable, Dict, List, Set, Tuple

import networkx as nx
import os, sys

from core.task import Subtask,Execution





sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from core.agent import Agent
from core.scheduler import Scheduler
from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.result_saver import result_save
from utils.constants import (
    KNOWLEDGE_PATH,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)
from utils.task import (
    build_tasks_and_constraints,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
    task_io,
)

from utils.math_utils import adjust_if_unreachable, build_navigation_graph

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
        "-s",
        "--simulation",
        # default=True,
        action="store_true",
    )
    return parser.parse_args()


def main():
    """Main entry point for the Task Scheduler."""
    approach_name = "DAG OS Scheduling(cpm)"
    args = parse_arguments()
    held_object = None

    # Set up the AI2-THOR controller and navigation graph
    controller = init_ai2thor()
    nav_graph = build_navigation_graph(controller)

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name = get_user_task_choice(task_files, ) # already chosen
    task_data = load_task_data_from_file(task_file_name)
    
    # Build tasks and constraints
    subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)
    edges = list(constraints.edges)

    # Visualize the task graph if enabled
    if args.visualize:
        visualize(approach_name, task_file_name, constraints)

    agent = Agent()

    shedule_order = []

    critical_path, held_object = find_critical_path(
        edges, subtasks, held_object, nav_graph
    )

    # 스케줄링 실행
    
    computation_time_start = time.time() 
    shedule_order = schedule_with_cp_priority(edges, critical_path)
    computation_time = time.time() - computation_time_start

    # 스케쥴링 끝난 거 앞에서 부터 시간 계산하기. 만약에 dependency가 지켜지지 않으면 wait넣기
    total_time, result_schedule_with_time = last_calculte_schedule_and_time(
        shedule_order, subtasks, held_object, nav_graph
    )
    
    print("total time = ", total_time)
    print("Schedule order with start and end times:")
    for st in result_schedule_with_time:
        print(f" - {st.name}: {st.start_time:.2f} ~ {st.end_time:.2f}")
    print("=== Combined single-scheduler with CP priority ===")
    for step in shedule_order:
        print(" -", step)
    
    result_save(task_file_name, approach_name, result_schedule_with_time, computation_time)


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


def find_critical_path(edges, subtasks, held_object, nav_graph):
    all_paths = paths(edges)
    total_time = []
    for path in all_paths:
        # 각 path의 실행시간 더하기 (subtask 시간 + interval(with nav))
        path_total_time = 0.0
        # path에 있는 subtask를 실행하는 시간을 더해서 해당 path의 실행 시간 구하기
        for i in range(len(path)):
            subtask = next(
                (subtask for subtask in subtasks if subtask.name == path[i]), None
            )
            subtask_total_time, held_object = subtask_time(
                subtask, held_object, nav_graph
            )
            # # 이 subtask로 인해 추가되는 시간
            path_total_time += subtask_total_time
            # dependency의 interval 더해주기
            temporal_constraints = subtask.temporal_constraints
            for obj in temporal_constraints:
                if hasattr(obj, "interval") and obj.interval:
                    if obj.interval:
                        path_total_time += obj.interval
        total_time.append(path_total_time)
    # all_paths와 total_time에서 total_time이 있는 idx와 같은 위치의 all_paths 값을 불러와서 critical_path에 저장하기
    critical_path = all_paths[total_time.index(max(total_time))]

    return critical_path, held_object


def action_duration(action, held_object, nav_graph):

    scene_positions = task_io.load_scene_positions("FloorPlan1_positions.json")

    tokens = action.split()
    if not tokens:
        log.error(f"action is not in exist.")
        raise ValueError(f"action is not in exist")

    action_type = tokens[0].upper()
    target_obj_id = tokens[1] if len(tokens) > 1 else None
    partial_time_str = tokens[2] if len(tokens) > 2 else None

    # 예외: WAIT 이외 액션에서, scene_positions에 없는 오브젝트를 타겟으로 지목
    if target_obj_id and target_obj_id not in scene_positions and action_type != "WAIT":
        log.error(f"Object {target_obj_id} not in scene_positions.")
        raise ValueError(f"Object {target_obj_id} not in scene_positions.")

    # 액션별 소요시간 계산
    if action_type == "NAVIGATE_TO":
        navigate_path = _find_short_path(
            scene_positions["agent"], scene_positions[target_obj_id], nav_graph
        )
        if partial_time_str is None:
            action_duration = len(navigate_path) * NAV_STEP_DURATION
            if navigate_path:
                scene_positions["agent"] = navigate_path[-1]
        else:
            nav_time = float(partial_time_str)
            steps = int(math.floor(nav_time / NAV_STEP_DURATION))
            steps = max(0, min(steps, len(navigate_path) - 1))
            action_duration = nav_time
            if navigate_path:
                scene_positions["agent"] = navigate_path[steps]

    elif action_type == "GRASP":
        if held_object is not None:
            raise ValueError(
                f"Already holding {held_object}, cannot grasp {target_obj_id}."
            )
        held_object = target_obj_id
        action_duration = PRIMITIVE_ACTION_DURATION

    elif action_type in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
        if held_object is None:
            raise ValueError("No object in hand to place.")
        # place 동작
        scene_positions[held_object] = scene_positions[target_obj_id]
        held_object = None
        action_duration = PRIMITIVE_ACTION_DURATION

    elif action_type == "MONITORING":
        action_duration = MONITORING_DURATION

    elif action_type == "WAIT":
        action_duration = float(target_obj_id)  # 예: WAIT 3.0

    elif action_type in PRIMITIVE_ACTION_SET:
        action_duration = PRIMITIVE_ACTION_DURATION

    else:
        log.error(f"Unknown action name: {action_type}")
        raise ValueError(f"Unknown action name: {action_type}")

    return action_duration, held_object


def _find_short_path(
    start_pos: Tuple[float, float, float],
    end_pos: Tuple[float, float, float],
    nav_graph,
):

    start_pos = adjust_if_unreachable(nav_graph, start_pos)
    end_pos = adjust_if_unreachable(nav_graph, end_pos)
    if start_pos == end_pos:
        return [start_pos]

    def direction(a, b):
        return (b[0] - a[0], b[2] - a[2])

    pq = []
    heapq.heappush(pq, (0, start_pos, None, [start_pos]))
    visited = {}

    while pq:
        turn_cnt, cur_pos, cur_dir, path = heapq.heappop(pq)
        if cur_pos == end_pos:
            return path
        if cur_pos in visited and visited[cur_pos] <= turn_cnt:
            continue
        visited[cur_pos] = turn_cnt
        for nxt in nav_graph.get(cur_pos, []):
            if nxt in path:
                continue
            new_dir = direction(cur_pos, nxt)
            nxt_turn = (
                turn_cnt if (cur_dir is None or new_dir == cur_dir) else (turn_cnt + 1)
            )
            new_path = path + [nxt]
            heapq.heappush(pq, (nxt_turn, nxt, new_dir, new_path))

    raise ValueError(f"No path found from {start_pos} to {end_pos}.")


def subtask_time(subtask, held_object, nav_graph):
    subtask_total_time = 0.0
    for action in subtask.execution.primitive_actions:
        subtask_time, held_object = action_duration(action, held_object, nav_graph)
        subtask_total_time += subtask_time
    
    #action에 걸리는 시간인가?

    return subtask_total_time, held_object


def specific_nav_time(action, nav_graph) -> float:
    """
    Look up the travel time from 'source' to 'target' in navigation_times.
    If not found, return 0.0 and log a warning.

    Note: If you need partial matching or fuzzy matching,
            adapt the dictionary access logic accordingly.
    """
    scene_positions = task_io.load_scene_positions("FloorPlan1_positions.json")
    nav_time = None
    tokens = action.split()
    if not tokens:
        log.error(f"action is not in exist.")
        raise ValueError(f"action is not in exist")

    action_type = tokens[0].upper()
    target_obj_id = tokens[1] if len(tokens) > 1 else None
    partial_time_str = tokens[2] if len(tokens) > 2 else None

    if action_type == "NAVIGATE_TO":
        navigate_path = _find_short_path(
            scene_positions["agent"], scene_positions[target_obj_id], nav_graph
        )
        if partial_time_str is None:
            action_duration = len(navigate_path) * NAV_STEP_DURATION
            if navigate_path:
                scene_positions["agent"] = navigate_path[-1]
        else:
            nav_time = float(partial_time_str)
            steps = int(math.floor(nav_time / NAV_STEP_DURATION))
            steps = max(0, min(steps, len(navigate_path) - 1))
            action_duration = nav_time
            if navigate_path:
                scene_positions["agent"] = navigate_path[steps]

    nav_time = action_duration
    # if nav_time is None:
    #     log.warning(
    #         f"Navigation time from '{"agent"}' to '{target_obj_id}' not found."
    #     )
    # return 0.0
    return nav_time


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
    graph = defaultdict(list)  # graph[A] = [B, C, ...] => A가 끝나야 시작 가능한 작업들
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


def last_calculte_schedule_and_time(schedule_order, subtasks, held_object, nav_graph):

    """
    기존 로직 최대한 유지하되,
    - (1) subtask.start_time, subtask.end_time을 기록
    - (2) result_schedule_with_time를 list로 두어 subtask 객체를 append
    - (3) interval/nav_time도 total_time에 더해 주고
    """

    # 스케쥴링 한 것 따라서 시간 순차적으로 더하기. 더할 때 dependency를 체크해서 아직 시간이 도달하지 않았다면 nav와 wait subtask 생성하기.

    total_time = 0
    result_schedule_with_time = []
    # subtask 하나 씩 구하기
    for task_name in schedule_order:
        subtask = next(
            (subtask for subtask in subtasks if subtask.name == task_name),None)
        
        for obj in subtask.temporal_constraints:
            if hasattr(obj, "interval") and obj.interval:
                if obj.interval:
                    # 앞에서 부터 숫자 더해서 start subtask 까지 더하고 거기에 interval을 추가.                     
                    needed_interval = obj.interval
                    start_subtask_name = obj.subtask
                    # start subtask + interval
                    start_subtask_obj = next(
                        (s for s in result_schedule_with_time if s.name == start_subtask_name),
                        None
                    )
                    #subtask에 end_time이 생겼으므로 직접 가져오는 방식으로 계산한다. 
                    #earlist_start는 시작 가능한 가장 빠른 시간을 뜻한다.
                    if start_subtask_obj is not None:
                        earliest_start = start_subtask_obj.end_time + needed_interval

                        if earliest_start > total_time: 
                            # 현재 total time이랑 비교해서 interval이 더 크면 nav시간 구해서 nav subtask랑 wait subtask 객체를 만들어서 추가.
                            # 선행 시간 제약으로 인해 그 제약 시간동안 이동을 수행하고 시간이 또 남으면 wait을 해야한다는 로직
                            # nav 시간 구하기. schedule_subtask_and_time에 nav_{result_schedule[i]} 넣기
                            nav_time = specific_nav_time(
                                subtask.execution.primitive_actions[0], nav_graph
                            )
                            nav_execution_objects=subtask.execution.objects
                            nav_execution_primitive_actions=subtask.execution.primitive_actions[0]
                            nav_execution=Execution(objects=nav_execution_objects, primitive_actions= nav_execution_primitive_actions)
                            nav_subtask = Subtask(task_name=task_name, name="nav",repetition= 1, type="interaction", execution=nav_execution, duration=nav_time)
                            
                            nav_subtask.start_time= total_time
                            nav_subtask.end_time = total_time+nav_time
                            result_schedule_with_time.append(nav_subtask)

                            total_time = nav_subtask.end_time

                            if nav_time < needed_interval:
                                wait_time = needed_interval - nav_time
                                wait_subtask=Subtask(task_name=task_name,name="wait", repetition=1,type="interaction", execution=None, duration= wait_time)
                                wait_subtask.start_time = total_time
                                wait_subtask.end_time = total_time+wait_time
                                result_schedule_with_time.append(wait_subtask)
                                total_time = wait_subtask.end_time
                            else:
                                wait_time = 0.0
                            
                            total_time += (nav_time + wait_time)


        

        # subtask
        subtask.start_time = total_time

        subtask_total_time, held_object = subtask_time(subtask, held_object, nav_graph)
        total_time += subtask_total_time

        subtask.end_time = total_time   

        result_schedule_with_time.append(subtask)

    return total_time, result_schedule_with_time


if __name__ == "__main__":
    main()
