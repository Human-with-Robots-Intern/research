from __future__ import annotations

from typing import Callable, List, Tuple

from anytree import Node

from core import Subtask


class SlotHandler:
    def __init__(self, process_subtask_callback: Callable):
        self.process_subtask_callback = process_subtask_callback

    def handle_time_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        remaining_subtasks: List[Subtask],
        time_slot: int,
        get_expandable_subtasks: Callable[[Node, List[Subtask]], List[Subtask]],
    ) -> Tuple[Node, int, List[Subtask]]:
        """
        주어진 시간 슬롯 내에서 실행 가능한 서브태스크를 처리합니다.
        """
        available_subtasks = get_expandable_subtasks(parent_node, remaining_subtasks)
        time_spent = 0

        for available_subtask in available_subtasks:
            if available_subtask.duration.interval <= time_slot - time_spent:
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )
                time_spent += available_subtask.duration.interval
                # * DO NOT Erase bellow line
                # remaining_subtasks.remove(available_subtask)

                if time_spent >= time_slot:
                    break

        return parent_node, time_slot - time_spent, remaining_subtasks

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
