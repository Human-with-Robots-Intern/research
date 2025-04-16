import argparse
import heapq
from typing import List, Optional, Tuple
import networkx as nx
import heapq
import time
from pathlib import Path
from simulation.runner_ai2thor import execute_subtask

from utils.common.logger import create_module_logger
from utils.io_utils.result_saver import result_save


PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
)  # 프로젝트 루트 경로
ASSETS_PATH = PROJECT_ROOT / Path("assets")  # assets 폴더 경로
from ithor.utils.math_utils import load_navigation_graph
from simulation.runner_ai2thor import init_ai2thor_controller
from utils.config.constants import RESULT_PATH
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
from utils.visualizers.visualizer import visualize


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


def compute_nav_time(subtask: Subtask, current_state: SchedulerState, action_handler) -> float:
    """
    subtask 내 첫 번째 NAVIGATE_TO primitive action의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(deadline=current_state.current_time, simulation_subtask=subtask, state=current_state)
    nav_time = 0.0
    
    # 모든 subtask의 첫 action은 NAVIGATE_TO 로 시작되어야 한다. 아니라면 문제가 있는것. 확인하라
    if not subtask.execution.primitive_actions[0].startswith("NAVIGATE_TO"):
        raise("first action is not NAVIGATE_TO")
    
    for act in subtask.execution.primitive_actions or []:
            if act.startswith("NAVIGATE_TO"):
                nav_info = action_handler.get_actions_info(temp_node, [act])
                if nav_info:
                    nav_time = nav_info.time_used
                break

    return nav_time

def offline_subtask_execution(subtask: Subtask, current_state: SchedulerState, action_handler:ActionHandler) -> float:
    """
    현재 subtask의 실행 시간을 시뮬레이션하여 반환
    """
    temp_node = SimulationNode(deadline= current_state.current_time, simulation_subtask=subtask, state=current_state)
    actions = subtask.execution.primitive_actions or []
    exec_info = action_handler.get_actions_info(temp_node, actions) if actions else None

    # exec_info를 추출하는데 실패할경우 None을 return
    return exec_info if exec_info else None



def compute_deadline_for_subtask(subtask: Subtask, current_state: SchedulerState,nav_time: float,) -> float:
    """
    subtask에 대한 deadline을 timeslot 유형과 dependency 조건에 따라 계산한다.
    
    [규칙]
        1. 기본규칙
            deadline = current_time + nav_time
        2. subtask가 non critical in edge만 있으면: 
            deadline = max(선행 subtask의 end_time + edge의 interval)
        3. subtask가 critical in edge를 포함한다면:
            deadline = critical edge의(선행 subtask의 end_time + edge interval)

    """
    # 가독성을 위한 변수 선언
    constraints= current_state.constraints
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
    deadline = current_time + nav_time

    if incoming_edges :
        #규칙 2
        non_critical_deadlines = [
            next(
                (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                current_time
            ) + data["info"]["Interval"]
            for u, v, data in incoming_edges
        ]
        # 두 non-critical-edge가 있으면 그중 느린쪽에 맞추면 해결됨. critical이 존재하면 아래에서 덮어 써짐.
        deadline =  max(non_critical_deadlines) 

    if critical_edges:
        #규칙 3
        critical_deadlines = [
            next(
                (entry.end_time for entry in current_state.completed_subtasks if entry.subtask.name == u),
                current_time
            ) + data["info"]["Interval"]
            for u, v, data in critical_edges
            
        ]
        # 어짜피 두 critical edge가 있으면 둘중 하나는 포기해야하므로 급한거 먼저 처리하도록 구성. 그러나 critical이 두개 있는경우는 없음
        deadline = min(critical_deadlines) 

    return deadline


def get_next_subtask_edf(current_state: SchedulerState, nav_graph) -> Optional[Subtask]:
    """
    각 실행 가능한 subtask에 대해 deadline을 산출한 후, deadline이 가장 짧은 subtask를 선택한다.    
    """
    import heapq
    action_handler = ActionHandler(nav_graph)    

    # pending_edges = get_pending_edges(current_state)
    # timeslot_type = get_timeslot_type(pending_edges)

    queue = []
    for subtask in current_state.remaining_subtasks:
        if not is_executable(subtask, current_state):
            continue

        nav_time = compute_nav_time(subtask, current_state, action_handler)
        deadline = compute_deadline_for_subtask(subtask, current_state, nav_time)
        sim_node = SimulationNode(deadline=deadline, simulation_subtask=subtask, state=current_state)
        heapq.heappush(queue, sim_node)
        # remaining_subtask들의 deadline 정보를 삽입
        subtask.deadline = deadline

    if queue:
        chosen_node = heapq.heappop(queue)
        # chosen_node.simulation_subtask.deadline = deadline
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
    
    exec_info = offline_subtask_execution(next_subtask, current_state, action_handler)
    real_exec_time = exec_info.time_used
    if real_exec_time == None :
        real_exec_time = next_subtask.duration.interval

    # subtask의 duration.interval을 실제 실행 시간으로 업데이트.
    next_subtask.duration.interval = real_exec_time

    # -------------------------------
    # 2) After 제약(interval=X) 처리
    # -------------------------------
    constraints = current_state.constraints
    incoming_edges = list(constraints.in_edges(next_subtask.name, data=True))
    designated_start = current_time  # 기본적으로는 지금 바로 시작

    # 현재 edge 가 critical이면 critical subtask의 predecessor를 찾아서 그 subtask 기준으로 연산해야함. 
    # 아니면 아무거나 써도 됨.

    wait_entries = []
    #incoming_edge 가 있으면 deadline 규칙에 따라 연산된 deadline 시간에 subtask 시작
    if incoming_edges:
        designated_start = next_subtask.deadline
    

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
            nav_time = compute_nav_time(next_subtask, current_state, action_handler)
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
        scene_positions=current_state.scene_positions,  # scene_positions도 필요시 갱신?
        held_object=current_state.held_object,
        agent_location=current_state.agent_location,
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
        default=True,
        action="store_true",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 출력 수준 설정 (default: INFO)"
    )
    parser.add_argument(
        "--scene",
        type=str,
        default="FloorPlan1",
        help="시뮬레이션에 사용할 씬 이름 (default: FloorPlan1)"
    )
    return parser.parse_args()

def main():

    # Set up the AI2-THOR controller and navigation graph
    approach_name = "dag_edf"
    scnen_name = args.scene
    args = parse_arguments()
    controller = init_ai2thor_controller(scene_name)
    nav_graph = load_navigation_graph(controller)
    scene_name = args.scene
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
        next_subtask = get_next_subtask_edf(current_state, nav_graph)

        if next_subtask is None:
            break
        current_state = update(current_state, next_subtask, nav_graph)
        subtask_scheduling_time = time.time() - subtask_scheduling_time_start

        computation_time += subtask_scheduling_time

        # 현재 시뮬레이션 실행시 schedule된 wait이나 navigate subtask는 단독으로 실행되지 않는다.
        if args.simulation:
            # 터미널에서 src/baselines/def/dag_edf.py -s 실행시 사용됨

            subtask_time, execution_status = execute_subtask(controller, next_subtask, args.log_level)
            simulation_subtask_times.append(subtask_time)
            next_subtask.execution_status = execution_status

    result_schedule = current_state.completed_subtasks
    result_schedule.pop(0)
    # completed_Entry 객체를 Subtask객체로 변환.
    # start_time과 end_time을 추출해서 Subtask 객체 안에 저장.

    output_path = RESULT_PATH / input_natural_language / "metadata"
    output_path.mkdir(parents=True, exist_ok=True)


    # plot_completed_subtasks_gantt(result_schedule, gantt_path)
    if args.simulation:
        approach_name = f"{approach_name}_simulation"
        visualize(approach_name, input_natural_language, constraints, result_schedule)
        i = 0
        current_time = 0

        for ce in result_schedule:
            ce.subtask.start_time_scheduled = ce.start_time
            ce.subtask.end_time_scheduled = ce.end_time

            ce.subtask.start_time_simulation = current_time
            # Wait 과 Navigate는 실제 시뮬레이션
            if ce.subtask.type == "WAIT" or ce.subtask.type == "NAVIGATE":
                ce.subtask.end_time_simulation = current_time + ce.subtask.duration.interval
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
            "constraints": constraints,
            # "simulationTime": None,
        }
        
        result_save(**result_args)


if __name__ == "__main__":
    main()