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
        name: str,
        type: str,
        roi: RoI,
        duration: Duration,
        decomposition: Decomposition,
        temporal_constraints: Optional[List[TemporalConstraint]] = None,
    ):
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
                asset=subtask_data["TaskScene"]["Asset"],
                objects=subtask_data["TaskScene"]["Objects"],
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
                precedence_subtask = constraint.subtask
                if precedence_subtask:
                    edge_data = {
                        "info": {
                            "Type": constraint.type,
                            "Interval": constraint.interval,
                            "Urgency": constraint.urgency,
                        }
                    }
                    if constraint.type == "Before":
                        G.add_edge(subtask_node, precedence_subtask, **edge_data)
                    elif constraint.type == "After":
                        G.add_edge(precedence_subtask, subtask_node, **edge_data)

    return G
