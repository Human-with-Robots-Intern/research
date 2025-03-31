#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import time
from typing import List, Optional

import networkx as nx

from src.utils.common import create_module_logger
from src.utils.config import LOG_ROUND, SCENE_NAME
from src.utils.io_utils import (
    get_natural_language_from_task_file,
    get_user_task_choice,
    list_task_files,
    load_scene_positions,
    load_task_data_from_file,
    result_save,
)
from src.utils.task import TaskUtil
from src.utils.visualizers import visualize

try:
    from ithor.handlers.navigation_handler import build_navigation_graph
    from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
except ImportError:
    execute_subtask = None
    init_ai2thor = None
    build_navigation_graph = None

from core.dataclass import CompletedEntry, SchedulerState, SimulationNode
from core.task import Subtask, Task
from scheduler.constraint_handler import ConstraintHandler

log = create_module_logger(module_name=__name__, module_log=True)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="CPM Interval Scheduler with UI (Single-Agent)"
    )
    parser.add_argument("-d", "--decomposition", default=True, action="store_true")
    parser.add_argument("-v", "--visualize", default=True, action="store_true")
    parser.add_argument("-r", "--reset", default=True, action="store_true")
    parser.add_argument("--rag", default=False, action="store_true")
    parser.add_argument("-s", "--simulation", default=True, action="store_true")
    return parser.parse_args()


def cpm_schedule_with_constraint_handler(
    subtasks: List[Subtask],
    constraints: nx.DiGraph,
    constraint_handler: ConstraintHandler,
    scene_positions: dict,
) -> Optional[List[Subtask]]:
    """
    CPM Interval 로직 + 단일 에이전트 자원제약.
    => Earliest Start(선행 + interval)와 전 서브태스크 종료시점(global_time) 중 큰 값을 실제 시작시간으로 사용.
    """
    name2sub = {st.name: st for st in subtasks}

    try:
        topo_order = list(nx.topological_sort(constraints))
    except nx.NetworkXUnfeasible:
        log.error("[CPM] Constraints graph has a cycle => No feasible schedule.")
        return None

    completed_entries: List[CompletedEntry] = []

    # === 핵심: 단일 에이전트의 "현재 시간" 관리
    # global_time은 "지금까지 할당된 서브태스크 중, 가장 늦게 끝난 시점"
    global_time = 0.0

    for node in topo_order:
        if node not in name2sub:
            continue
        st_obj = name2sub[node]

        # ConstraintHandler가 참조할 state
        state_for_handler = SchedulerState(
            subtask=None,
            completed_subtasks=completed_entries,
            remaining_subtasks=[],
            constraints=constraints,
            current_time=0.0,  # 병렬일 경우 0이지만, 여기서는 global_time 함께 사용
            scene_positions=scene_positions,
            held_object=None,
        )
        curr_node = SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
            state=state_for_handler,
        )

        # (1) ConstraintHandler로부터 "선행작업 + interval"에 따른 earliest_start
        earliest_start_from_constraints, is_crit = (
            constraint_handler.get_earliest_start_time(curr_node, st_obj)
        )
        if earliest_start_from_constraints is None:
            log.error(f"[CPM] Subtask '{node}' => conflict => scheduling aborted.")
            return None

        # (2) 단일 에이전트 자원제약 => 실제 start_time = max(earliest_start_from_constraints, global_time)
        start_time_scheduled = max(earliest_start_from_constraints, global_time)

        # (3) 종료시점 계산
        end_time_scheduled = start_time_scheduled + st_obj.duration.interval

        # (4) 서브태스크에 기록
        st_obj.start_time_scheduled = start_time_scheduled
        st_obj.end_time_scheduled = end_time_scheduled

        # (5) completed_entries 갱신
        completed_entries.append(
            CompletedEntry(st_obj, start_time_scheduled, end_time_scheduled)
        )
        log.debug(
            f"[CPM] Subtask {st_obj.name}: "
            f"earliest={earliest_start_from_constraints}, global_time(before)={global_time}, "
            f"start={start_time_scheduled}, end={end_time_scheduled}"
        )

        # (6) 단일 에이전트 => global_time 갱신
        global_time = end_time_scheduled

    return subtasks


def main():
    args = parse_arguments()
    approach_name = "cpm_interval_singleagent"

    # (1) AI2-THOR (옵션)
    controller = None
    nav_graph = None
    if args.simulation:
        controller = init_ai2thor_controller()
        nav_graph = build_navigation_graph(controller)

    scene_name = SCENE_NAME
    scene_poses = load_scene_positions(f"{scene_name}_positions.json")

    # (2) 사용자 Task 선택 & 로드
    task_files = list_task_files()
    task_file_name, choice = get_user_task_choice(task_files, is_rag=args.rag)
    task_data = load_task_data_from_file(task_file_name)
    input_natural_language = (
        get_natural_language_from_task_file(f"{choice}") if choice else task_file_name
    )

    # (3) subtasks, constraints
    subtasks, constraints = TaskUtil.build_tasks_and_constraints(
        task_data, args.decomposition
    )

    # (4) 초기가시화(옵션)
    if args.visualize:
        visualize(approach_name, input_natural_language, constraints)

    # (5) CPM Interval + 단일 에이전트 스케줄
    constraint_handler = ConstraintHandler()
    t0 = time.time()
    result_subtasks = cpm_schedule_with_constraint_handler(
        subtasks, constraints, constraint_handler, scene_poses
    )
    comp_time = time.time() - t0

    if result_subtasks is None:
        log.error("[MAIN] No feasible solution found.")
        return

    # (6) 시뮬레이션(옵션)
    simulation_time = 0.0
    result_schedule = []
    if args.simulation and controller:
        # start_time_scheduled 오름차순 정렬
        result_subtasks_sorted = sorted(
            result_subtasks, key=lambda s: s.start_time_scheduled
        )

        for st in result_subtasks_sorted:
            st_start = simulation_time
            subtask_time, execution_status = execute_subtask(controller, st)
            st_end = simulation_time + subtask_time

            st.start_time_simulation = st_start
            st.end_time_simulation = st_end
            st.execution_status = execution_status

            simulation_time = st_end
            result_schedule.append(CompletedEntry(st, st_start, st_end))
    else:
        # 시뮬레이션 안 하면, CPM 결과만 쓰면 됨
        # CompletedEntry를 만들어 저장해두면, 나중에 result_save 할 때 편함
        for st in result_subtasks:
            result_schedule.append(
                CompletedEntry(st, st.start_time_scheduled, st.end_time_scheduled)
            )

    # (7) 결과 로그
    log.info("[MAIN] CPM Interval + Single Agent => success")
    for ce in result_schedule:
        log.info(
            f" - Subtask {ce.subtask.name} => "
            f"Scheduled: {round(ce.subtask.start_time_scheduled,2)}~{round(ce.subtask.end_time_scheduled,2)}, "
            f"Simulated: {round(getattr(ce.subtask,'start_time_simulation',0),2)}~{round(getattr(ce.subtask,'end_time_simulation',0),2)}"
        )

    # (8) 최종 그래프 시각화
    if args.visualize:
        visualize(
            approach_name, input_natural_language, constraints, plan=result_schedule
        )

    # (9) 결과 저장
    approach_name += "_simulation" if args.simulation else ""
    result_args = {
        "task_name": input_natural_language,
        "approach_name": approach_name,
        "result_schedule": result_schedule,
        "computation_time": comp_time,
        "scene_name": scene_name,
    }
    result_save(**result_args)


if __name__ == "__main__":
    main()
