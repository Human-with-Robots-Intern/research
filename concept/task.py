from typing import Dict, List, Tuple

import networkx as nx
from matplotlib import pyplot as plt


class Subtask:
    class Duration:
        def __init__(self, duration_type: str, interval: int):
            self.type = duration_type
            self.interval = interval

        def __repr__(self):
            return f"Duration(type={self.type}, interval={self.interval})"

    class Decomposition:
        def __init__(self, repetition: int, interval: int, actions: list):
            self.repetition = repetition
            self.interval = interval
            self.actions = actions

        def __repr__(self):
            return (
                f"Decomposition(repetition={self.repetition}, "
                f"interval={self.interval}, actions={self.actions})"
            )

    class RoI:
        def __init__(self, room, asset, objects) -> None:
            self.room = room
            self.asset = asset
            self.objects = objects

        def __repr__(self) -> str:
            return f"RoI(room={self.room}, asset={self.asset}, objects={self.objects})"

    def __init__(
        self,
        name: str,
        type: str,
        roi: RoI,
        duration: Duration,
        decomposition: Decomposition,
    ):
        self.name = name
        self.type = type
        self.roi = roi
        self.duration = duration
        self.decomposition = decomposition

    def __repr__(self):
        return f"Subtask({self.name} (duration={self.duration}))"


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
                room=subtask_data["Room"],
                asset=subtask_data["Asset"],
                objects=subtask_data["Objects"],
            )
            duration = Subtask.Duration(
                duration_type=subtask_data["Duration"]["Type"],
                interval=subtask_data["Duration"]["Interval"],
            )
            decomposition = Subtask.Decomposition(
                repetition=subtask_data["Decomposition"]["Repetition"],
                interval=subtask_data["Decomposition"]["Interval"],
                actions=subtask_data["Decomposition"]["Actions"],
            )
            subtask = Subtask(
                name=subtask_name,
                type=subtask_type,
                roi=roi,
                duration=duration,
                decomposition=decomposition,
            )
            subtasks.append(subtask)

        tasks.append(Task(name=task_name, subtasks=subtasks))

    return tasks


def parse_constraints(data: List[Dict]) -> nx.DiGraph:
    G = nx.DiGraph()

    # Add all subtask nodes to the graph
    for task in data:
        for subtask in task["Subtasks"]:
            subtask_node = subtask["Subtask"]
            subtask_type = subtask["Type"]
            G.add_node(subtask_node, subtask_type=subtask_type)

    # Add edges based on temporal constraints
    for task in data:
        for subtask in task["Subtasks"]:
            main_subtask = subtask["Subtask"]
            temporal_constraints = subtask.get("TemporalConstraints", [])

            for temporal_constraint in temporal_constraints:
                precedence_subtask = temporal_constraint["Subtask"]
                if precedence_subtask:
                    edge_data = {
                        "info": {
                            "Type": temporal_constraint["Type"],
                            "Interval": temporal_constraint["Interval"],
                            "Urgency": temporal_constraint["Urgency"],
                        }
                    }
                    if temporal_constraint["Type"] == "Before":
                        G.add_edge(main_subtask, precedence_subtask, **edge_data)
                    elif temporal_constraint["Type"] == "After":
                        G.add_edge(precedence_subtask, main_subtask, **edge_data)

    return G
