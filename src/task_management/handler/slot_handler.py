from typing import Callable, List, Tuple

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
    ) -> Tuple[Node, int]:
        """
        Handles the scheduling of a subtask based on available time slots and urgency.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to be scheduled.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            Tuple[Node, int]: Updated node and makespan after processing the time slots.
        """

        # Process based on time slot urgencies
        time_slot_urgencies = self.constraint_handler.get_time_slot_and_urgency(
            parent_node, subtask
        )
        for time_slot, is_urgent in time_slot_urgencies:
            if is_urgent and time_slot < 0:
                pass
            else:
                # Monitoring 시작 시간을 저장할 변수
                temp_parent_node = parent_node
                temp_makespan = makespan

                # Monitoring을 작업 배치 이후 makespan
                parent_node, makespan, remaining_subtasks = self._execute_quick_tasks(
                    parent_node, subtask, makespan, remaining_subtasks, time_slot
                )

                # Monitoring Duration 만큼, 작업 배치 할 것
                if subtask.type == "Monitoring":
                    parent_node, makespan, remaining_subtasks = (
                        self._execute_parallel_tasks(
                            temp_parent_node, subtask, temp_makespan, remaining_subtasks
                        )
                    )

        return parent_node, makespan

    def _execute_parallel_tasks(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
    ) -> Tuple[Node, int, List[Subtask]]:
        """
        Schedules interaction subtasks to run in parallel with a monitoring subtask.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The monitoring subtask being processed.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            Tuple[Node, int, List[Subtask]]: Updated node, makespan, and remaining subtasks.
        """
        # Retrieve eligible subtasks that can run in parallel
        available_subtasks = self._get_eligible_subtasks(
            parent_node, remaining_subtasks
        )
        time_slot = subtask.duration.interval
        time_spent = 0

        # Process each eligible interaction subtask
        for available_subtask in available_subtasks:
            # Check if the subtask can fit within the remaining time slot
            if (
                available_subtask.type == "Interaction"
                and available_subtask.duration.interval <= time_slot - time_spent
            ):
                # Process the interaction subtask
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )

                # Update the time spent and remove the subtask from the list
                time_spent += available_subtask.duration.interval
                remaining_subtasks.remove(available_subtask)

                # Break if the time slot is filled
                if time_spent >= time_slot:
                    break

        # If there is remaining time, add a wait node
        if time_spent < time_slot:
            wait_time = time_slot - time_spent
            wait_node = Node(
                name=f"Wait_for_{subtask.name}",
                parent=parent_node,
                makespan=makespan + wait_time,
                location=parent_node.location,
            )
            parent_node = wait_node
            makespan += wait_time

        return parent_node, makespan, remaining_subtasks

    def _execute_quick_tasks(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
        time_slot: int,
    ) -> Tuple[Node, int]:
        """
        Executes quick tasks that can fit within the given time slot.

        Args:
            parent_node (Node): The parent node in the task tree.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.
            time_slot (int): The available time slot duration.

        Returns:
            Tuple[Node, int]: Updated node and makespan after executing quick tasks.
        """
        # Get eligible subtasks based on constraints
        available_subtasks = self._get_eligible_subtasks(
            parent_node, remaining_subtasks
        )

        time_spent = 0

        # Process each available subtask
        for available_subtask in available_subtasks:
            # Check if the available subtask can fit within the time slot
            if available_subtask.duration.interval <= time_slot - time_spent:
                # Process the subtask if it fits within the remaining time slot
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )

                time_spent += available_subtask.duration.interval
                remaining_subtasks.remove(available_subtask)

                # Break if the time slot is filled
                if time_spent >= time_slot:
                    break

        if time_spent < time_slot:
            # Wait for the remaining time if not all time slots are used
            wait_time = time_slot - time_spent
            parent_node = Node(
                name=f"Wait_for_{subtask.name}",
                parent=parent_node,
                makespan=makespan + wait_time,
                location=parent_node.location,
            )
            makespan += wait_time

        return parent_node, makespan, remaining_subtasks

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
