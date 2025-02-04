import copy
from typing import List

from networkx import DiGraph

from core.task import Duration, Execution, Subtask, Task, TaskGraphBuilder
from scheduler.dataclass import CompletedEntry, SchedulerState
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
        pending_monitoring=None,
        constraints=constraints,
        agent_location="agent",
        current_time=0,
    )
    return init_state


def get_monitoring_subtask() -> Subtask:
    monitoring_subtask = Subtask(
        task_name=None,
        name="Monitoring",
        duration=Duration(interval=MONITORING_DURATION, type="Monitor"),
        repetition=1,
        type="Monitor",
        execution=Execution(
            objects=[], primitive_actions=[f"Monitoring {MONITORING_DURATION}"]
        ),
        temporal_constraints=None,
    )

    return monitoring_subtask


def make_early_subtask(original_sub: Subtask, early_exec_time: float) -> Subtask:
    early_sub = copy.deepcopy(original_sub)
    early_sub.name += "_early"
    early_sub.duration.interval = early_exec_time
    early_sub.type = "Interaction"
    early_sub.decomposed = True
    return early_sub


def make_monitoring_subtask(original_sub_name: str) -> Subtask:
    mon_sub = get_monitoring_subtask()
    mon_sub.name = f"Monitoring for {original_sub_name}"
    mon_sub.type = "Monitoring"
    mon_sub.decomposed = True
    return mon_sub


def make_remain_subtask(original_sub: Subtask, remain_duration: float) -> Subtask:
    remain_sub = copy.deepcopy(original_sub)
    remain_sub.name += "_remain"
    remain_sub.duration.interval = remain_duration
    remain_sub.type = "Interaction"
    remain_sub.decomposed = True
    return remain_sub
