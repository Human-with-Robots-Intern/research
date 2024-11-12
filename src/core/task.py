from typing import Dict, List, Optional

import networkx as nx
import numpy as np

# class Decomposition:
#     def __init__(self, repetition: int, actions: List[str]):
#         self.repetition = repetition
#         self.actions = actions

#     def __repr__(self):
#         return f"Decomposition(repetition={self.repetition}, actions={self.actions})"

#     @classmethod
#     def from_dict(cls, data: Dict) -> "Decomposition":
#         return cls(
#             repetition=data["Repetition"],
#             actions=data["Actions"],
#         )


# class RoI:
#     def __init__(self, room: str, asset: List[str], objects: Dict[str, int]) -> None:
#         self.room = room
#         self.asset = asset
#         self.objects = objects

#     def __repr__(self) -> str:
#         return f"RoI(room={self.room}, asset={self.asset}, objects={self.objects})"


#     @classmethod
#     def from_dict(cls, data: Dict) -> "RoI":
#         return cls(
#             room=data["Room"],
#             asset=data["Assets"],
#             objects=data["Objects"],
#         )


class Duration:
    def __init__(self, duration_type: str, interval: int):
        self.type = duration_type
        self.interval = interval

    def __repr__(self):
        return f"Duration(type={self.type}, interval={self.interval})"

    @classmethod
    def from_dict(cls, data: Dict) -> "Duration":
        return cls(
            duration_type=data["Type"],
            interval=data["Interval"],
        )


class Execution:
    def __init__(self, objects: Dict[str, int], primitive_actions: List[str]):
        self.objects = objects
        self.primitive_actions = primitive_actions

    def __repr__(self):
        return f"Execution(objects={self.objects}, primitive_actions={self.primitive_actions})"

    @classmethod
    def from_dict(cls, data: Dict) -> "Execution":
        return cls(
            objects=data["Objects"],
            primitive_actions=data["PrimitiveActions"],
        )


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

    @classmethod
    def from_dict(cls, data: Dict) -> "TemporalConstraint":
        return cls(
            constraint_type=data["Type"],
            subtask=data["Subtask"],
            interval=data["Interval"],
            urgency=data["Urgency"],
        )


class Subtask:
    def __init__(
        self,
        task_name: str,
        name: str,
        repetition: int,
        type: str,
        execution: Execution,
        duration: Duration,
        temporal_constraints: Optional[List[TemporalConstraint]] = None,
    ):
        self.task_name = task_name
        self.name = name
        self.repetition = repetition
        self.type = type
        self.execution = execution
        self.duration = duration
        self.temporal_constraints = temporal_constraints or []

    def __repr__(self):
        return f"Subtask({self.name}, duration={self.duration}, constraints={self.temporal_constraints})"

    @classmethod
    def from_dict(cls, subtask_data: Dict, task_name: str) -> "Subtask":
        """Create a Subtask object from a dictionary.

        Args:
            subtask_data (Dict): dictionary containing subtask data
            task_name (str): task which include the subtask

        Returns:
            Subtask: Subtask object created from the dictionary
        """
        execution = Execution.from_dict(subtask_data["Executions"])
        duration = Duration.from_dict(subtask_data["Duration"])
        repetition = subtask_data.get("Repetition", 1)

        temporal_constraints_data = subtask_data.get("TemporalConstraints", [])
        temporal_constraints = [
            TemporalConstraint.from_dict(tc) for tc in temporal_constraints_data
        ]

        return cls(
            task_name=task_name,
            name=subtask_data["Subtask"],
            repetition=repetition,
            type=subtask_data["Type"],
            duration=duration,
            execution=execution,
            temporal_constraints=temporal_constraints,
        )

    def decompose(self) -> List["Subtask"]:
        """Decompose a subtask into multiple subtasks when repetition larger than 1."""
        if self.repetition > 1:
            return self._decompose_subtask()
        else:
            return [self]

    def _decompose_subtask(self) -> List["Subtask"]:
        """Implementation of Subtask Decomposition."""
        decomposed_subtasks = []
        # 실제 decomposed subtask 생성
        for part_index in range(self.repetition):
            decomposed_subtask = Subtask(
                task_name=self.task_name,
                name=f"{self.name}_part_{part_index + 1}",
                type=self.type,
                repetition=1,
                duration=Duration(
                    duration_type=self.duration.type,
                    interval=self.duration.interval,
                ),
                execution=self.execution,
                temporal_constraints=self._get_temporal_constraints(part_index),
            )
            decomposed_subtasks.append(decomposed_subtask)

        return decomposed_subtasks

    def _get_temporal_constraints(self, part_index: int) -> List[TemporalConstraint]:
        if part_index == 0:
            return self.temporal_constraints
        else:
            return [
                TemporalConstraint(
                    constraint_type="After",
                    subtask=f"{self.name}_part_{part_index}",
                    interval=0,
                    urgency=False,
                )
            ]


class Task:
    def __init__(self, name: str, subtasks: List[Subtask]):
        self.name = name
        self.subtasks = subtasks

    def __repr__(self):
        return f"Task(name={self.name}, subtasks={self.subtasks})"

    def get_total_seq_duration(self) -> int:
        return sum(subtask.duration.interval for subtask in self.subtasks)

    @classmethod
    def from_dict(cls, task_data: Dict) -> "Task":
        task_name = task_data["Task"]
        subtasks = [
            Subtask.from_dict(subtask_data, task_name)
            for subtask_data in task_data["Subtasks"]
        ]
        return cls(name=task_name, subtasks=subtasks)

    @classmethod
    def parse_instruction(cls, data: List[Dict]) -> List["Task"]:
        return [cls.from_dict(task_data) for task_data in data]

    # def decompose_subtasks(self):
    #     decomposed_subtasks = []
    #     subtask_mapping = {}

    #     for subtask in self.subtasks:
    #         decomposed_parts = subtask.decompose()
    #         decomposed_subtasks.extend(decomposed_parts)
    #         subtask_mapping[subtask.name] = decomposed_parts

    #     self.subtasks = decomposed_subtasks

    #     self.update_constraints(subtask_mapping)

    # def update_constraints(self, subtask_mapping: Dict[str, List[Subtask]]):
    #     for subtask in self.subtasks:
    #         updated_constraints = []
    #         for constraint in subtask.temporal_constraints:
    #             if constraint.subtask in subtask_mapping:
    #                 last_decomposed_part = subtask_mapping[constraint.subtask][-1]
    #                 updated_constraints.append(
    #                     TemporalConstraint(
    #                         constraint_type=constraint.type,
    #                         subtask=last_decomposed_part.name,
    #                         interval=constraint.interval,
    #                         urgency=constraint.urgency,
    #                     )
    #                 )
    #             else:
    #                 updated_constraints.append(constraint)
    #         subtask.temporal_constraints = updated_constraints
    # @staticmethod
    # def get_all_subtasks(tasks: List["Task"]) -> List[Subtask]:
    #     return [subtask for task in tasks for subtask in task.subtasks]


class TaskGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def build_graph(self, tasks: List[Task]):
        for task in tasks:
            for subtask in task.subtasks:
                subtask_node = subtask.name
                subtask_type = subtask.type
                self.graph.add_node(subtask_node, subtask_type=subtask_type)

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
                            self.graph.add_edge(
                                subtask_node, constraint.subtask, **edge_data
                            )
                        elif constraint.type == "After":
                            self.graph.add_edge(
                                constraint.subtask, subtask_node, **edge_data
                            )
                    else:
                        raise ValueError("Constrained Node does not exist")

    def get_graph(self) -> nx.DiGraph:
        return self.graph


class ScheduledTask:
    def __init__(self, name, start, end, duration, subtask=None):
        self.name = name
        self.start = start
        self.end = end
        self.duration = duration
        self.subtask = subtask

    def __repr__(self):
        return (
            f"ScheduledTask(name={self.name}, "
            f"subtask={self.subtask}, start={self.start}, end={self.end}, duration={self.duration})"
        )
