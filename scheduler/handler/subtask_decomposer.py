# task_decomposer.py
from typing import List

from concept.task import Subtask


class TaskDecomposer:
    def decompose_task(self, subtask: Subtask, duration: int) -> List[Subtask]:
        """
        Decompose a subtask into two smaller subtasks.

        Parameters:
        - subtask: The original subtask to be decomposed.
        - duration: The duration of the first part of the decomposed subtask.

        Returns:
        - A list of two smaller subtasks.
        """
        if subtask.duration <= duration:
            return [subtask]

        first_part = Subtask(
            name=f"{subtask.name}_part_1",
            type=subtask.type,
            duration=duration,
            location=subtask.location,
            temporal_constraints=subtask.temporal_constraints,
            precondition=subtask.precondition,
            effect=subtask.effect,
        )

        second_part = Subtask(
            name=f"{subtask.name}_part_2",
            type=subtask.type,
            duration=subtask.duration - duration,
            location=subtask.location,
            temporal_constraints=subtask.temporal_constraints,
            precondition=subtask.precondition,
            effect=subtask.effect,
        )

        return [first_part, second_part]
