import json


class Subtask:
    def __init__(self, name: str, duration: int, type: str, constraints: str = None):
        """subtask constructor

        Args:
            name (str): the name of the sub task
            duration (int): time cost to complete the task
            type (str, optional): controllable / uncontrollable
            constraints (str, optional): additional constraints for the uncontrollable sub task. Defualt is None (Space, Time, Temperature)
        """
        self.name = name
        self.duration = duration
        self.type = type
        self.constraints = constraints

    def __repr__(self):
        return f"Subtask(name={self.name}, duration={self.duration}, type={self.type}, constraints={self.constraints})"


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
        self.subtasks = [Subtask(*subtask) for subtask in subtasks]

    def get_controllable_subtasks(self):
        return [
            f"{subtask.name}"
            for subtask in self.subtasks
            if subtask.type == "Controllable"
        ]

    def get_duration(self):
        return sum(subtask.duration for subtask in self.subtasks)

    def __repr__(self):
        return f"Task(name={self.name}, location={self.location}, subtasks={self.subtasks})"


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
