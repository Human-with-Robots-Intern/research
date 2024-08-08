from typing import Dict, List

from concept.task import Subtask, Task


class SubtaskDecomposer:
    def __init__(self, subtask: Subtask):
        self.subtask = subtask

    def decompose(self) -> List[Subtask]:
        if self.subtask.decomposition.repetition > 1:
            return self._decompose_subtask()
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
            interval=self.subtask.decomposition.interval,
        )
        decomposed_decomposition = Subtask.Decomposition(
            repetition=1,
            interval=self.subtask.decomposition.interval,
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

    for task in tasks:
        decomposed_subtasks = []
        for subtask in task.subtasks:
            decomposer = SubtaskDecomposer(subtask)
            decomposed_subtasks.extend(decomposer.decompose())

        decomposed_tasks.append(Task(name=task.name, subtasks=decomposed_subtasks))

    return decomposed_tasks
