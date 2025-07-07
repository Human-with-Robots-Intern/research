from __future__ import annotations

import sys
from typing import List

import rclpy
from rclpy.node import Node
from robot_manager_interface.srv import RobotManager
from ttp_client.translate import InstructionTranslator

_ros_client_node: RobotManagerClient | None = None


class RobotManagerClient(Node):
    """A client node to communicate with the RobotManager service."""

    def __init__(self) -> None:
        """Initialize the RobotManagerClient node."""
        super().__init__("robot_manager_client")
        self.cli = self.create_client(RobotManager, "/robot_command")
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Service not available, waiting again...")

    def send_request(
        self, robot_model: int, instruction: str, a: str, b: str
    ) -> rclpy.task.Future:
        """
        Send a request to the RobotManager service.

        Args:
            robot_model: The model of the robot.
            instruction: The instruction to be executed.
            a: The first parameter for the instruction.
            b: The second parameter for the instruction.

        Returns:
            A future that completes when the service call is done.
        """
        req_temp = RobotManager.Request()
        req_temp.robot_model = robot_model
        req_temp.instruction = instruction
        req_temp.a = a
        req_temp.b = b
        return self.cli.call_async(req_temp)


def init_ros_communication(args: list[int] | None = None) -> None:
    """
    Initialize the ROS communication client.

    This function should be called once before any communication calls.

    Args:
        args: Command line arguments for rclpy initialization.
    """
    global _ros_client_node
    if _ros_client_node is None:
        rclpy.init(args=args)
        _ros_client_node = RobotManagerClient()
        _ros_client_node.get_logger().info("ROS communication initialized.")


def shutdown_ros_communication() -> None:
    """
    Shut down the ROS communication client.

    This function should be called once after all communication is finished.
    """
    global _ros_client_node
    if _ros_client_node is not None:
        _ros_client_node.get_logger().info("Shutting down ROS communication.")
        _ros_client_node.destroy_node()
        rclpy.shutdown()
        _ros_client_node = None


def communicate(action_parts: List[int]) -> bool:
    """
    Send a single primitive action to the robot and wait for a response.

    Args:
        action_parts: A list containing the parts of a translated action,
                    e.g., ['PICK_UP', 'Cup', ''].

    Returns:
        True if the action was successful, False otherwise.
    """
    global _ros_client_node
    if _ros_client_node is None:
        rclpy.logging.get_logger("ros_communicate").error(
            "ROS communication not initialized. Call init_ros_communication() first."
        )
        return False

    if not isinstance(action_parts, list) or not action_parts:
        _ros_client_node.get_logger().error(f"Invalid action_parts received: {action_parts}")
        return False

    robot_model = action_parts[0]
    instruction = action_parts[1]
    a = action_parts[2] 
    b = action_parts[3]

    action_str = f"{instruction} {a} {b}".strip()
    _ros_client_node.get_logger().info(f"Sending action: '{action_str}'")

    future = _ros_client_node.send_request(robot_model, instruction, a, b)
    rclpy.spin_until_future_complete(_ros_client_node, future)

    try:
        response = future.result()
        if response.success:
            _ros_client_node.get_logger().info(f"Action '{action_str}' succeeded.")
            return True
        else:
            _ros_client_node.get_logger().error(
                f"Action '{action_str}' failed on robot side."
            )
            return False
    except Exception as e:
        _ros_client_node.get_logger().error(
            f"Service call for action '{action_str}' failed with exception: {e!r}"
        )
        return False


def main(args: list[str] | None = None) -> None:
    """Main function to run a test communication."""
    translator = InstructionTranslator()
    try:
        init_ros_communication(args=args)
        test_actions = [
            "NAVIGATE_TO banana", 
            "GRASP banana",
            "NAVIGATE_TO cooker",
            "PLACE_INSIDE cooker",
            "NAVIGATE_TO banana",
            "GRASP banana"
        ]
        for test_action in test_actions:
            translated_primitive_action = translator.translate(
            instruction=test_action
        )
            success = communicate(translated_primitive_action)
            print(f"Test action success: {success}")

    finally:
        shutdown_ros_communication()


if __name__ == "__main__":
    main()