from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import numpy as np


class Duration:
    def __init__(self, interval: int, duration_type: str = "Controllable"):
        self.interval = interval
        self.type = duration_type

    def __repr__(self):
        return f"Duration(interval={self.interval}, type={self.type})"


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


class TaskComponent(ABC):
    def __init__(self, name: str):
        self.name = name
        self.status = "Not Started"

    def update_status(self, new_status: str):
        valid_statuses = ["Not Started", "In Progress", "Completed"]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status: {new_status}")
        self.status = new_status


class Subtask(TaskComponent):
    def __init__(
        self,
        name: str,
        task_scene: Dict,
        duration: Duration,
        actions : List[str],
        temporal_constraints: Optional[List[TemporalConstraint]] = None,
        subtask_type: str = "Interaction",
    ):
        super().__init__(name)
        self.task_scene = task_scene
        self.duration_obj = duration
        self.actions = actions
        self.temporal_constraints = temporal_constraints or []
        self.type = subtask_type

    def duration(self):
        return self.duration_obj.interval

    def _decompose

    def __repr__(self):
        return (
            f"Subtask(name={self.name}, type={self.type}, task_scene={self.task_scene}, "
            f"duration={self.duration_obj}, decomposition={self.decomposition}, "
            f"temporal_constraints={self.temporal_constraints})"
        )

    @classmethod
    def from_dict(cls, data: Dict, decompose: bool = False):
        task_scene = data["TaskScene"]
        
        if decompose:
            duration = Duration(data["Duration"]["Interval"], data["Duration"]["Type"])
            decomposition = data["Decomposition"]
            temporal_constraints = [
                TemporalConstraint(
                    constraint["Type"],
                    constraint["Subtask"],
                    constraint["Interval"],
                    constraint["Urgency"],
                )
            for constraint in data.get("TemporalConstraints", [])
            ]
        return cls(
            name=data["Subtask"],
            task_scene=task_scene,
            duration=duration,
            decomposition=decomposition,
            temporal_constraints=temporal_constraints,
            subtask_type=data["Type"],
        )


class Task(TaskComponent):
    def __init__(self, name: str):
        super().__init__(name)
        self.subtasks: List[TaskComponent] = []

    def add_subtask(self, subtask: TaskComponent):
        self.subtasks.append(subtask)

    def duration(self):
        return sum(subtask.duration() for subtask in self.subtasks)

    def __repr__(self):
        subtasks_repr = ", ".join([str(subtask) for subtask in self.subtasks])
        return f"CompositeTask(name={self.name}, status={self.status}, subtasks=[{subtasks_repr}])"

    @classmethod
    def from_dict(cls, data: Dict):
        composite_task = cls(data["Task"])
        for subtask_data in data["Subtasks"]:
            composite_task.add_subtask(Subtask.from_dict(subtask_data))
        return composite_task


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
