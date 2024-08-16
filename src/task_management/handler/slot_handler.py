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
        time_slot: int,
    ) -> Tuple[Node, int, List[Subtask]]:
        """
        Handles the scheduling of an interaction subtask based on available time slots.

        Args:
            parent_node (Node): The parent node in the task tree.
            subtask (Subtask): The subtask to be scheduled.
            makespan (int): The current makespan.
            remaining_subtasks (List[Subtask]): List of remaining subtasks to be processed.

        Returns:
            Tuple[Node, int, List[Subtask]]: Updated node, makespan, and remaining subtasks after processing the time slots.
        """

        available_subtasks = self.constraint_handler.get_expandable_subtasks(
            parent_node, remaining_subtasks
        )

        # if remaining_subtasks != available_subtasks:
        #     print(
        #         f"available_subtasks : {[available_subtask.name for available_subtask in available_subtasks]}"
        #     )

        time_spent = 0

        # Process each available subtask
        for available_subtask in available_subtasks:
            # Check if the available subtask can fit within the time slot
            if (
                available_subtask.duration.interval
                + parent_node.makespan
                - parent_node.parent.makespan
                <= time_slot - time_spent
            ):
                # Process the subtask if it fits within the remaining time slot
                self.process_subtask_callback(
                    parent_node, available_subtask, remaining_subtasks
                )

                time_spent += available_subtask.duration.interval + parent_node.makespan
                -parent_node.parent.makespan
                remaining_subtasks.remove(available_subtask)

                # Break if the time slot is filled
                if time_spent >= time_slot:
                    break

        return time_slot - time_spent

    def handle_monitoring_slots(
        self,
        parent_node: Node,
        subtask: Subtask,
        makespan: int,
        remaining_subtasks: List[Subtask],
    ) -> Tuple[Node, int]:

        # 모니터링 슬롯 길이
        monitoring_slot = subtask.duration.interval

        # makespan은 모니터링 끝난 시간을 의미
        makespan += monitoring_slot
        parent_node = Node(
            subtask.name,
            parent=parent_node,
            makespan=makespan,
            location=f"{subtask.roi.room}:{subtask.roi.asset}",
            type="Monitoring",
        )

        # content task 소모 시간
        time_spent = 0

        interaction_subtasks = [
            s
            for s in self.constraint_handler.get_expandable_subtasks(
                parent_node, remaining_subtasks
            )
            if s.type == "Interaction"
        ]

        # Schedule interaction subtasks during the monitoring period
        for interaction_subtask in interaction_subtasks:
            if (
                interaction_subtask.duration.interval
                + parent_node.parent.makespan
                - parent_node.parent.parent.makespan
                <= monitoring_slot - time_spent
            ):
                # Use the callback to process the subtask
                self.process_subtask_callback(
                    parent_node, interaction_subtask, remaining_subtasks
                )
                time_spent += (
                    interaction_subtask.duration.interval
                    + parent_node.parent.makespan
                    - parent_node.parent.parent.makespan
                )

                remaining_subtasks.remove(interaction_subtask)

                if time_spent >= monitoring_slot:
                    break

        return monitoring_slot - time_spent

    def compress_time_slots(self, parent_node: Node, subtask: Subtask):
        time_slots_urgencies = self.constraint_handler.get_time_slot_and_urgency(
            parent_node, subtask
        )

        # Time slots with urgency = True and time_slot > 0
        fill_time_slot_urgencies = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if urgency and time_slot > 0
        ]

        # Time slots with urgency = False and time_slot > 0
        fill_time_slot_not_urgencies = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if not urgency and time_slot > 0
        ]

        # Time slots that are either (urgency=True and time_slot==0) or (urgency=False and time_slot<=0)
        expandable_slot = [
            (time_slot, urgency)
            for time_slot, urgency in time_slots_urgencies
            if (urgency and time_slot == 0) or (not urgency and time_slot <= 0)
        ]

        # Handle multiple fill_time_slot_urgencies
        if len(fill_time_slot_urgencies) > 1:
            if len(set(fill_time_slot_urgencies)) == 1:
                # All time slots are the same, return any
                return fill_time_slot_urgencies[0]
            else:
                # Different time slots with urgency True, prune by returning None
                return None, None

        # Handle a mix of urgency True and False
        elif fill_time_slot_urgencies and fill_time_slot_not_urgencies:
            urgency_true_slot = fill_time_slot_urgencies[0][0]
            max_not_urgent_slot = max(
                time_slot for time_slot, _ in fill_time_slot_not_urgencies
            )
            if urgency_true_slot > max_not_urgent_slot:
                return fill_time_slot_urgencies[0]
            else:
                # Prune the True urgency slot, return None
                return None, None

        # Handle single urgency True or False
        elif fill_time_slot_urgencies:
            return fill_time_slot_urgencies[0]
        elif fill_time_slot_not_urgencies:
            return max(fill_time_slot_not_urgencies)

        # If no valid time slots, consider expandable slots
        elif expandable_slot:
            # Returning the first expandable slot found (since urgency=False and time_slot<=0)
            return expandable_slot[0]

        # If all else fails, return None to indicate pruning
        return None, None
