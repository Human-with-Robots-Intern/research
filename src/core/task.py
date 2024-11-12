from typing import Dict, List, Optional

import networkx as nx


class Subtask:
    class Duration:
        def __init__(self, duration_type: str, interval: int):
            self.type = duration_type
            self.interval = interval

        def __repr__(self):
            return f"Duration(type={self.type}, interval={self.interval})"

    class Decomposition:
        def __init__(self, repetition: int, actions: list):
            self.repetition = repetition

            self.actions = actions

        def __repr__(self):
            return (
                f"Decomposition(repetition={self.repetition}, actions={self.actions})"
            )

    class RoI:
        def __init__(self, room, asset, objects) -> None:
            self.room = room
            self.asset = asset
            self.objects = objects

        def __repr__(self) -> str:
            return f"RoI(room={self.room}, asset={self.asset}, objects={self.objects})"

    class TemporalConstraint:
        def __init__(
            self, constraint_type: str, subtask: str, interval: int, urgency: bool
        ):
            self.type = constraint_type
            self.subtask = subtask
            self.interval = interval
            self.urgency = urgency

        def __repr__(self):
            return (
                f"TemporalConstraint(type={self.type}, subtask={self.subtask}, "
                f"interval={self.interval}, urgency={self.urgency})"
            )

    def __init__(
        self,
        task_name: str,
        name: str,
        type: str,
        roi: RoI,
        duration: Duration,
        decomposition: Decomposition,
        temporal_constraints: Optional[List[TemporalConstraint]] = None,
    ):
        self.task_name = task_name
        self.name = name
        self.type = type
        self.roi = roi
        self.duration = duration
        self.decomposition = decomposition
        self.temporal_constraints = temporal_constraints or []

    def __repr__(self):
        return f"Subtask({self.name}, duration={self.duration}, constraints={self.temporal_constraints})"


class Task:
    def __init__(self, name: str, subtasks: List[Subtask]):
        self.name = name
        self.subtasks = subtasks

    def __repr__(self):
        return f"Task(name={self.name}, subtasks={self.subtasks})"

    def get_total_seq_duration(self) -> int:
        return sum(subtask.duration.interval for subtask in self.subtasks)


def get_all_subtasks(tasks: List[Task]) -> List[Subtask]:
    return [subtask for task in tasks for subtask in task.subtasks]


def parse_tasks(data: List[Dict]) -> List[Task]:
    tasks = []
    for task in data:
        task_name = task["Task"]
        subtasks = []

        for subtask_data in task["Subtasks"]:
            subtask_name = subtask_data["Subtask"]
            subtask_type = subtask_data["Type"]
            roi = Subtask.RoI(
                room=subtask_data["TaskScene"]["Room"],
                asset=subtask_data["TaskScene"]["Assets"],
                objects=subtask_data["TaskScene"]["Objects"],
            )
            duration = Subtask.Duration(
                duration_type=subtask_data["Duration"]["Type"],
                interval=subtask_data["Duration"]["Interval"],
            )
            decomposition = Subtask.Decomposition(
                repetition=subtask_data["Decomposition"]["Repetition"],
                actions=subtask_data["Decomposition"]["Actions"],
            )

            # Parse temporal constraints
            temporal_constraints_data = subtask_data.get("TemporalConstraints", [])
            temporal_constraints = [
                Subtask.TemporalConstraint(
                    constraint_type=tc["Type"],
                    subtask=tc["Subtask"],
                    interval=tc["Interval"],
                    urgency=tc["Urgency"],
                )
                for tc in temporal_constraints_data
            ]

            subtask = Subtask(
                task_name=task_name,
                name=subtask_name,
                type=subtask_type,
                roi=roi,
                duration=duration,
                decomposition=decomposition,
                temporal_constraints=temporal_constraints,
            )
            subtasks.append(subtask)

        tasks.append(Task(name=task_name, subtasks=subtasks))

    return tasks


def parse_constraints(tasks: List[Task]) -> nx.DiGraph:
    G = nx.DiGraph()

    # Add all subtask nodes to the graph
    for task in tasks:
        for subtask in task.subtasks:
            subtask_node = subtask.name
            subtask_type = subtask.type
            G.add_node(subtask_node, subtask_type=subtask_type)

            # Add edges based on temporal constraints
            for constraint in subtask.temporal_constraints:
                if constraint.subtask:
                    edge_data = {
                        "info": {
                            "Type": constraint.type,
                            "Interval": constraint.interval,
                            "Urgency": constraint.urgency,
                        }
                    }
                    if constraint.type == "Before":
                        G.add_edge(subtask_node, constraint.subtask, **edge_data)
                    elif constraint.type == "After":
                        G.add_edge(constraint.subtask, subtask_node, **edge_data)
                else:
                    raise ValueError("Constrained Node is not exist")

    return G


import numpy as np


class ScheduledTask:
    def __init__(self, name, start, end, duration, subtask=None):
        self.name = name
        self.start = start  # 시작 시간
        self.end = end  # 끝 시간
        self.duration = duration  # 지속 시간
        self.subtask = subtask  # 서브태스크 자체 정보

    def __repr__(self):
        return (
            f"ScheduledTask(name={self.name}, "
            f"subtask={self.subtask},start={self.start}, end={self.end}, duration={self.duration})"
        )


def simulate_task_plan(task_plan):
    """
    Simulate the execution of a task plan by adding noise to the task durations.

    Args:
        task_plan (list of ScheduledTask): The planned tasks.

    Returns:
        list of ScheduledTask: The simulated tasks with actual start and end times.
    """
    sim_schedule = []
    current_time = 0

    for task in task_plan:
        # Simulate task duration with some noise
        while True:
            sim_task_duration = round(np.random.normal(task.duration, 0.1), 3)
            if sim_task_duration > 0:
                break
        sim_task_start_time = round(current_time, 3)
        sim_task_end_time = sim_task_start_time + sim_task_duration

        # Create a simulated ScheduledTask
        sim_task = ScheduledTask(
            name=task.name,
            start=sim_task_start_time,
            end=sim_task_end_time,
            duration=sim_task_duration,
        )
        sim_schedule.append(sim_task)

        current_time = sim_task_end_time  # Update current time for the next task

    return sim_schedule


def convert_tree_to_schedule(root):
    schedules = []

    # Traverse the tree to gather task paths
    def traverse_tree(node, current_path):

        task = ScheduledTask(
            node.name,
            node.makespan - node.duration,
            node.makespan,
            node.duration,
        )
        if not node.children:  # If it's a leaf node, store the path
            schedules.append(current_path + [task])
        for child in node.children:
            traverse_tree(
                child,
                current_path + [task],
            )

    traverse_tree(root, [])

    return schedules[0][1:]


from typing import Dict, List

from core.task import Subtask, Task


class SubtaskDecomposer:
    def __init__(self, subtask: Subtask):
        self.subtask = subtask

    def decompose(self) -> List[Subtask]:
        if self.subtask.decomposition.repetition > 1:
            decomposed_subtask = self._decompose_subtask()
            return decomposed_subtask
        else:
            return [self.subtask]

    def _decompose_subtask(self) -> List[Subtask]:
        decomposed_subtasks = []
        subtask_part_num = self.subtask.decomposition.repetition

        object_counts = self._calculate_object_counts(subtask_part_num)

        for i in range(subtask_part_num):
            decomposed_subtask = self._create_decomposed_subtask(i, object_counts)
            decomposed_subtasks.append(decomposed_subtask)

        return decomposed_subtasks

    def _calculate_object_counts(self, subtask_part_num: int) -> Dict[str, int]:
        return {
            obj: max(1, num // subtask_part_num)
            for obj, num in self.subtask.roi.objects.items()
        }

    def _create_decomposed_subtask(
        self, part_index: int, object_counts: Dict[str, int]
    ) -> Subtask:
        decomposed_subtask_name = f"{self.subtask.name}_part_{part_index + 1}"
        decomposed_roi = Subtask.RoI(
            room=self.subtask.roi.room,
            asset=self.subtask.roi.asset,
            objects=object_counts,
        )
        decomposed_duration = Subtask.Duration(
            duration_type=self.subtask.duration.type,
            interval=(
                self.subtask.duration.interval // self.subtask.decomposition.repetition
            ),
        )
        decomposed_decomposition = Subtask.Decomposition(
            repetition=1,
            actions=self.subtask.decomposition.actions,
        )
        decomposed_temporal_constraints = self._get_temporal_constraints(part_index)

        return Subtask(
            name=decomposed_subtask_name,
            type=self.subtask.type,
            roi=decomposed_roi,
            duration=decomposed_duration,
            decomposition=decomposed_decomposition,
            temporal_constraints=decomposed_temporal_constraints,
        )

    def _get_temporal_constraints(
        self, part_index: int
    ) -> List[Subtask.TemporalConstraint]:
        if part_index == 0:
            return self.subtask.temporal_constraints
        else:
            return [
                Subtask.TemporalConstraint(
                    constraint_type="After",
                    subtask=f"{self.subtask.name}_part_{part_index}",
                    interval=0,
                    urgency=False,
                )
            ]


def decompose_tasks(tasks: List[Task]) -> List[Task]:
    """
    Decomposes tasks with subtasks that have a repetition count greater than 1.

    Args:
        tasks (List[Task]): The original list of tasks.

    Returns:
        List[Task]: The list of tasks with decomposed subtasks.
    """
    decomposed_tasks = []
    subtask_mapping = {}  # Map from original subtask names to decomposed parts

    for task in tasks:
        decomposed_subtasks = []
        for subtask in task.subtasks:
            decomposer = SubtaskDecomposer(subtask)
            decomposed_parts = decomposer.decompose()
            decomposed_subtasks.extend(decomposed_parts)
            subtask_mapping[subtask.name] = decomposed_parts

        decomposed_tasks.append(Task(name=task.name, subtasks=decomposed_subtasks))

    # Update constraints to point to the correct decomposed parts
    for decomposed_task in decomposed_tasks:
        for decomposed_subtask in decomposed_task.subtasks:
            decomposed_subtask.temporal_constraints = update_constraints(
                decomposed_subtask.temporal_constraints, subtask_mapping
            )

    return decomposed_tasks


def update_constraints(
    constraints: List[Subtask.TemporalConstraint],
    subtask_mapping: Dict[str, List[Subtask]],
) -> List[Subtask.TemporalConstraint]:
    """
    Updates temporal constraints to refer to the correct decomposed subtask parts.

    Args:
        constraints (List[Subtask.TemporalConstraint]): Original constraints to update.
        subtask_mapping (Dict[str, List[Subtask]]): Mapping of original subtasks to their decomposed parts.

    Returns:
        List[Subtask.TemporalConstraint]: Updated list of temporal constraints.
    """
    updated_constraints = []

    for constraint in constraints:
        if constraint.subtask in subtask_mapping:
            # Point the constraint to the last part of the decomposed subtask
            last_decomposed_part = subtask_mapping[constraint.subtask][-1]
            updated_constraints.append(
                Subtask.TemporalConstraint(
                    constraint_type=constraint.type,
                    subtask=last_decomposed_part.name,
                    interval=constraint.interval,
                    urgency=constraint.urgency,
                )
            )
        else:
            updated_constraints.append(constraint)

    return updated_constraints
