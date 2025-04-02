
import argparse
import heapq
from typing import List, Optional
import networkx as nx
import heapq
import time
from pathlib import Path
from simulation.runner_ai2thor import execute_subtask

from utils.io_utils.result_saver import result_save
import os

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

# 임시로 사용할 함수
def get_available_filename(filepath: str) -> str:
    """
    주어진 filepath가 이미 존재하면, 뒤에 (1), (2), ... 등의 첨자를 붙여서 사용 가능한 파일명을 반환합니다.
    """
    base, ext = os.path.splitext(filepath)
    counter = 1
    new_filepath = filepath
    while os.path.exists(new_filepath):
        new_filepath = f"{base} ({counter}){ext}"
        counter += 1
    return new_filepath
##


def is_executable(subtask: Subtask, current_state: SchedulerState) -> bool:
    """
    subtask가 dependency 때문에 실행 가능한지 여부 반환
    """
    constraints = current_state.constraints
    incoming = list(constraints.in_edges(subtask.name))
    if incoming:  # dependency가 있는 경우
        # 단순히 첫번째 dependency가 완료되었는지 여부로 판단
        pred_name = incoming[0][0]
        completed = {entry.subtask.name for entry in current_state.completed_subtasks}
        return pred_name in completed
    return True  # dependency가 없으면 실행 가능


def get_pending_edges(current_state: SchedulerState) -> list:
    """
    complete_subtasks에 있는 노드 중, digraph 상에서 한쪽만 완료된 edge를
    timeslot이 시작된 것으로 판단하여 pending edge 리스트를 반환한다.
    """
    constraints = current_state.constraints
    completed_names = {entry.subtask.name for entry in current_state.completed_subtasks}
    pending_edges = []
    for u, v, data in constraints.edges(data=True):
        # XOR 연산: 정확히 한쪽만 완료된 경우
        if (u in completed_names) ^ (v in completed_names):
            pending_edges.append((u, v, data))
    return pending_edges


def get_timeslot_type(pending_edges: list) -> Optional[str]:
    """
    pending_edges 중 하나라도 critical이면 "critical", 그렇지 않으면 "non-critical",
    pending_edges가 없으면 None을 반환한다.
    """
    if pending_edges:
        for _, _, data in pending_edges:
            if data.get("info", {}).get("IsCritical", False):
                # 문자열 말고 다른거로 하자 bool 같은거로 
                return "critical"
        return "non-critical"
    return None


def compute_execution_time(subtask: Subtask, current_time: float, current_state: SchedulerState, action_handler) -> float:
    """
    현재 subtask의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(deadline=current_time, simulation_subtask=subtask, state=current_state)
    actions = subtask.execution.primitive_actions or []
    exec_info = action_handler.get_actions_info(temp_node, actions) if actions else None
    return exec_info.time_used if exec_info else 0


def compute_nav_time(subtask: Subtask, current_time: float, current_state: SchedulerState, action_handler) -> float:
    """
    subtask 내 첫 번째 NAVIGATE_TO primitive action의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(deadline=current_time, simulation_subtask=subtask, state=current_state)
    nav_time = 0
    for act in subtask.execution.primitive_actions or []:
        if act.startswith("NAVIGATE_TO"):
            nav_info = action_handler.get_actions_info(temp_node, [act])
            if nav_info:
                nav_time = nav_info.time_used
            break
    return nav_time


def simulate_following_nav_time(edges: list, subtask: Subtask, current_state: SchedulerState,
                                action_handler, current_time: float) -> float:
    """
    edges: (u, v, edge_data) 리스트
    constraint 유발 edge의 후행 노드의 첫 primitive action을 사용해, 해당 노드로 이동하는 내비게이션 시간을 시뮬레이션한다.
    여러 edge 중 첫 유효 결과를 반환하며, 없으면 0을 반환한다.
    """
    for edge in edges:
        u, v, _ = edge
        completed_names = {entry.subtask.name for entry in current_state.completed_subtasks}
        following_node = v if u in completed_names else u

        # following_node에 해당하는 subtask를 remaining_subtasks에서 찾음
        target_subtask = next((st for st in current_state.remaining_subtasks if st.name == following_node), None)
        if target_subtask is None:
            continue

        actions = target_subtask.execution.primitive_actions or []
        if not actions:
            continue
        first_action = actions[0]

        temp_node = SimulationNode(deadline=current_time, simulation_subtask=subtask, state=current_state)
        nav_info = action_handler.get_actions_info(temp_node, [first_action])
        if nav_info:
            return nav_info.time_used
    return 0


def compute_deadline_for_subtask(subtask: Subtask, current_state: SchedulerState, constraints,
                                 timeslot_type: Optional[str], execution_time: float, nav_time: float,
                                 pending_edges: list, action_handler, current_time: float) -> float:
    """
    subtask에 대한 deadline을 timeslot 유형과 dependency 조건에 따라 계산한다.
    
    [규칙]
        1. timeslot이 없는 경우: 실행대신 이동시간을 고려하게 하면
           deadline = current_time + nav_time 
        2. critical timeslot:
            a. subtask가 critical in edge가 있다면: -> navtime 빼지 말자. 
                deadline = (선행 subtask의 end_time + edge interval) 
            b. subtask가 non critical in edge만 있으면: -> 실행시간 제외하자
                deadline = 현재 subtask의 edge의 선행 subtask의 end_time + edge의 interval                     
            c. 그 외:
                deadline = current_time + nav_time

                
        3. non-critical timeslot:
            a. 현재 subtask 가 noncritical의 후행 subtask 인 경우:
                deadline = (선행 subtask의 end_time + edge interval) 
            b. 그 외:
                deadline = current_time + nav_time
    """
    # 현재 subtask가 가진 edge들의 list
    incoming_edges = list(constraints.in_edges(subtask.name, data=True))
    if timeslot_type is None:
        # 규칙 1
        return current_time + execution_time

    elif timeslot_type == "critical":
        # critical in edge가 존재하는 경우
        critical_edges = [
            (u, v, data)
            for u, v, data in incoming_edges
            if data.get("info", {}).get("IsCritical", False)
        ]
        
        if critical_edges:
            #규칙 2-a
            critical_deadlines = [
                next(
                    (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                    current_time
                ) + data["info"]["Interval"]
                for u, v, data in critical_edges
            ]
            return min(critical_deadlines) - nav_time

        
        elif incoming_edges:
            # 규칙 2-b
            for u, v, data in incoming_edges:
                # current_state.completed_subtasks에서 u에 해당하는 predecessor의 end_time
                predecessor_endtime = next(
                    (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                    None  # 없으면 None 또는 기본값을 사용합니다.
                )
                
                interval = data.get("info", {}).get("Interval", None)   
                # 가장 나중에 끝나야 하는 경우를 기준으로 deadline을 연산한다. 
                if predecessor_endtime is not None:
                    current_deadline = predecessor_endtime + interval
                    if (max_deadline is None) or (current_deadline > max_deadline):
                        max_deadline = current_deadline
            if max_deadline is None:
                max_deadline = 0

            return max_deadline+ execution_time
        
        else:
            # in_edge가 없는 경우: 후행 subtask까지의 내비게이션 시간 포함
            following_nav = simulate_following_nav_time(pending_edges, subtask, current_state, action_handler, current_time)
            return current_time + execution_time + following_nav

    elif timeslot_type == "non-critical":
        if incoming_edges:
            #규칙 3-a
            non_critical_deadlines = [
                next(
                    (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                    current_time
                ) + data["info"]["Interval"]
                for u, v, data in incoming_edges
            ]
            return min(non_critical_deadlines) 
        else:
            #규칙 3-b
            return current_time + execution_time

    # 기본 fallback
    return current_time + execution_time


def simulation_edf(current_state: SchedulerState, nav_graph) -> Optional[Subtask]:
    """
    각 실행 가능한 subtask에 대해 deadline을 산출한 후, deadline이 가장 짧은 subtask를 선택한다.
    
    """
    import heapq

    action_handler = ActionHandler(nav_graph)
    current_time = current_state.current_time
    constraints = current_state.constraints


    pending_edges = get_pending_edges(current_state)
    timeslot_type = get_timeslot_type(pending_edges)

    queue = []
    for subtask in current_state.remaining_subtasks:
        if not is_executable(subtask, current_state):
            continue

        execution_time = compute_execution_time(subtask, current_time, current_state, action_handler)
        nav_time = compute_nav_time(subtask, current_time, current_state, action_handler)

        deadline = compute_deadline_for_subtask(
            subtask, current_state, constraints, timeslot_type,
            execution_time, nav_time, pending_edges, action_handler, current_time
        )

        sim_node = SimulationNode(deadline=deadline, simulation_subtask=subtask, state=current_state)
        heapq.heappush(queue, sim_node)

    if queue:
        chosen_node = heapq.heappop(queue)
        return chosen_node.simulation_subtask
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
