import copy
import uuid
from typing import List, Tuple

from networkx import DiGraph

from core.task import Duration, Execution, Subtask, Task, TaskGraphBuilder
from scheduler.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from utils.constants import (
    MONITORING_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)


def tasks_to_subtasks(tasks, mode="all"):
    subtasks = []
    if mode == "all":
        for task in tasks:
            subtasks.extend(task.subtasks)
    elif mode == "name":
        for task in tasks:

            subtasks.extend([subtask.name for subtask in task.subtasks])

    return subtasks


def adjust_subtasks_duration(subtasks: List[Subtask]) -> List[Subtask]:
    """
    Adjust the duration intervals of subtasks in the given tasks based on the agent's knowledge.

    Args:
        tasks (List[Task]): List of tasks whose subtasks' durations are to be adjusted.

    Returns:
        List[Task]: The list of tasks with adjusted subtask durations.
    """

    def _get_action_duration(subtask: Subtask) -> float:
        total_duration = 0.0
        for primitive_action in subtask.execution.primitive_actions:
            action_name = primitive_action.split()[0]
            is_valid_action = True if action_name in PRIMITIVE_ACTION_SET else False
            if not is_valid_action:
                raise ValueError(
                    f"Action '{action_name}' not found in the primitive action set."
                )
            if action_name not in {"NAVIGATE_TO", "MONITORING", "WAIT"}:
                total_duration += PRIMITIVE_ACTION_DURATION
        return total_duration

    for subtask in subtasks:

        subtask.duration.interval = _get_action_duration(subtask)
    return subtasks


def revision_primitive_actions(tasks):
    """Check and revision if the PLACE action is followed by a NAVIGATE action."""
    for task in tasks:
        for subtask in task.subtasks:
            actions = subtask.execution.primitive_actions
            updated_actions = []
            for i, action in enumerate(actions):
                if i > 0 and "PLACE" in action and "NAVIGATE" not in actions[i - 1]:
                    to_obj = action.split(" ")[1]
                    updated_actions.append(f"NAVIGATE_TO {to_obj}")
                if "PLACE" in action and "Sink" in action and "SinkBasin" not in action:
                    to_obj = action.split(" ")[1] + "|SinkBasin"
                    updated_actions.append(f"PLACE_INSIDE {to_obj}")
                updated_actions.append(action)
            subtask.execution.primitive_actions = updated_actions
    return tasks


def build_tasks_and_constraints(
    task_data: dict, enable_decomposition: bool
) -> tuple[list[Task], dict]:
    """
    Parse the tasks from data, revise primitive actions, adjust subtask duration,
    optionally decompose, and build the task graph.

    :param task_data: The raw task data loaded from JSON.
    :param enable_decomposition: Whether to enable subtask decomposition.
    :return: A tuple containing the list of Task objects and the task graph/constraints.
    """
    tasks = Task.parse_instruction(task_data)
    tasks = revision_primitive_actions(tasks)

    if enable_decomposition:
        for task in tasks:
            task.decompose_subtasks()

    task_graph_builder = TaskGraphBuilder()
    task_graph = task_graph_builder.build_graph(tasks)
    subtasks = tasks_to_subtasks(tasks)
    subtasks = adjust_subtasks_duration(subtasks)
    return subtasks, task_graph


def get_init_state(subtasks: List[Subtask], constraints: DiGraph) -> SchedulerState:
    init_subtask = Subtask(
        task_name=None,
        name="Init",
        duration=Duration(interval=0, type="Init"),
        repetition=1,
        type="Init",
        execution=Execution(objects=[], primitive_actions=[f"Monitoring 0"]),
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
        agent_location="agent",
        current_time=0,
    )
    return init_state


def get_monitoring_subtask(obj: str) -> Subtask:
    monitoring_subtask = Subtask(
        task_name=None,
        name="Monitoring",
        duration=Duration(interval=MONITORING_DURATION, type="Monitor"),
        repetition=1,
        type="Monitor",
        execution=Execution(objects=[], primitive_actions=[f"Monitoring {obj}"]),
        temporal_constraints=None,
    )

    return monitoring_subtask


def make_monitoring_subtask(target_sub_name: str, obj: str) -> Subtask:
    mon_sub = get_monitoring_subtask(obj)
    mon_sub.name = f"Monitoring for {target_sub_name}_{obj}_{uuid.uuid4().hex[:8]}"
    mon_sub.decomposed = True
    return mon_sub


# def make_early_subtask(original_sub: Subtask, early_exec_time: float) -> Subtask:
#     early_sub = copy.deepcopy(original_sub)
#     for primitive_action in early_sub.execution.primitive_actions:
#         pass
#     early_sub.name += "_early"
#     early_sub.duration.interval = early_exec_time
#     early_sub.decomposed = True
#     return early_sub


# def make_remain_subtask(original_sub: Subtask, remain_duration: float) -> Subtask:
#     remain_sub = copy.deepcopy(original_sub)
#     remain_sub.name += "_remain"
#     remain_sub.duration.interval = remain_duration
#     remain_sub.decomposed = True
#     return remain_sub


def split_subtask_for_monitoring(
    curr_node,
    candidate: Candidate,
    nav_manager,
    ratio: float = 0.7,
):
    """
    서브태스크를 Early / Monitoring / Remain 으로 분할
    - (1) Early Subtask : 초반 ratio 비율에 해당하는 시간의 Primitive Action들
    - (2) Monitoring Subtask : 0.1초 (분할 없음)
    - (3) Remaining Subtask : 나머지 액션
    """
    # 1) 원본 서브태스크 전체 액션 시간
    total_time = sum_action_durations(curr_node, candidate.subtask, nav_manager)

    # 2) early에 할당할 시간
    monitoring_timing = total_time * ratio

    # 3) 실제로 액션 분할
    early_actions, early_time, remain_actions, remain_time = (
        split_primitive_actions_by_time(
            curr_node, candidate.subtask, monitoring_timing, nav_manager
        )
    )

    # 4) Early 서브태스크
    early_sub = copy.deepcopy(candidate.subtask)
    early_sub.name += "_early"
    early_sub.duration.interval = early_time
    early_sub.execution.primitive_actions = early_actions
    early_sub.decomposed = True

    # 5) Monitoring 서브태스크(0.1초)
    monitoring_obj = curr_node.state.subtask.execution.primitive_actions[-1].split(" ")[
        -1
    ]
    related_subtask_name = candidate.deadline.subtask_name
    monitor_sub = Subtask(
        task_name=candidate.subtask.task_name,
        name=f"Monitor for {related_subtask_name}_{uuid.uuid4().hex[:6]}",
        duration=Duration(interval=MONITORING_DURATION, type="Monitor"),
        repetition=1,
        type="Monitor",
        execution=Execution(
            objects=[], primitive_actions=[f"MONITORING {monitoring_obj}"]
        ),
        decomposed=True,
    )

    # 6) Remaining 서브태스크
    remain_sub = copy.deepcopy(candidate.subtask)
    remain_sub.name += "_remain"
    remain_sub.duration.interval = remain_time
    remain_sub.execution.primitive_actions = remain_actions
    remain_sub.decomposed = True

    return early_sub, monitor_sub, remain_sub


def split_primitive_actions_by_time(
    curr_node: SimulationNode, subtask: Subtask, cutoff_time: float, nav_manager
) -> Tuple[List[str], float, List[str], float]:
    """
    Primitive Action을 "초반(cutoff_time)"과 "나머지"로 분할
    - NAVIGATE_TO / WAIT 만 분할 가능
    - MONITORING 은 분할 금지 (그대로 한 덩어리)
    - 나머지 액션도 분할 안 함 (그대로 한 덩어리)
    - 초반 시간이 남으면 leftover_time 만큼 WAIT 추가

    Args:
    - curr_node : 현재 시뮬레이션 노드
    - subtask   : 분할 대상 서브태스크
    - cutoff_time (float): 초반 실행 시간(예: total_time * 0.7)
    - nav_manager : 이동 시간 계산에 사용

    Returns:
    - early_actions      : 초반 실행에 들어갈 액션 리스트
    - early_total_time   : 초반 실행 시간 합
    - remain_actions     : 나머지 액션 리스트
    - remain_total_time  : 나머지 실행 시간 합
    """
    # 분해 대상 action list
    actions = subtask.execution.primitive_actions

    early_actions = []
    remain_actions = []

    time_used = 0.0
    i = 0

    while i < len(actions):
        action = actions[i]
        # base_action, (obj_name), duration 추출
        tokens = action.split()
        base_action = tokens[0].upper()

        # (A) 액션 시간 계산
        duration = 0.0
        if base_action == "NAVIGATE_TO":
            # NAVIGATE_TO <object> [time]
            if len(tokens) == 3:
                # 예: "NAVIGATE_TO COUNTERTOP 3.0"
                duration = float(tokens[2])
            else:
                # 시간이 명시 안된 경우 NavManager로 추정
                duration = nav_manager.compute_specific_navigation_time(
                    curr_node, tokens[1]
                )
        elif base_action == "WAIT":
            # WAIT [time]
            duration = float(tokens[1])

        elif base_action == "MONITORING":
            # Monitoring은 분할 안 함
            duration = MONITORING_DURATION
        else:
            # 나머지 액션은 기본 0.1초
            duration = PRIMITIVE_ACTION_DURATION

        # (B) cutoff_time과 비교
        if time_used >= cutoff_time:
            # 이미 초반 할당 시간 초과 → 남은 액션으로 이동
            remain_actions.append(action)
            i += 1
            continue

        leftover_for_early = cutoff_time - time_used

        # (C) 분할 로직
        if duration <= leftover_for_early:
            # 이 액션 전체를 early에 할당
            early_actions.append(action)
            time_used += duration
            i += 1
        else:
            # 만약 NAVIGATE_TO 또는 WAIT이라면, 분할 가능
            if base_action in ["NAVIGATE_TO", "WAIT"]:
                # early portion
                early_actions.append(
                    f"{tokens[0]} {tokens[1]} {leftover_for_early}"
                    if base_action == "NAVIGATE_TO" and len(tokens) >= 2
                    else f"{base_action} {leftover_for_early}"
                )
                # remain portion
                remain_time = duration - leftover_for_early

                if base_action == "NAVIGATE_TO" and len(tokens) >= 2:
                    # NAVIGATE_TO <object> remain_time
                    object_name = tokens[1]
                    remain_actions.append(f"NAVIGATE_TO {object_name}")
                else:
                    # WAIT remain_time
                    remain_actions.append(f"WAIT {remain_time}")

                time_used += leftover_for_early
                i += 1
            else:
                # 나머지 액션(GRASP 등)은 분할 불가 → 통째로 remain
                remain_actions.append(action)
                i += 1

    # (D) 초반에 time_used < cutoff_time이면, 남은 부분만큼 WAIT 추가
    if time_used < cutoff_time:
        leftover_wait = cutoff_time - time_used
        early_actions.append(f"WAIT {leftover_wait}")
        time_used += leftover_wait

    early_total_time = time_used
    remain_total_time = (
        sum_action_durations(curr_node, subtask, nav_manager) - time_used
    )

    return early_actions, early_total_time, remain_actions, remain_total_time


def sum_action_durations(
    curr_node: SimulationNode, subtask: Subtask, nav_manager
) -> float:
    total = 0.0
    actions = subtask.execution.primitive_actions
    for action in actions:
        tokens = action.split()
        base_action = tokens[0].upper()

        if base_action == "NAVIGATE_TO":
            if len(tokens) == 3:
                # NAVIGATE_TO <object> <time>
                dur = float(tokens[2])
            else:
                # 시간이 명시 안됨 → 직접 계산
                dur = nav_manager.compute_specific_navigation_time(curr_node, tokens[1])
        elif base_action == "WAIT" and len(tokens) >= 2:
            dur = float(tokens[1])
        elif base_action == "MONITORING":
            # e.g. "MONITORING <Obj>"
            dur = MONITORING_DURATION
        else:
            # GRASP, PLACE_INSIDE 등
            dur = PRIMITIVE_ACTION_DURATION
        total += dur
    return total
