from typing import Callable, List

from anytree import Node

from concept.task import Subtask


class SlotHandler:
    """
    Handles the scheduling and processing of subtasks based on timing constraints
    and available time slots.
    """

    def __init__(self, constraint_handler, process_subtask_callback: Callable):
        """
        Initializes the SlotHandler with a constraint handler and a callback for processing subtasks.

        Args:
            constraint_handler: An object that manages constraints related to task scheduling.
            process_subtask_callback: A callable to execute when a subtask is processed.
        """
        self.constraint_handler = constraint_handler
        self.process_subtask_callback = process_subtask_callback

    def handle_time_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
    ) -> int:
        """
        Handles the scheduling of a subtask based on available time slots and urgency.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to be scheduled.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            int: Updated makespan after processing the time slots.
        """
        # Retrieve time slots and urgency for the subtask
        time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
            parent_node, subtask
        )

        # Process each time slot
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
        """
        Processes a specific time slot by either executing quick tasks or waiting.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to be scheduled.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.
            time_slot (int): The available time slot duration.
            is_urgent (bool): Indicates if the time slot is urgent.

        Returns:
            int: Updated makespan after processing the time slot.
        """
        if is_urgent:
            # Execute quick tasks if the time slot is urgent
            makespan = self._execute_quick_tasks(
                parent_node, makespan, remaining_subtasks, time_slot
            )
        else:
            # Wait for the time slot if it is not urgent
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
        """
        Executes quick tasks that can fit within the given time slot.

        Args:
            parent_node (Node): The parent node in the task tree.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.
            time_slot (int): The available time slot duration.

        Returns:
            int: Updated makespan after executing quick tasks.
        """
        # Get eligible subtasks based on constraints
        available_subtasks = self._get_eligible_subtasks(
            parent_node, remaining_subtasks
        )
        time_spent = 0
        last_processed_subtask = (
            None  # Keep track of the last processed subtask for waiting
        )

        # Process each available subtask
        for available_subtask in available_subtasks:
            if available_subtask.duration.interval <= time_slot - time_spent:
                # Process the subtask if it fits within the remaining time slot
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )
                time_spent += available_subtask.duration.interval
                remaining_subtasks.remove(available_subtask)
                last_processed_subtask = (
                    available_subtask  # Update the last processed subtask
                )

                # Break if the time slot is filled
                if time_spent >= time_slot:
                    break

        if time_spent < time_slot:
            # Wait for the remaining time if not all time slots are used
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
        """
        Waits for a specific time slot before proceeding with the next subtask.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to wait for.
            makespan (int): The current makespan.
            time_slot (int): The duration of the time slot to wait for.

        Returns:
            int: Updated makespan after waiting.
        """
        # Create a wait node for the specified time slot
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
        """
        Retrieves a list of subtasks that are eligible for execution based on constraints.

        Args:
            parent_node (Node): The parent node in the task tree.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            List[Subtask]: List of subtasks that meet the constraints and can be executed.
        """
        eligible_subtasks = []
        for subtask in remaining_subtasks:
            # Check ordering constraints
            if self.constraint_handler.validate_ordering_constraints(
                parent_node, subtask
            ):
                # Check timing constraints
                time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
                    parent_node, subtask
                )
                if self.constraint_handler.validate_timing_constraints(
                    time_slot_urgencies
                ):
                    eligible_subtasks.append(subtask)

        return eligible_subtasks
