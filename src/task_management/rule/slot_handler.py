from __future__ import annotations

from logging import log
from typing import Callable, List, Tuple

from anytree import Node

from core import Subtask


class SlotHandler:
    def __init__(self, process_subtask_callback: Callable):
        self.process_subtask_callback = process_subtask_callback

    def handle_time_slots(
        self,
        parent_node: Node,
        remaining_subtasks: List[Subtask],
        time_slot: int,
        get_expandable_subtasks: Callable[[Node, List[Subtask]], List[Subtask]],
    ) -> Tuple[Node, int, List[Subtask]]:
        pass

    def compress_time_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        get_time_slot_and_urgency: Callable[[Node, Subtask], List[Tuple[int, bool]]],
    ) -> Tuple[int, bool]:
        """
        select the time slot and urgency of the subtask among the available time slots.

        Args:
            parent_node (Node): Parent node to expand from.
            subtask (Subtask): Child subtask to process.
            get_time_slot_and_urgency (Callable[[Node, Subtask], List[Tuple[int, bool]]]):
                Function to get time slot and urgency of the subtask.

        Returns:
            Tuple[int, bool]: Time slot and urgency of the subtask.
        """
        time_slots_urgencies = get_time_slot_and_urgency(parent_node, subtask)

        urgent_time_slots = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if urgency and time_slot > 0
        ]

        non_urgent_time_slots = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if not urgency and time_slot > 0
        ]

        expandable_slots = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if (urgency and time_slot == 0) or (not urgency and time_slot <= 0)
        ]

        if len(urgent_time_slots) > 1:
            if len(set(urgent_time_slots)) == 1:
                return urgent_time_slots[0]
            else:
                return None, None

        elif urgent_time_slots and non_urgent_time_slots:
            first_urgent_time_slot = urgent_time_slots[0][0]
            max_non_urgent_time_slot = max(
                time_slot for time_slot, _ in non_urgent_time_slots
            )
            if first_urgent_time_slot > max_non_urgent_time_slot:
                return urgent_time_slots[0]
            else:
                return None, None

        elif urgent_time_slots:
            return urgent_time_slots[0]
        elif non_urgent_time_slots:
            return max(non_urgent_time_slots)

        elif expandable_slots:
            return expandable_slots[0]

        return None, None
