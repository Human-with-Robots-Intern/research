import argparse
import heapq
import json
from typing import List, Optional, Tuple
import networkx as nx
import matplotlib.pyplot as plt
import os
import copy
import heapq
import time

from pathlib import Path

from sim.runner_ai2thor import execute_subtask
from utils.io_utils.result_saver import result_save

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # 프로젝트 루트 경로
ASSETS_PATH = PROJECT_ROOT / Path("assets")  # assets 폴더 경로



from ithor.utils.math_utils import build_navigation_graph

from sim.runner_ai2thor import init_ai2thor
from utils.task import load_scene_positions
from utils.constants import SCENE_NAME


from scheduler.action_handler import ActionHandler
from utils.task.task_util import build_tasks_and_constraints
from utils.viz.make_gantt import gantt_chart
from scheduler.dataclass import CompletedEntry, SchedulerState
from utils.dataclass import SimulationNode
from core.task import Subtask, Execution, Duration
from utils.io_utils.task_io import get_natural_language_from_task_file, list_task_files, get_user_task_choice, load_task_data_from_file


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
    # dependency가 없는 경으면 그냥 실행 가능
    return True


def get_current_timeslot(current_state: SchedulerState) -> Optional[str]:
    """
    complete_subtasks에 있는 노드 중, digraph 상에서 나가는 edge가 있고 들어오는 edge가 없다면
    timeslot이 시작된 것으로 판단한다.
    반환값: "critical", "non-critical", 또는 None (timeslot 없음)
    """
    constraints = current_state.constraints
    for entry in current_state.completed_subtasks:
        node = entry.subtask.name
        if node in constraints:  # 노드 존재 여부 확인
            if constraints.out_degree(node) > 0 and constraints.in_degree(node) == 0:
                # 나가는 edge 중 critical한 edge가 있으면 critical timeslot
                for _, target, data in constraints.out_edges(node, data=True):
                    if data.get("info", {}).get("IsCritical", False):
                        return "critical"
                return "non-critical"
    return None


def simulation_edf(current_state: SchedulerState, nav_graph) -> Optional[Subtask]:
    """
    함수 이름은 simulation 이지만 schedueling을 하는 함수다.
    각 실행 가능한 subtask에 대해 deadline을 산출한 후, deadline이 가장 짧은 subtask를 선택한다.

    [계산 방법]
    - complete_subtasks에서, digraph의 node 중 나가는 edge만 있고 들어오는 edge가 없다면 timeslot이 시작된 것으로 본다.

    1. critical한 timeslot이 시작된 경우:
       1-a. 만약 subtask가 dependency(들어오는 edge가 있음)를 가진 후행 subtask라면,
           designated_start = (선행 subtask의 end_time + constraint의 interval)
           candidate1 = designated_start - (자신의 nav_time)
           deadline = candidate1
       1-b. dependency가 없는 경우,
           deadline = current_time + execution_time + (후행 subtask까지의 nav_time)
           → 후행 subtask의 nav_time은, complete_subtasks 중 timeslot을 시작한 노드(즉, out_degree > 0, in_degree == 0)의 outgoing critical edge에 연결된 target subtask의 nav_time(시뮬레이션)으로 산출
    2. non-critical한 timeslot이 시작된 경우:
       2-a. 후행 subtask인 경우 (dependency 있음)
           designated_start = (선행 subtask의 end_time + constraint의 interval)
           candidate1 = designated_start - (자신의 nav_time)
           candidate2 = current_time + execution_time + (자신의 nav_time)
           ! 근데 생각해보니깐 여기서는 nav_time을 생각 안해도 될 것 같음
           deadline = max(candidate1, candidate2)
       2-b. 그렇지 않은 경우
           deadline = current_time + execution_time
    3. timeslot이 없는 경우:
         deadline = current_time + execution_time
    """
    action_handler = ActionHandler(nav_graph)
    current_time = current_state.current_time
    constraints = current_state.constraints
    # timeslot 존재 여부: get_current_timeslot는 "critical", "non-critical", 또는 None을 반환
    timeslot_type = get_current_timeslot(current_state)
    queue = []

    for subtask in current_state.remaining_subtasks:
        if not is_executable(subtask, current_state):
            continue

        # 시뮬레이션으로 subtask의 실행 시간(execution_time) 산출
        temp_node = SimulationNode(
            deadline=current_time, simulation_subtask=subtask, state=current_state
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

        # 기본 deadline (rule 3)
        deadline = current_time + execution_time

        # dependency 여부: subtask가 들어오는 edge가 있으면 후행 subtask로 판단
        incoming_edges = list(constraints.in_edges(subtask.name, data=True))
        has_dependency = len(incoming_edges) > 0

        if timeslot_type is None:
            # rule 3: timeslot이 없으면 deadline = current_time + execution_time
            deadline = current_time + execution_time
        else:
            if timeslot_type == "critical":
                if has_dependency:
                    # rule 1-a: 후행 subtask인 경우
                    crit_edge = next(
                        (
                            edge
                            for edge in incoming_edges
                            if edge[2].get("info", {}).get("IsCritical", False)
                        ),
                        None,
                    )
                    if crit_edge:
                        pred_name = crit_edge[0]
                        interval = crit_edge[2]["info"]["Interval"]
                        predecessor_entry = next(
                            (
                                entry
                                for entry in current_state.completed_subtasks
                                if entry.subtask.name == pred_name
                            ),
                            None,
                        )
                        designated_start = (
                            predecessor_entry.end_time
                            if predecessor_entry
                            else current_time
                        ) + interval
                        candidate1 = designated_start - nav_time
                        deadline = candidate1
                    else:
                        # 만약 critical edge가 없으면 후행 subtask가 아니므로 rule 1-b 적용
                        candidate_nav_times = []
                        for entry in current_state.completed_subtasks:
                            node = entry.subtask.name
                            # timeslot을 시작한 노드: 나가는 edge만 있고 들어오는 edge가 없음
                            if (
                                node in constraints
                                and constraints.out_degree(node) > 0
                                and constraints.in_degree(node) == 0
                            ):
                                for _, target, data in constraints.out_edges(
                                    node, data=True
                                ):
                                    if data.get("info", {}).get("IsCritical", False):
                                        if any(
                                            st.name == target
                                            for st in current_state.remaining_subtasks
                                        ):
                                            temp_target = SimulationNode(
                                                deadline=current_time,
                                                simulation_subtask=subtask,
                                                state=current_state,
                                            )
                                            nav_info = action_handler.get_actions_info(
                                                temp_target, [f"NAVIGATE_TO {target}"]
                                            )
                                            if nav_info:
                                                candidate_nav_times.append(
                                                    nav_info.time_used
                                                )
                        following_nav = (
                            min(candidate_nav_times) if candidate_nav_times else 0
                        )
                        deadline = current_time + execution_time + following_nav
                else:
                    # rule 1-b: dependency가 없는 경우
                    candidate_nav_times = []
                    for entry in current_state.completed_subtasks:
                        node = entry.subtask.name
                        if (
                            node in constraints
                            and constraints.out_degree(node) > 0
                            and constraints.in_degree(node) == 0
                        ):
                            for _, target, data in constraints.out_edges(
                                node, data=True
                            ):
                                if data.get("info", {}).get("IsCritical", False):
                                    if any(
                                        st.name == target
                                        for st in current_state.remaining_subtasks
                                    ):
                                        temp_target = SimulationNode(
                                            deadline=current_time,
                                            simulation_subtask=subtask,
                                            state=current_state,
                                        )
                                        nav_info = action_handler.get_actions_info(
                                            temp_target, [f"NAVIGATE_TO {target}"]
                                        )
                                        if nav_info:
                                            candidate_nav_times.append(
                                                nav_info.time_used
                                            )
                    following_nav = (
                        min(candidate_nav_times) if candidate_nav_times else 0
                    )
                    deadline = current_time + execution_time + following_nav
            elif timeslot_type == "non-critical":
                if has_dependency:
                    # rule 2-a: 후행 subtask인 경우
                    crit_edge = next(
                        (
                            edge
                            for edge in incoming_edges
                            if edge[2].get("info", {}).get("IsCritical", False)
                        ),
                        None,
                    )
                    if crit_edge:
                        pred_name = crit_edge[0]
                        interval = crit_edge[2]["info"]["Interval"]
                        predecessor_entry = next(
                            (
                                entry
                                for entry in current_state.completed_subtasks
                                if entry.subtask.name == pred_name
                            ),
                            None,
                        )
                        designated_start = (
                            predecessor_entry.end_time
                            if predecessor_entry
                            else current_time
                        ) + interval
                        candidate1 = designated_start
                        candidate2 = current_time + execution_time
                        deadline = max(candidate1, candidate2)
                    else:
                        deadline = current_time + execution_time
                else:
                    # rule 2-b: dependency가 없는 경우
                    deadline = current_time + execution_time

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
        start_time = new_current_time,
        end_time = new_current_time + real_exec_time,
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


def get_init_state(
    subtasks: List[Subtask], constraints: nx.DiGraph, scene_poses: dict
) -> SchedulerState:
    init_subtask = Subtask(
        task_name=None,
        name="Init",
        duration=Duration(interval=0, type="Init"),
        repetition=1,
        type="Init",
        execution=Execution(objects=[], primitive_actions=None),
        temporal_constraints=None,
    )
    init_completed = CompletedEntry(
        subtask=init_subtask,
        start_time=0.0,
        end_time=0.0,
    )

    init_state = SchedulerState(
        subtask=init_subtask,
        completed_subtasks=[init_completed],
        remaining_subtasks=subtasks,
        constraints=constraints,
        current_time=0,
        scene_positions=scene_poses,
        held_object=None,
    )
    return init_state


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
    approach_name="dag_edf"
    args = parse_arguments()
    controller = init_ai2thor()
    nav_graph = build_navigation_graph(controller)
    scene_name = SCENE_NAME
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")

    # Load the chosen task data
    task_files = list_task_files()
    task_file_name ,choice= get_user_task_choice(task_files)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = get_natural_language_from_task_file(f"{choice}")

    # Build tasks and constraints

    subtasks, constraints = build_tasks_and_constraints(task_data, True)

    computation_time = 0
    current_state = get_init_state(subtasks, constraints, scene_poses)
    result_schedule = []
    simulation_subtask_times = []
    for _ in range(len(subtasks)):
        #next_subtask는 Subtask 객체이다.

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
   

    gantt_chart(result_schedule, input_natural_language)
    # completed_Entry 객체를 Subtask객체로 변환.
    # start_time과 end_time을 추출해서 Subtask 객체 안에 저장.
    result_schedule_with_time =[]

    if args.simulation: 
        approach_name = f"{approach_name}_simulation"
        i = 0
        current_time=0

        for st in result_schedule:
            st.subtask.start_time_scheduled = st.start_time
            st.subtask.end_time_scheduled = st.end_time  


            st.subtask.start_time_simulation =current_time
            #Wait 과 Navigate는 실제 시뮬레이션 
            if st.subtask.type == "WAIT" or st.subtask.type == "NAVIGATE":
                st.subtask.end_time_simulation = current_time + st.subtask.duration.interval
                current_time += st.subtask.duration.interval
            else:
                st.subtask.end_time_simulation = current_time + simulation_subtask_times[i]
                current_time += simulation_subtask_times[i]
                i += 1

            result_schedule_with_time.append(st.subtask)

        result_args={
            "task_name": input_natural_language,
            "approach_name":approach_name,
            "result_schedule": result_schedule_with_time,
            "computation_time": computation_time,
            "scene_name": scene_name,
            "simulationTime": None
        }
    
        result_save(**result_args)


if __name__ == "__main__":
    main()
