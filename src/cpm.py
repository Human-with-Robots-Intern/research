import networkx as nx
import heapq
from collections import defaultdict
import argparse
import math
from typing import List, Dict, Tuple, Set, Optional

from sim.runner_ai2thor import execute_subtask, init_ai2thor
from utils import create_module_logger, visualize
from utils.constants import PRIMITIVE_ACTION_DURATION, MONITORING_DURATION, NAV_STEP_DURATION, PRIMITIVE_ACTION_SET 
from utils.task import (
    build_tasks_and_constraints,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file
)
from utils.task.task_io import load_scene_positions
from ithor.utils.math_utils import build_navigation_graph, adjust_if_unreachable

from func_for_gantt import func_for_gantt
import time

from core.task import Subtask

# TODO : nav_graph를 어떻게 설명해야할지 모르겠음. math_utils의 build_navigation_graph 이용. 

# Set up logging configuration
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
    """Main entry point for the Task Scheduler.

    Side Effects:
    - It interacts with the AI2-THOR environment to perform tasks.
    - It writes the results of the task schedule to a Gantt chart file using the func_for_gantt module.
    """

    log.info("Starting task scheduling process...")
    args = parse_arguments()

    # Load the chosen task data
    task_files: List[str] = list_task_files()

    for i in range(len(task_files)):
        j = i + 1
        # 코드 실제 실행 시간 기준이 언제 인지. 일단은 파일 불러오기 전으로 함.
        # Track the time when the task starts
        task_started_time = time.time()
        # held_object : the object which the robot hold on its hand.
        held_object : str | None = None
        task_file_name : str = get_user_task_choice(task_files, choice= j)
        task_data = load_task_data_from_file(task_file_name)

        log.info(f"Processing task : {task_file_name}")

        # Set up the AI2-THOR controller and navigation graph
        log.info("Initializing AI2-THOR controller and navigation graph...")
        controller = init_ai2thor()
        nav_graph = build_navigation_graph(controller)

        # Build tasks and constraints
        subtasks, constraints = build_tasks_and_constraints(task_data, args.decomposition)
        edges = list(constraints.edges)

        # Visualize the task graph if enabled
        if args.visualize:
            visualize(task_file_name, constraints)

        result_schedule : List[str] = []

        # Find the critical path
        # held_object : str or None = target_obj_id
        log.info("Finding the critical path...")
        critical_path, held_object = find_critical_path(edges, subtasks, held_object, nav_graph)

        # Schedule tasks with CP priority
        log.info("Scheduling tasks with CP priority...")
        result_schedule = schedule_with_cp_priority(edges, critical_path)

        # schedule_subtask_time : Dict[str, float]
        # Group scheduled subtasks and their times into a dict.
        # If dependency is not finished, insert 'wait' and 'nav' subtasks
        log.info("Calculating the total execution time and adjusting for dependencies...")
        _, schedule_subtask_time = last_calculte_schedule_and_time(result_schedule, subtasks, held_object, nav_graph)

        # Get total executed task of real_time
        task_completed_time = time.time()
        real_time : float = task_completed_time - task_started_time

        # Create a dictionary of subtasks Dict[subtask.name : str, subtask.execution : float]
        subtask_dict = {st.name: st for st in subtasks}

        # execute ai2thor time of each subtask 
        ai2thor_time : List[str] = []
        for i in range(len(schedule_subtask_time)):
            subtask_name = list(schedule_subtask_time.keys())[i]
            subtask = subtask_dict.get(subtask_name) 
            if args.simulation:
                log.info(f"Executing subtask: {subtask_name}")
                ai2thor_time.append = execute_subtask(controller, subtask)
            else:
                ai2thor_time.append(0)
        
        log.debug("Task scheduling completed.")

        # Final schedule with execution times
        final_schedule : Dict[str, List[float]] = {key: [value, float(ai2thor_time[i])] for i, (key, value) in enumerate(schedule_subtask_time.items())}

        # Write the schedule results to a Gantt chart file
        log.info(f"Writing results to Gantt chart file for {task_file_name}")
        func_for_gantt.write_gantt_file("cpm", task_file_name, final_schedule, real_time, edges)

    log.debug("Every task scheduling process finished.")




def paths(edges: List[Tuple[str, str]]) -> List[List[str]]:
    """Find all paths. Path means the list what they have dependency. They have order.

    Args:
        edges (List[Tuple[str, str]]): A list of edges in the graph

    Returns:
        List[List[str]]: A list of all paths.
    """
    # Create directed graph
    G = nx.DiGraph(edges)

    # Find start nodes (nodes with outgoing edges)
    start_nodes = [node for node in G.nodes if G.in_degree(node) == 0]

    # Find end nodes (nodes with incoming edges)
    end_nodes = [node for node in G.nodes if G.out_degree(node) == 0]

    # Find all paths
    all_paths = []
    for start in start_nodes:
        for end in end_nodes:
            paths = list(nx.all_simple_paths(G, source=start, target=end))
            all_paths.extend(paths)
    log.info(f"Total {len(all_paths)} paths found: {all_paths}")

    return all_paths

def find_critical_path(edges: List[Tuple[str, str]], subtasks: List[Subtask], 
                       held_object: Optional[str] , nav_graph: Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]
                        )-> Tuple[List[str], Optional[str]]:
    """Finds the critical path. The critical path is the path that takes the longest time.
    The execution time includes the time for each subtask and the time for navigate subtask to subtask.

    Args:
        edges (List[Tuple[str, str]]): A list of edges in the graph
        subtasks (List[Subtask]): All subtasks in the task
        held_object (Optional[str]): the object which the robot hold on its hand.
        nav_graph (Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]): 

    Returns:
        Tuple[List[str], Optional[str]]: critical_path and updated held_object
    """
    all_paths = paths(edges) # find all paths
    log.debug(f"Found {len(all_paths)} paths.")

    total_time = []
    for path in all_paths:
        path_total_time = 0.0
        
        for i in range(len(path)):
            # get the total time of each path (subtask executed time + dependency interval(with nav))
            # subtask executed time
            subtask = next((subtask for subtask in subtasks if subtask.name == path[i]), None)
            subtask_total_time, held_object = subtask_time(subtask, held_object, nav_graph)
            path_total_time += subtask_total_time
            # the interval of dependency (navigate must done during )
            # FIXME : nav time 구하고 dependency interval과 비교하기. 그중에 큰 걸 더한다.
            #         (일반적으로 dependency interval > nav time 이어서 문제되지 않았다.)
            for obj in subtask.temporal_constraints:
                    if hasattr(obj, 'interval') and obj.interval:
                            path_total_time += obj.interval
        log.info(f"Calculating total time for path: {path} = {path_total_time}")
        total_time.append(path_total_time)
    # Find the path with the maximum total time
    critical_path_idx = total_time.index(max(total_time))
    critical_path = all_paths[critical_path_idx]
    log.debug(f"Critical path found: {critical_path} with time {total_time[critical_path_idx]}")

    return critical_path, held_object

def action_duration(action: str, held_object: Optional[str], 
                    nav_graph: Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]) -> Tuple[float, Optional[str]]:
    """ compute the duration about one action.

    Args:
        action (str): action_type target_obj_id partial_time_str
        held_object (Optional[str]): the object which the robot hold on its hand.
        nav_graph (Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]): _description_

    Returns:
        Tuple[float, Optional[str]]: action_duration, held_object
    """
    # HACK : action_handler의 def _simulate_actions와 거의 같다. 해당 함수를 최적화했으면 같은 방식으로 수정 요망.

    scene_positions = load_scene_positions("FloorPlan1_positions.json")

    tokens = action.split()
    if not tokens:
        log.error(f"action is not in exist.")
        raise ValueError(f"action is not in exist")

    action_type = tokens[0].upper()
    target_obj_id = tokens[1] if len(tokens) > 1 else None
    partial_time_str = tokens[2] if len(tokens) > 2 else None

    # Occur Error: For actions other than WAIT, if the target object is not in scene_positions
    if (
        target_obj_id
        and target_obj_id not in scene_positions
        and action_type != "WAIT"
    ):
        log.error(f"Object {target_obj_id} not in scene_positions.")
        raise ValueError(f"Object {target_obj_id} not in scene_positions.")

    # Calculate the duration for each action
    # Action types : "NAVIGATE TO", "GRASP", "PLACE_INSIDE", "PLACE_ON_TOP", "MONITORING", "WAIT" and {PRIMITIVE_ACTION_SET}
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
        # 지금 이 순간을 위해 main에서 부터 held_object를 데리고 옴...
        # HACK : 위와 같은 이유로 불필요한 부분이 많아보임.
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
    
    log.info(f"Action {action_type} completed. Duration: {action_duration}. Held object: {held_object}")
    
    return action_duration, held_object

def _find_short_path(start_pos: Tuple[float, float, float], end_pos: Tuple[float, float, float]
    , nav_graph: Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]
    ) -> List[Tuple[str]]:
        """find the shorsest path from current position to target object.

        Args:
            start_pos (Tuple[float, float, float]): "agent". You must put the position of agent.
            end_pos (Tuple[float, float, float]): the position of target object.
            nav_graph (Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]): _description_

        Returns:
            List[Tuple[str]]: The shortest path from current position to target object
        """
        # XXX : 지금 이 함수가 뭔지 잘 모르겠음. return값이 왜 저런지도 모르겠음. 근데 오늘은 여기까지.
        # Adjust positions if it is unreachable
        end_pos = adjust_if_unreachable(nav_graph, end_pos)
        # If start and end positions are the same, return the start position as the path
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
                    turn_cnt
                    if (cur_dir is None or new_dir == cur_dir)
                    else (turn_cnt + 1)
                )
                new_path = path + [nxt]
                heapq.heappush(pq, (nxt_turn, nxt, new_dir, new_path))

        raise ValueError(f"No path found from {start_pos} to {end_pos}.")

def subtask_time(subtask, held_object, nav_graph):
    subtask_total_time = 0.0
    for action in subtask.execution.primitive_actions:
        subtask_time, held_object = action_duration(action, held_object, nav_graph)
        subtask_total_time += subtask_time
    
    return subtask_total_time, held_object

def specific_nav_time(action, nav_graph) -> float:
    """
    Look up the travel time from 'source' to 'target' in navigation_times.
    If not found, return 0.0 and log a warning.

    Note: If you need partial matching or fuzzy matching,
            adapt the dictionary access logic accordingly.
    """
    scene_positions = load_scene_positions("FloorPlan1_positions.json")
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

def last_calculte_schedule_and_time(result_schedule, subtasks, held_object, nav_graph):
    # 스케쥴링 한 것 따라서 시간 순차적으로 더하기. 더할 때 dependency를 체크해서 아직 시간이 도달하지 않았다면 nav와 wait subtask 생성하기.
    total_time = 0
    schedule_subtask_and_time = {}
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
                        # nav 시간 구하기. schedule_subtask_and_time에 nav_{result_schedule[i]} 넣기
                        nav_time = specific_nav_time(subtask.execution.primitive_actions[0], nav_graph)
                        schedule_subtask_and_time.update({f"nav_{result_schedule[i]}": nav_time})
                        # interval-nav시간 만큼 schedule_subtask_and_time에 wait_{result_schedule[i]} 넣기
                        wait_time = obj.interval - nav_time
                        schedule_subtask_and_time.update({f"wait_{result_schedule[i]}": wait_time})
                        # 전체 시간 update
                        total_time += (nav_time + wait_time)
 
        # subtask 
        subtask_total_time, held_object = subtask_time(subtask, held_object, nav_graph)
        total_time += subtask_total_time
        schedule_subtask_and_time.update({subtask.name : subtask_total_time})

    return total_time, schedule_subtask_and_time




if __name__ == "__main__":
    main()