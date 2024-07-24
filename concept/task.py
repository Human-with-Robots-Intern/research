import json
from collections import deque


class Subtask:
    def __init__(
        self,
        task_name,
        task_location,
        name: str,
        type: str,
        duration: int,
        constraints: str = None,
    ):
        """subtask constructor

        Args:
            name (str): the name of the sub task
            type (str): Interaction / Monitoring
            duration (int): time cost to complete the task
            constraints (str, optional): Temporal / Resource constraint to start subtask
        """
        self.task_name = task_name
        self.location = task_location

        self.name = name
        self.type = type
        self.duration = duration
        self.constraints = constraints

    def __repr__(self):
        constraint = None
        if self.constraints.get["After"]:
            precedence_subtask = self.constraints["After"]
            time_interval = self.constraints["Interval"]
            constraint = f"can start {time_interval} after {precedence_subtask} end"
        else:
            constraint = f"don't have any constraints"
        return f"Subtask(name={self.name} (duration={self.duration}) constraints={constraint}) \n"


class Task:
    def __init__(self, name: str, location: str, subtasks: list[tuple]):
        """_summary_

        Args:
            name (str): Task name
            location (str): Task Location (Kichen, Living Room, Restroom, Bedroom)
            subtasks (list[tuple]): list of suptask (tuple)
        """

        self.name = name
        self.location = location
        self.subtasks = [Subtask(name, location, *subtask) for subtask in subtasks]

    def __repr__(self):
        return f"Task(name={self.name}, location={self.location}, subtasks={self.subtasks})"

    def get_total_seq_duration(self):
        return sum(subtask.duration for subtask in self.subtasks)


def get_all_subtasks(tasks: list[Task], mode: str = "name"):
    if mode == "name":
        subtasks = {}
        for task in tasks:
            for subtask in task.subtasks:
                subtasks[subtask.name] = task.name
    elif mode == "all":
        subtasks = []
        for task in tasks:
            subtask_group = []
            for subtask in task.subtasks:
                subtask_group.append(subtask)
            subtasks.append(subtask_group)
    return subtasks


def parse_tasks(data):
    tasks = []

    for task in data:
        task_name = task["Task"]
        location = task["Location"]

        subtasks = []
        for subtask in task["Subtasks"]:
            subtask_name = subtask["Subtask"]
            subtask_type = subtask["Type"]
            subtask_duration = subtask["Duration"]["Interval"]
            subtask_temporal_constraint = subtask["Constraints"]["TemporalConstraint"]
            subtask_resource_constraint = subtask["Constraints"]["ResourceConstraint"]
            subtask_effect = subtask["Effect"]

            subtasks.append(
                (
                    subtask_name,
                    subtask_type,
                    subtask_duration,
                    subtask_temporal_constraint,
                    # subtask_resource_constraint,
                    # subtask_effect,
                )
            )

        tasks.append(Task(task_name, location, subtasks))
    return tasks
