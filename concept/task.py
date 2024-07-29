from typing import Dict, List, Tuple

import networkx as nx


class Subtask:
    def __init__(
        self,
        task_name: str,
        task_location: str,
        name: str,
        subtask_type: str,
        duration: int,
    ):
        """
        Subtask constructor

        Args:
            task_name (str): The name of the main task
            task_location (str): The location of the task
            name (str): The name of the subtask
            subtask_type (str): Type of the subtask (Interaction / Monitoring)
            duration (int): Time cost to complete the subtask
        """
        self.task_name = task_name
        self.location = task_location
        self.name = name
        self.type = subtask_type
        self.duration = duration

    def __repr__(self):
        return f"Subtask({self.name} (duration={self.duration}))"


class Task:
    def __init__(self, name: str, location: str, subtasks: List[Tuple[str, str, int]]):
        """
        Task constructor

        Args:
            name (str): Task name
            location (str): Task location (Kitchen, Living Room, Restroom, Bedroom)
            subtasks (list[tuple]): List of subtasks (name, type, duration)
        """
        self.name = name
        self.location = location
        self.subtasks = [Subtask(name, location, *subtask) for subtask in subtasks]

    def __repr__(self):
        return f"Task(name={self.name}, location={self.location}, subtasks={self.subtasks})"

    def get_total_seq_duration(self) -> int:
        return sum(subtask.duration for subtask in self.subtasks)


def get_all_subtasks(tasks: List[Task]) -> List[Subtask]:
    return [subtask for task in tasks for subtask in task.subtasks]


def parse_tasks(data: List[Dict]) -> List[Task]:
    tasks = []
    for task in data:
        task_name = task["Task"]
        location = task["Location"]
        subtasks = [
            (sub["Subtask"], sub["Type"], sub["Duration"]["Interval"])
            for sub in task["Subtasks"]
        ]
        tasks.append(Task(task_name, location, subtasks))
    return tasks


def parse_constraints(data: List[Dict]) -> nx.DiGraph:
    G = nx.DiGraph()

    # Add all subtask nodes to the graph
    for task in data:
        for subtask in task["Subtasks"]:
            subtask_node = subtask["Subtask"]
            G.add_node(subtask_node)

    # Add edges based on temporal constraints
    for task in data:
        for subtask in task["Subtasks"]:
            main_subtask = subtask["Subtask"]
            temporal_constraints = subtask.get("TemporalConstraints", [])

            for temporal_constraint in temporal_constraints:
                condition_subtask = temporal_constraint["Subtask"]
                edge_data = {
                    "info": {
                        "Type": temporal_constraint["Type"],
                        "Interval": temporal_constraint["Interval"],
                        "Urgency": temporal_constraint["Urgency"],
                    }
                }
                G.add_edge(main_subtask, condition_subtask, **edge_data)

    return G
