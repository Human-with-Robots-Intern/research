
"""This module provides a class to handle ROS communication for executing subtasks."""

import time
from typing import Any, List, Optional, Tuple, Dict

from src.models.dataclass import CompletedEntry
from src.models.task import Subtask
from src.utils.common.logger import create_module_logger

logger = create_module_logger(module_name=__name__, module_log=True)


class RosExecutor:
    """Handles execution of subtasks via ROS."""

    def __init__(self) -> None:
        """
        Initializes the RosExecutor.

        This involves setting up the instruction translator, object position simulator,
        and initializing the ROS communication.
        """
        from src.ros.ttp_ws.ttp_client.ttp_client.ros_communicate import init_ros_communication
        from src.ros.ttp_ws.ttp_client.ttp_client.simulate_object_pos_change import SimulateObjectPosChange
        from src.ros.ttp_ws.ttp_client.ttp_client.translate import InstructionTranslator

        self.translator = InstructionTranslator()
        self.object_pos_simulator = SimulateObjectPosChange()
        self.held_object: Optional[str] = None
        self.ros_start_time: Optional[float] = None
        self.total_ros_time: float = 0.0
        init_ros_communication()
        logger.info("ROS communication initialized.")

    def execute_primitive_actions(
        self, primitive_actions: List[str]
    ) -> Tuple[bool, float, List[Dict[str, Any]]]:
        """
        Executes a list of primitive actions via ROS and records timing.

        Args:
            primitive_actions: A list of primitive action strings to execute.

        Returns:
            A tuple containing:
            - bool: True if all actions succeed, False otherwise.
            - float: The total time elapsed for executing these actions.
            - List[Dict[str, Any]]: A log of each action and its execution time.
        """
        from src.ros.ttp_ws.ttp_client.ttp_client.ros_communicate import (
            communicate,
        )

        action_log: List[Dict[str, Any]] = []
        total_elapsed_time = 0.0

        for primitive_action in primitive_actions:
            action_start_time = time.time()

            primitive_action_parts = primitive_action.split(" ")
            action_verb = primitive_action_parts[0].lower()

            if action_verb == "wait":
                wait_duration = float(primitive_action_parts[1])
                time.sleep(wait_duration)
                success = True
            else:
                translated_action = self.translator.translate(primitive_action)
                success = communicate(translated_action)

            action_end_time = time.time()
            elapsed_time = action_end_time - action_start_time
            total_elapsed_time += elapsed_time
            action_log.append(
                {"action": primitive_action, "duration": elapsed_time}
            )

            if not success:
                logger.error(f"Action '{primitive_action}' failed. Stopping task.")
                return False, total_elapsed_time, action_log

            # Simulate object state changes
            if action_verb == "grasp":
                self.object_pos_simulator._simulate_grasp(primitive_action_parts[1].lower())
                self.held_object = primitive_action_parts[1]
                logger.info(f"Held object: {self.held_object}")
            elif action_verb.startswith("place"):
                self.object_pos_simulator._simulate_place(primitive_action_parts[1].lower())
                if self.held_object:
                    logger.info(
                        f"Object '{self.held_object}' position: "
                        f"{self.object_pos_simulator._get_object_pos(self.held_object.lower())}"
                    )
                self.held_object = None
        
        return True, total_elapsed_time, action_log

    def execute_subtask(self, subtask: Subtask) -> Tuple[bool, float, List[Dict[str, Any]]]:
        """
        Executes the primitive actions of a single subtask.

        Args:
            subtask: The subtask to execute.

        Returns:
            A tuple containing:
            - bool: True if execution is successful, False otherwise.
            - float: The total time elapsed for the subtask.
            - List[Dict[str, Any]]: A log of each action and its execution time.
        """
        if self.ros_start_time is None:
            self.ros_start_time = time.time()
            
        primitive_actions = subtask.execution.primitive_actions
        if not primitive_actions:
            return True, 0.0, []
        
        success, elapsed_time, action_logs = self.execute_primitive_actions(primitive_actions)
        self.total_ros_time += elapsed_time
        return success, elapsed_time, action_logs

    def execute_schedule(
        self, schedule: List[CompletedEntry]
    ) -> None:
        """
        Executes a pre-defined schedule of subtasks.

        This method iterates through a list of completed entries and executes
        the corresponding subtasks. It ensures that ROS communication is
        properly shut down afterwards.

        Args:
            schedule: A list of CompletedEntry objects representing the schedule.
        """
        try:
            for entry in schedule:
                ros_start_offset = self.total_ros_time
                success, elapsed_time, action_logs = self.execute_subtask(entry.subtask)
                
                entry.sim_start_time = ros_start_offset
                entry.sim_end_time = ros_start_offset + elapsed_time
                entry.execution_status = success
                # Storing detailed action logs in a new attribute
                entry.primitive_action_log = action_logs

                if not success:
                    break
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Shuts down the ROS communication."""
        from src.ros.ttp_ws.ttp_client.ttp_client.ros_communicate import (
            shutdown_ros_communication,
        )

        shutdown_ros_communication()
        logger.info("ROS communication shut down.") 