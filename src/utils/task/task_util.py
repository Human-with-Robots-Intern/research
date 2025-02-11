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


def split_subtask_for_monitoring(
    curr_node,
    candidate: Candidate,
    early_cutoff: float,
    nav_manager,
):
    """
    서브태스크를 Early / Monitoring / Remain 으로 분할
    - (1) Early Subtask : 초반 ratio 비율에 해당하는 시간의 Primitive Action들
    - (2) Monitoring Subtask : 0.1초 (분할 없음)
    - (3) Remaining Subtask : 나머지 액션
    """

    # 3) 실제로 액션 분할
    early_actions, early_time, remain_actions, remain_time = (
        split_primitive_actions_by_time(curr_node, candidate, early_cutoff, nav_manager)
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
    curr_node: SimulationNode, candidate: Candidate, cutoff_time: float, nav_manager
) -> Tuple[List[str], float, List[str], float]:
    """
    Primitive Action을 "초반(cutoff_time)"과 "나머지"로 분할
    """
    actions = candidate.subtask.execution.primitive_actions
    init_agent_loc = curr_node.state.agent_location  # 분할 전 위치 기억
    agent_loc = curr_node.state.agent_location
    early_actions = []
    remain_actions = []
    time_used = 0.0
    i = 0

    while i < len(actions):
        action = actions[i]
        tokens = action.split()
        base_action = tokens[0].upper()

        # (A) 액션 시간 계산
        if base_action == "NAVIGATE_TO":
            if len(tokens) == 3:
                duration = float(tokens[2])
            else:
                duration = nav_manager._lookup_navigation_time(agent_loc, tokens[1])
        elif base_action == "WAIT":
            duration = float(tokens[1])
        elif base_action == "MONITORING":
            duration = MONITORING_DURATION
        else:
            duration = PRIMITIVE_ACTION_DURATION

        # (B) cutoff_time 비교
        if time_used >= cutoff_time:
            # 이미 early 구간을 채웠다면 남은 액션은 전부 remain
            remain_actions.append(action)
            i += 1
            continue

        leftover_for_early = cutoff_time - time_used

        # (C) 분할 로직
        if duration <= leftover_for_early:
            # 액션 전부 early에 할당
            early_actions.append(action)
            time_used += duration

            # NAVIGATE_TO 전체가 early에 들어간 경우 → 도착지 갱신
            if base_action == "NAVIGATE_TO":
                agent_loc = tokens[1]
            i += 1
        else:
            # 부분 분할 (NAVIGATE_TO or WAIT)
            if base_action in ["NAVIGATE_TO", "WAIT"]:
                # Early portion
                if base_action == "NAVIGATE_TO":
                    # e.g. "NAVIGATE_TO Table leftover_time"
                    early_actions.append(
                        f"{base_action} {tokens[1]} {leftover_for_early}"
                    )
                    # 나머지 시간은 remain
                    remain_time = duration - leftover_for_early
                    remain_actions.append(f"{base_action} {tokens[1]} {remain_time}")
                    # 여기서는 도착 안 했으므로 location 갱신 X
                else:  # WAIT
                    early_actions.append(f"{base_action} {leftover_for_early}")
                    remain_time = duration - leftover_for_early
                    remain_actions.append(f"{base_action} {remain_time}")

                time_used += leftover_for_early
                i += 1
            else:
                # GRASP 등 분할 불가능 → 통째로 remain
                remain_actions.append(action)
                i += 1

    # (D) early 구간이 cutoff_time에 못 미쳤다면 남은 부분 WAIT
    if time_used < cutoff_time:
        leftover_wait = cutoff_time - time_used
        early_actions.append(f"WAIT {leftover_wait}")
        time_used += leftover_wait

    early_total_time = time_used

    remain_total_time = (
        sum_action_durations(curr_node, candidate.subtask, nav_manager) - time_used
    )

    return early_actions, early_total_time, remain_actions, remain_total_time


def sum_action_durations(
    curr_node: SimulationNode, subtask: Subtask, nav_manager
) -> float:
    """
    Compute the total execution time for all primitive actions in 'subtask',
    WHILE temporarily updating 'curr_node.state.agent_location' for each NAVIGATE_TO.
    At the end, restore the original location to avoid side-effects.

    Warning:
        - This approach modifies the node's agent_location during the calculation.
        - Make sure this is safe in your search/plan context (e.g., if you're not branching from the same node afterward).
    """

    total = 0.0
    if not subtask.execution or not subtask.execution.primitive_actions:
        return 0.0

    actions = subtask.execution.primitive_actions

    # 2) 현재 location(로봇 위치)을 state에서 가져온다.
    current_loc = curr_node.state.agent_location
    if not current_loc:
        current_loc = "agent"

    # 3) 모든 액션 순회
    for action in actions:
        tokens = action.split()
        if not tokens:
            continue

        base_action = tokens[0].upper()

        if base_action == "NAVIGATE_TO":
            # e.g. "NAVIGATE_TO Kitchen" or "NAVIGATE_TO Kitchen 3.0"
            if len(tokens) >= 2:
                target_loc = tokens[1]
            else:
                # 잘못된 형식
                continue

            # 이동 시간 결정
            if len(tokens) == 3:
                # NAVIGATE_TO Kitchen 3.0
                try:
                    dur = float(tokens[2])
                except ValueError:
                    dur = nav_manager._lookup_navigation_time(current_loc, target_loc)
            else:
                dur = nav_manager._lookup_navigation_time(current_loc, target_loc)

            total += dur

            current_loc = target_loc

        elif base_action == "WAIT":
            if len(tokens) >= 2:
                try:
                    dur = float(tokens[1])
                except ValueError:
                    dur = 0.0
            else:
                dur = 0.0
            total += dur

        elif base_action == "MONITORING":
            total += MONITORING_DURATION

        else:
            # GRASP, PLACE 등
            total += PRIMITIVE_ACTION_DURATION

    # 4) 계산이 모두 끝난 후 total 반환
    return total
