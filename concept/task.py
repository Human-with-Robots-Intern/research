import json
from collections import deque


class Subtask:
    def __init__(
        self,
        task_name,
        task_location,
        name: str,
        duration: int,
        type: str,
        constraints: str = None,
    ):
        """subtask constructor

        Args:
            name (str): the name of the sub task
            duration (int): time cost to complete the task
            type (str, optional): controllable / uncontrollable
            constraints (str, optional): additional constraints for the uncontrollable sub task. Defualt is None (Space, Time, Temperature)
        """
        self.task_name = task_name
        self.location = task_location

        self.name = name
        self.duration = duration
        self.type = type
        self.constraints = constraints

    def __repr__(self):
        return f"Subtask(name={self.name}, duration={self.duration}, constraints={self.constraints}) \n"


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
        self.subtasks = deque(Subtask(name, location, *subtask) for subtask in subtasks)

    def get_controllable_subtasks(self):
        return [
            f"{subtask.name}"
            for subtask in self.subtasks
            if subtask.type == "Controllable"
        ]

    def is_contain_uncontrollable(self):
        uncontrollable_subtasks = [
            f"{subtask.name}"
            for subtask in self.subtasks
            if subtask.type == "Uncontrollable"
        ]

        if uncontrollable_subtasks:
            return True
        else:
            return False

    def check_containing(self, subtask_name):
        for subtask in self.subtasks:
            if subtask.name == subtask_name:
                return True

        return False

    def get_total_seq_duration(self):
        return sum(subtask.duration for subtask in self.subtasks)

    def __repr__(self):
        return f"Task(name={self.name}, location={self.location}, subtasks={self.subtasks})"


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


def get_all_controllable_subtasks(tasks):
    controllable_subtasks = []
    for task in tasks:
        controllable_subtasks.extend(task.get_controllable_subtasks())
    return controllable_subtasks


def parse_tasks(data):
    tasks = []

    for item in data:
        task_name = item["Task"]
        location = item["Location"]

        subtasks = []
        for subtask in item["Subtasks"]:
            constraints = subtask.get("Constraint")
            subtasks.append(
                (
                    subtask["Name"],
                    subtask["Duration"],
                    subtask["Type"],
                    constraints,
                )
            )
        tasks.append(Task(task_name, location, subtasks))
    return tasks
