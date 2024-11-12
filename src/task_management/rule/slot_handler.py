from typing import Callable, List, Tuple

from anytree import Node

from archive.task import Subtask


class SlotHandler:
    def __init__(self, constraint_handler, process_subtask_callback: Callable):
        self.constraint_handler = constraint_handler
        self.process_subtask_callback = process_subtask_callback

    def handle_time_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        remaining_subtasks: List[Subtask],
        time_slot: int,
    ) -> Tuple[Node, int, List[Subtask]]:

        available_subtasks = self.constraint_handler.get_expandable_subtasks(
            parent_node, remaining_subtasks
        )

        time_spent = 0

        for available_subtask in available_subtasks:
            if available_subtask.duration.interval <= time_slot - time_spent:
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )
                time_spent += available_subtask.duration.interval
                remaining_subtasks.remove(available_subtask)

                if time_spent >= time_slot:
                    break

        return parent_node, time_slot - time_spent, remaining_subtasks

    def compress_time_slots(self, parent_node: Node, subtask: Subtask):
        time_slots_urgencies = self.constraint_handler._get_time_slot_and_urgency(
            parent_node, subtask
        )

        fill_time_slot_urgencies = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if urgency and time_slot > 0
        ]

        fill_time_slot_not_urgencies = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if not urgency and time_slot > 0
        ]

        expandable_slot = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if (urgency and time_slot == 0) or (not urgency and time_slot <= 0)
        ]

        if len(fill_time_slot_urgencies) > 1:
            if len(set(fill_time_slot_urgencies)) == 1:
                return fill_time_slot_urgencies[0]
            else:
                return None, None

        elif fill_time_slot_urgencies and fill_time_slot_not_urgencies:
            urgency_true_slot = fill_time_slot_urgencies[0][0]
            max_not_urgent_slot = max(
                time_slot for time_slot, _ in fill_time_slot_not_urgencies
            )
            if urgency_true_slot > max_not_urgent_slot:
                return fill_time_slot_urgencies[0]
            else:
                return None, None

        elif fill_time_slot_urgencies:
            return fill_time_slot_urgencies[0]
        elif fill_time_slot_not_urgencies:
            return max(fill_time_slot_not_urgencies)

        elif expandable_slot:
            return expandable_slot[0]

        return None, None
