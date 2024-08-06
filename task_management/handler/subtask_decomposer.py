from typing import List

from concept.task import Subtask, Task


class SubtaskDecomposer:
    def __init__(self, batch_duration: int):
        self.batch_duration = batch_duration

    def decompose(self, task: Task) -> List[Subtask]:
        new_subtasks = []
        for subtask in task.subtasks:
            if subtask.decomposition.repetition > 1:
                batched_subtasks = self._decompose_interaction(subtask)
                new_subtasks.extend(batched_subtasks)
        return new_subtasks

    def _decompose_interaction(self, subtask: Subtask) -> List[Subtask]:
        """Subtask의 Repetition, Batch_duration을 고려하여 Task를 분할"""
        repetitions = subtask.decomposition.repetition
        intervals = subtask.decomposition.interval
        actions = subtask.decomposition.actions

        batched_subtasks = []
        current_repetition = 0
        batch_index = 1

        while current_repetition < repetitions:
            batch_repetitions = repetitions - current_repetition
            batch_name = f"{subtask.name}_{batch_index}"

            # Check if the batch is the first one for urgency constraint adjustment
            # urgency_constraint = False
            # for constraint in subtask.temporal_constraints:
            #     if constraint.urgency is False:
            #         urgency_constraint = True
            #         break

            # new_temporal_constraints = [
            #     Subtask.TemporalConstraint(
            #         constraint_type=constraint.type,
            #         subtask=constraint.subtask,
            #         interval=constraint.interval,
            #         urgency=(constraint.urgency if not urgency_constraint else True),
            #     )
            #     for constraint in subtask.temporal_constraints
            # ]

            batched_subtasks.append(
                Subtask(
                    name=batch_name,
                    type=subtask.type,
                    roi=subtask.roi,
                    duration=Subtask.Duration(
                        duration_type=subtask.duration.type,
                        interval=intervals * batch_repetitions,
                    ),
                    decomposition=Subtask.Decomposition(
                        repetition=1,
                        interval=intervals,
                        actions=actions,
                    ),
                    temporal_constraints=new_temporal_constraints,
                )
            )

            current_repetition += batch_repetitions
            batch_index += 1

        return batched_subtasks
