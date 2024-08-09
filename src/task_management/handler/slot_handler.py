from typing import Callable, List

from anytree import Node

from concept.task import Subtask


class SlotHandler:
    def __init__(self, constraint_handler, process_subtask_callback: Callable):
        self.constraint_handler = constraint_handler
        self.process_subtask_callback = process_subtask_callback

    def handle_time_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
    ) -> int:
        time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
            parent_node, subtask
        )

        for time_slot, is_urgent in time_slot_urgencies:
            if time_slot > 0:
                makespan = self._process_time_slot(
                    parent_node,
                    subtask,
                    makespan,
                    remaining_subtasks,
                    time_slot,
                    is_urgent,
                )

        return makespan

    def _process_time_slot(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
        time_slot: int,
        is_urgent: bool,
    ) -> int:
        if is_urgent:
            makespan = self._execute_quick_tasks(
                parent_node, makespan, remaining_subtasks, time_slot
            )
        else:
            makespan = self._wait_for_time_slot(
                parent_node, subtask, makespan, time_slot
            )

        return makespan

    def _execute_quick_tasks(
        self,
        parent_node: Node,
        makespan: int,
        remaining_subtasks: List[Subtask],
        time_slot: int,
    ) -> int:
        available_subtasks = self._get_eligible_subtasks(
            parent_node, remaining_subtasks
        )
        time_spent = 0
        last_processed_subtask = (
            None  # Keep track of the last processed subtask for waiting
        )

        for available_subtask in available_subtasks:
            if available_subtask.duration.interval <= time_slot - time_spent:
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )
                time_spent += available_subtask.duration.interval
                remaining_subtasks.remove(available_subtask)
                last_processed_subtask = (
                    available_subtask  # Update the last processed subtask
                )

                if time_spent >= time_slot:
                    break

        if time_spent < time_slot:
            wait_time = time_slot - time_spent
            # Ensure last_processed_subtask is defined before using it
            wait_subtask_name = (
                last_processed_subtask.name if last_processed_subtask else "Idle"
            )
            parent_node = Node(
                name=f"Wait_for_{wait_subtask_name}",
                parent=parent_node,
                makespan=makespan + wait_time,
                location=parent_node.location,
            )
            makespan += wait_time

        return makespan

    def _wait_for_time_slot(
        self, parent_node: Node, subtask: Subtask, makespan: int, time_slot: int
    ) -> int:
        Node(
            name=f"Wait_for_{subtask.name}",
            parent=parent_node,
            makespan=makespan + time_slot,
            location=parent_node.location,
        )
        return makespan + time_slot

    def _get_eligible_subtasks(
        self, parent_node: Node, remaining_subtasks: List[Subtask]
    ) -> List[Subtask]:
        return [
            subtask
            for subtask in remaining_subtasks
            if self.constraint_handler.validate_ordering_constraints(
                parent_node, subtask
            )
            and self.constraint_handler.validate_timing_constraints(
                self.constraint_handler.get_time_slot_and_urgency(parent_node, subtask)
            )
        ]
