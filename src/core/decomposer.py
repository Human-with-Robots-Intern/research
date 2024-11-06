from typing import Dict, List

from tasks.task import Subtask, Task


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
