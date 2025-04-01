
import argparse
import heapq
from typing import List, Optional
import networkx as nx
import heapq
import time
from pathlib import Path
from simulation.runner_ai2thor import execute_subtask

from utils.io_utils.result_saver import result_save

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
)  # 프로젝트 루트 경로
ASSETS_PATH = PROJECT_ROOT / Path("assets")  # assets 폴더 경로
from ithor.utils.math_utils import build_navigation_graph
from simulation.runner_ai2thor import init_ai2thor_controller
from utils.config.constants import RESULT_PATH, SCENE_NAME
from scheduler.action_handler import ActionHandler
from dataclass import SimulationNode, SchedulerState, CompletedEntry
from core.task import *

from utils.io_utils.task_io import (
    load_scene_positions,
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_task_data_from_file,
)

from utils.task.task_util import TaskUtil
from utils.visualizers.gantt import plot_completed_subtasks_gantt

# def get_current_timeslot(current_state: SchedulerState) -> Optional[str]:
#     """
#     complete_subtasks에 있는 노드 중, digraph 상에서 나가는 edge가 있고 들어오는 edge가 없다면
#     timeslot이 시작된 것으로 판단한다.
#     반환값: "critical", "non-critical", 또는 None (timeslot 없음)
#     """
#     constraints = current_state.constraints
#     for entry in current_state.completed_subtasks:
#         node = entry.subtask.name
#         if node in constraints:  # 노드 존재 여부 확인
#             if constraints.out_degree(node) > 0 and constraints.in_degree(node) == 0:
#                 # 나가는 edge 중 critical한 edge가 있으면 critical timeslot
#                 for _, target, data in constraints.out_edges(node, data=True):
#                     if data.get("info", {}).get("IsCritical", False):

#                         return "critical"
#                 return "non-critical"
#     return None

# def get_current_timeslot(current_state: SchedulerState) -> Optional[str]:
#     """
#     complete_subtasks에 있는 노드 중, digraph 상에서 나가는 edge가 있고 들어오는 edge가 없다면
#     timeslot이 시작된 것으로 판단한다.
#     반환값: "critical", "non-critical", 또는 None (timeslot 없음)
#     """
#     constraints = current_state.constraints
#     completed_names = {entry.subtask.name for entry in current_state.completed_subtasks}
#     pending_edges = []
#     # 한쪽 노드만 completed_names 에 있는 edge 가 있는 경우. 
#     for u, v, data in constraints.edges(data=True):
#         # XOR 연산: 정확히 한쪽만 완료되었을 경우
#         if (u in completed_names) ^ (v in completed_names):
#             pending_edges.append((u, v, data))
    
#     if pending_edges:
#         # 한 노드와만 연결된 edge 가 critical 이면
#         for _,_,data in pending_edges:
#             if data.get("info", {}).get("IsCritical", False):
#                 return "critical"
#         #한 노드와만 연결된 edge 가 있는데 critical은 없으면
#         return "non-critical"
            
#     return None

def is_executable(subtask: Subtask, current_state: SchedulerState):
    """
    subtask가 dependency 때문에 실행 가능한지 여부 반환
    """
    constraints = current_state.constraints
    if constraints.in_edges(subtask.name):  # dependency가 있는 경우
        if list(constraints.in_edges(subtask.name))[0][0] in [
            finish_subtask.subtask.name
            for finish_subtask in current_state.completed_subtasks
        ]:
            # 앞 subtask 가 completed_subtasks에 있어야 실행 가능
            return True
        else:
            return False
    # dependency가 없는 경우면 그냥 실행 가능
    return True

def get_pending_edges(current_state: SchedulerState) -> list:
    """
    complete_subtasks에 있는 노드 중, digraph 상에서 나가는 edge가 있고 들어오는 edge가 없다면
    timeslot이 시작된 것으로 판단한다.
    반환값: "critical", "non-critical", 또는 None (timeslot 없음)
    """
    constraints = current_state.constraints
    completed_names = {entry.subtask.name for entry in current_state.completed_subtasks}
    pending_edges = []
    # 한쪽 노드만 completed_names 에 있는 edge 가 있는 경우. 
    for u, v, data in constraints.edges(data=True):
        # XOR 연산: 정확히 한쪽만 완료되었을 경우
        if (u in completed_names) ^ (v in completed_names):
            pending_edges.append((u, v, data))
    
    return pending_edges

def get_timeslot_type(pending_edges):
    if pending_edges:
        # pending edge들 중 하나라도 critical이면 "critical"을 반환
        for _, _, data in pending_edges:
            if data.get("info", {}).get("IsCritical", False):
                return "critical"
        # pending edge가 존재하지만 모두 non-critical인 경우
        return "non-critical"
    return None

def simulate_following_nav_time(edges, subtask, current_state, action_handler, current_time):
    """
    edges: (u, v, edge_data)의 list
    subtask : 현재 subtask, 아마 필요 없는데 지식 부족으로 일단 삽입. 
    current_state: SchedulerState
    action_handler: ActionHandler 인스턴스
    current_time: 현재 시간
    현재 subtask에서 
    후행 노드로 이동하는데 걸리는 내비게이션 시간을 반환한다.
    """
    # edge에서 timeslot 유발 노드와 후행 노드를 구분
    nav_infos= []
    for edge in edges:
        u, v, _ = edge
        completed_names = {entry.subtask.name for entry in current_state.completed_subtasks}

        if u in completed_names:
            following_node = v  # u: 완료된 노드, v: 후행 노드
        else:
            following_node = u
        
        # 후행 노드로 이동하는 내비게이션 동작을 시뮬레이션.
        # simulation_subtask가 필요하면, 해당 context에 맞는 subtask를 전달해야 하겠지만,
        # 여기서는 간단하게 None으로 처리하거나 적절한 subtask를 전달할 수 있다.

        target_subtask = next((st for st in current_state.remaining_subtasks if st.name == following_node), None)
        if target_subtask is None:
            continue 

        actions = target_subtask.execution.primitive_actions or []
        if not actions:
            raise("subtask not has primitive action")
        first_action = actions[0]

        temp_node = SimulationNode(
            deadline=current_time,
            simulation_subtask=subtask,  
            state=current_state
        )

        nav_infos.append(action_handler.get_actions_info(temp_node, [first_action]))
    nav_info = min(nav_infos)

    return nav_info.time_used if nav_info else 0


def simulation_edf(current_state: SchedulerState, nav_graph) -> Optional[Subtask]:
    """
    함수 이름은 simulation 이지만 schedueling을 하는 함수다.
    각 실행 가능한 subtask에 대해 deadline을 산출한 후, deadline이 가장 짧은 subtask를 선택한다.

    [계산 방법]
    - complete_subtasks에서, digraph의 node 중 나가는 edge만 있고 들어오는 edge가 없다면 timeslot이 시작된 것으로 본다.

    1. **timeslot이 시작되지 않은 경우.**
        a. 모든 subtask의 deadline = current_time + execution_time + 그 subtask의 첫 nav_time
    2. **현재 critical timeslot인 경우**
        a. **현재 subtask가 critical in edge가 존재하는 후행 subtask 면**
            deadline = 현재 subtask의 선행 subtask의 end_time + edge의 constraint의 interval - 현재 subtask의 첫 nav_time
        b. **subtask 가 non_critical in edge 가 존재하는 후행 subtask면**
            deadline = critical timeslot을 유발한 subtask의 end_time + 유발 subtask의 constraint의 interval + 유발 subtask의 후행 subtask의 execution_time - 후행 subtask의 첫 nav_time
        c. **나머지 subtask의 경우**
            deadline = current_time + execution_time + 후행 subtask까지의 nav_time + 그 subtask의 첫 nav_time
    3. 현재 non-critical time slot인 경우.
        a. 현재 subtask가 non_critical in edge 가 존재하는 후행 subtask면
            deadline = 현재 subtask의 선행 subtask의 end_time + edge의 constraint의 interval - 현재 subtask의 첫 nav_time
        b. 나머지 subtask의 경우
            deadline = current_time + execution_time + 후행 subtask까지의 nav_time + 그 subtask의 첫 nav_time
    """
    action_handler = ActionHandler(nav_graph)
    current_time = current_state.current_time
    constraints = current_state.constraints
    # timeslot 존재 여부: get_current_timeslot는 "critical", "non-critical", 또는 None을 반환
    
    #현재 시점에 한 노드만 완료된 엣지들의 리스트.
    pending_edges = get_pending_edges(current_state)
    # 그 리스트중 critical type이 있는지 확인
    timeslot_type = get_timeslot_type(pending_edges)

    queue = []
    

    for subtask in current_state.remaining_subtasks:
        if not is_executable(subtask, current_state):
            continue

        # 시뮬레이션으로 subtask의 실행 시간(execution_time) 산출
        temp_node = SimulationNode(
            deadline=current_time, 
            simulation_subtask=subtask, 
            state=current_state
        )
        actions = subtask.execution.primitive_actions or []
        exec_info = (
            action_handler.get_actions_info(temp_node, actions) if actions else None
        )
        execution_time = exec_info.time_used if exec_info else 0

        # 자신의 nav_time: subtask 내 첫번째 NAVIGATE_TO 동작의 시뮬레이션 결과 사용 (없으면 0)
        nav_time = 0
        for act in actions:
            if act.startswith("NAVIGATE_TO"):
                nav_info = action_handler.get_actions_info(temp_node, [act])
                if nav_info:
                    nav_time = nav_info.time_used
                break
        

        # 기본 deadline (rule 1)
        deadline = current_time + execution_time + nav_time

        # dependency 여부: subtask에 들어오는 edge가 있으면 후행 subtask로 판단. 
        incoming_edges = list(constraints.in_edges(subtask.name, data=True))  

        if timeslot_type is None:
            # 1: timeslot이 없는 경우
            deadline = current_time + execution_time       

        elif timeslot_type == "critical":
            # 2: timeslot 이 critical 인 경우

            # 현재 subtask 의 critical in edge를 담은 list
            critical_edges = [
                (u, v, edge_data)
                for u, v, edge_data in incoming_edges
                if edge_data.get("info", {}).get("IsCritical", False)
            ]

            
            
            if critical_edges:
                # 2-a 현재 subtask가 critical in edge가 존재하는 후행 subtask 인 경우

                # 한 subtask가 가진 critical in edge 들의 deadline들 
                critical_deadlines = [
                    (
                        # predecessor의 end_time (없으면 current_time 사용)
                        next(
                            (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                            current_state.current_time
                        )
                        + edge_data["info"]["Interval"]                        
                    )
                    for u, v, edge_data in critical_edges
                ]

                # 이 subtask가 실행되어야하면 wait 여부를 확인해야한다.     
                # ciritical_deadlines 에서 가장 급한걸 deadline으로 설정.                   
                deadline = min(critical_deadlines) + nav_time

            
            elif incoming_edges:
                # 2-b 현재 subtask 가 non_critical in edge 가 존재하는 후행 subtask 인 경우
                
                #현재 상태를 유발한 edge 들을 순회해서 그 edge의 후행 subtask 시작 시간보다 뒤로 deadline 을 준다. 

                candidate_nav_times =  simulate_following_nav_time(
                    critical_edges, subtask, current_state, action_handler, current_time
                    )                
                # 후행 subtask중 가장 급한것 까지의 nav_time 
                following_nav = (
                    min(candidate_nav_times) if candidate_nav_times else 0
                )

                non_critical_deadlines = [
                    (
                        # predecessor의 end_time (없으면 current_time 사용)
                        next(
                            (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u)                        ,
                            current_state.current_time
                        )
                        # 후행 subtask의 execution time
                        + next( 
                            (entry.end_time - entry.start_time for entry in current_state.completed_subtasks 
                            if entry.subtask.name == v), 0
                            )
                        + edge_data["info"]["Interval"] #그 edge 의 interval
                        - following_nav 
                        
                    )
                    for u, v, edge_data in pending_edges
                    if edge_data.get("info", {}).get("IsCritical", False)
                ]
                # deadline = critical timeslot을 유발한 subtask의 end_time +  유발 subtask의 후행 subtask의 execution_time + 유발 subtask의 constraint의 interval - 후행 subtask의 첫 nav_time
                deadline = min(non_critical_deadlines)
            else:
                # 2-c in_edge가 없는 subtask인 경우

                # 현상황에서 constraint의 후행 subtask로 이동하는데 걸리는 시간들
                critical_pending_edges = [
                    (u, v, edge_data)
                    for u, v, edge_data in pending_edges
                    if edge_data.get("info", {}).get("IsCritical", False)
                ]

                candidate_nav_times = [
                    simulate_following_nav_time(critical_pending_edges, subtask, current_state, action_handler, current_time)
                    
                ]

                # 후행 subtask까지의 nav_time 
                following_nav = (
                    min(candidate_nav_times) if candidate_nav_times else 0
                )
                
                deadline = current_time + execution_time + following_nav + nav_time

        elif timeslot_type == "non-critical":
            if incoming_edges:
                # rule 3-a: 후행 subtask인 경우   
                non_critical_deadlines = [
                    (
                        # predecessor의 end_time (없으면 current_time 사용)
                        next(
                            (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                            current_state.current_time
                        )
                        + edge_data["info"]["Interval"]                
                    )
                    for u, v, edge_data in incoming_edges
                ] 
                 
                # deadline = 현재 subtask의 선행 subtask의 end_time + edge의 constraint의 interval - 현재 subtask의 첫 nav_time             
                deadline = min(non_critical_deadlines)+ nav_time
            else:
                # rule 3-b: edge 가 없는 subtask 인 경우
                deadline = current_time + execution_time + nav_time

        sim_node = SimulationNode(
            deadline=deadline,
            simulation_subtask=subtask,
            state=current_state,
        )
        heapq.heappush(queue, sim_node)

    if queue:
        chosen_node = heapq.heappop(queue)
        return chosen_node.simulation_subtask
    else:
        return None


def update(
    current_state: SchedulerState, next_subtask: Subtask, nav_graph
) -> SchedulerState:
    """
    1) next_subtask 실행 시간 시뮬레이션 후 subtask.duration.interval 에 반영
    2) After 제약(interval=X)이 있으면, designated_start = predecessor.end_time + X
       - current_time < designated_start => NAVIGATE_TO + WAIT subtask를 CompletedEntry로 추가
    3) next_subtask 실행 CompletedEntry 추가
    """

    action_handler = ActionHandler(nav_graph)

    # -------------------------------
    # 1) 실제 실행 시간 시뮬레이션
    # -------------------------------
    current_time = current_state.current_time
    temp_node = SimulationNode(
        deadline=current_time,
        simulation_subtask=next_subtask,
        state=current_state,
    )
    sim_log = action_handler._simulate_actions(
        temp_node, next_subtask.execution.primitive_actions or []
    )
    if sim_log and sim_log.results:
        last_result = sim_log.results[-1]
        real_exec_time = last_result.time_used  # 시뮬레이션이 0초부터 시작했다고 가정
    else:
        # primitive_actions가 없거나 시뮬레이션 실패 시 fallback
        real_exec_time = next_subtask.duration.interval

    # subtask의 duration.interval을 실제 실행 시간으로 업데이트
    next_subtask.duration.interval = real_exec_time

    # -------------------------------
    # 2) After 제약(interval=X) 처리
    # -------------------------------
    constraints = current_state.constraints
    incoming_edges = list(constraints.in_edges(next_subtask.name, data=True))
    designated_start = current_time  # 기본적으로는 지금 바로 시작

    # After 제약(edge info.Type=="After", info.Interval=X) 찾기
    # (하나만 있다고 가정. 여러 개면 추가 로직 필요)
    after_edge = None
    for edge in incoming_edges:
        # edge: (pred_node, next_subtask.name, data)
        info = edge[2].get("info", {})
        if info.get("Type") == "After":
            after_edge = edge
            break

    wait_entries = []
    if after_edge:
        pred_name = after_edge[0]
        interval_x = after_edge[2]["info"]["Interval"]
        # 선행 subtask의 완료시각 찾기
        predecessor_entry = next(
            (
                entry
                for entry in current_state.completed_subtasks
                if entry.subtask.name == pred_name
            ),
            None,
        )
        pred_end = predecessor_entry.end_time if predecessor_entry else current_time
        designated_start = pred_end + interval_x

    new_current_time = current_time

    # 만약 current_time < designated_start 라면 => 대기 필요
    if new_current_time < designated_start:
        # (a) NAVIGATE_TO subtask를 따로 표시하기 원한다면
        #     next_subtask의 첫 번째 NAVIGATE_TO를 추출해서 CompletedEntry로 만든다
        nav_action = None
        for act in next_subtask.execution.primitive_actions or []:
            if act.startswith("NAVIGATE_TO"):
                nav_action = act
                break

        if nav_action:
            # NAVIGATE_TO에 걸리는 시간 계산
            nav_sim_log = action_handler._simulate_actions(temp_node, [nav_action])
            if nav_sim_log and nav_sim_log.results:
                nav_time = nav_sim_log.results[-1].time_used
            else:
                nav_time = 1  # fallback
            # NAVIGATE_TO CompletedEntry
            nav_entry = CompletedEntry(
                subtask=Subtask(
                    task_name=next_subtask.task_name,
                    name=f"NAVIGATE_TO_{nav_action.split()[1]}",
                    repetition=1,
                    type="NAVIGATE",
                    execution=Execution(objects={}, primitive_actions=[nav_action]),
                    duration=Duration(type="NAVIGATE", interval=nav_time),
                    temporal_constraints=[],
                ),

                start_time=new_current_time,
                end_time=new_current_time + nav_time,
            )
            nav_entry.subtask.execution_status = True
            wait_entries.append(nav_entry)
            new_current_time += nav_time

        # (b) 남은 시간(= designated_start - new_current_time) 만큼 WAIT
        remaining_wait = designated_start - new_current_time
        if remaining_wait > 0:
            wait_entry = CompletedEntry(
                subtask=Subtask(
                    task_name=next_subtask.task_name,
                    name=f"WAIT_for_{next_subtask.name}",
                    repetition=1,
                    type="WAIT",
                    execution=Execution(
                        objects={}, primitive_actions=[f"WAIT {remaining_wait}"]
                    ),
                    duration=Duration(type="WAIT", interval=remaining_wait),
                    temporal_constraints=[],
                ),
                start_time=new_current_time,
                end_time=designated_start,
            )
            wait_entry.subtask.execution_status = True
            wait_entries.append(wait_entry)
            new_current_time = designated_start

    # -------------------------------
    # 3) next_subtask 실행
    # -------------------------------
    subtask_entry = CompletedEntry(
        subtask=next_subtask,
        start_time=new_current_time,
        end_time=new_current_time + real_exec_time,
    )
    new_current_time += real_exec_time

    # -------------------------------
    # 완료 목록 및 state 갱신
    # -------------------------------
    new_completed = current_state.completed_subtasks + wait_entries + [subtask_entry]
    new_remaining = [
        st for st in current_state.remaining_subtasks if st.name != next_subtask.name
    ]

    updated_state = SchedulerState(
        subtask=next_subtask,
        completed_subtasks=new_completed,
        remaining_subtasks=new_remaining,
        constraints=constraints,
        current_time=new_current_time,
        scene_positions=current_state.scene_positions,  # scene_positions도 필요시 갱신
        held_object=current_state.held_object,
        agent_location=current_state.agent_location,
    )
    return updated_state


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Task Scheduler")

    # 현재 미사용중인 argument들은 주석처리되었다.
    # parser.add_argument(
    #     "-d",
    #     "--decomposition",
    #     help="Enable or disable decomposition",
    #     default=True,
    #     action="store_true",
    # )
    # parser.add_argument(
    #     "-v",
    #     "--visualize",
    #     help="Enable visualization of the task plan",
    #     default=True,
    #     action="store_true",
    # )
    # parser.add_argument(
    #     "-r",
    #     "--reset",
    #     default=True,
    #     help="Reset the knowledge base to Gaussian",
    #     action="store_true",
    # )
    parser.add_argument(
        "-s",
        "--simulation",
        default=True,
        action="store_true",
    )
    return parser.parse_args()


def main():

    # Set up the AI2-THOR controller and navigation graph
    approach_name = "dag_edf"
    args = parse_arguments()
    controller = init_ai2thor_controller()
    nav_graph = build_navigation_graph(controller)
    scene_name = SCENE_NAME
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name , choice= get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = (
        get_natural_language_from_task_file(f"{choice}")
        if choice is not None
        else Path(task_file_name).stem
    )

    # Build tasks and constraints

    subtasks, constraints = TaskUtil.build_tasks_and_constraints(task_data, True)

    computation_time = 0
    current_state = TaskUtil.get_init_state(subtasks, constraints, scene_poses)
    result_schedule = []
    simulation_subtask_times = []
    for _ in range(len(subtasks)):
        # next_subtask는 Subtask 객체이다.

        subtask_scheduling_time_start = time.time()
        next_subtask = simulation_edf(current_state, nav_graph)

        if next_subtask is None:
            break
        current_state = update(current_state, next_subtask, nav_graph)
        subtask_scheduling_time = time.time() - subtask_scheduling_time_start

        computation_time += subtask_scheduling_time

        # 현재 시뮬레이션 실행시 schedule된 wait이나 navigate subtask는 단독으로 실행되지 않는다.
        if args.simulation:
            # 터미널에서 src/baselines/def/dag_edf.py -s 실행시 사용됨

            subtask_time, execution_status = execute_subtask(controller, next_subtask)
            simulation_subtask_times.append(subtask_time)
            next_subtask.execution_status = execution_status

    result_schedule = current_state.completed_subtasks
    result_schedule.pop(0)
    # completed_Entry 객체를 Subtask객체로 변환.
    # start_time과 end_time을 추출해서 Subtask 객체 안에 저장.

    output_path = RESULT_PATH / input_natural_language / "metadata"
    output_path.mkdir(parents=True, exist_ok=True)
    gantt_path = output_path/"edf_gantt"

    plot_completed_subtasks_gantt(result_schedule, gantt_path)



    if args.simulation:
        approach_name = f"{approach_name}_simulation"
        i = 0
        current_time = 0

        for ce in result_schedule:
            ce.subtask.start_time_scheduled = ce.start_time
            ce.subtask.end_time_scheduled = ce.end_time

            ce.subtask.start_time_simulation = current_time
            # Wait 과 Navigate는 실제 시뮬레이션
            if ce.subtask.type == "WAIT" or ce.subtask.type == "NAVIGATE":
                ce.subtask.end_time_simulation = (
                    current_time + ce.subtask.duration.interval
                )
                current_time += ce.subtask.duration.interval
            else:
                ce.subtask.end_time_simulation = (
                    current_time + simulation_subtask_times[i]
                )
                current_time += simulation_subtask_times[i]
                i += 1



        result_args = {
            "task_name": input_natural_language,
            "approach_name": approach_name,
            "result_schedule": result_schedule,
            "computation_time": computation_time,
            "scene_name": scene_name,
            # "simulationTime": None,
        }

        result_save(**result_args)


if __name__ == "__main__":
    main()
