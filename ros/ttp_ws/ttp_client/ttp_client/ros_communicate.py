from __future__ import annotations

import sys
import threading
import time
from typing import List

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from robot_manager_interface.srv import RobotManager


_ros_client_node: RobotManagerClient | None = None
_spin_thread: threading.Thread | None = None
_executor: MultiThreadedExecutor | None = None


class RobotManagerClient(Node):
    """A client node to communicate with the RobotManager service."""

    def __init__(self) -> None:
        """Initialize the RobotManagerClient node."""
        super().__init__("robot_manager_client")
        self.cli = self.create_client(RobotManager, "/robot_command")
        # while not self.cli.wait_for_service(timeout_sec=1.0):
        #     self.get_logger().info("Service not available, waiting again...")

    def send_request(
        self, robot_model: int, instruction: int, a: int, b: int
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
    Starts a background spin thread so that subscriptions (e.g. camera
    image topic) receive callbacks continuously.

    Args:
        args: Command line arguments for rclpy initialization.
    """
    global _ros_client_node, _spin_thread, _executor
    if _ros_client_node is None:
        rclpy.init(args=args)
        _ros_client_node = RobotManagerClient()
        _executor = MultiThreadedExecutor()
        _executor.add_node(_ros_client_node)
        _spin_thread = threading.Thread(target=_executor.spin, daemon=True)
        _spin_thread.start()
        _ros_client_node.get_logger().info("ROS communication initialized (background spin).")


def shutdown_ros_communication() -> None:
    """
    Shut down the ROS communication client.

    This function should be called once after all communication is finished.
    """
    global _ros_client_node, _spin_thread, _executor
    if _ros_client_node is not None:
        _ros_client_node.get_logger().info("Shutting down ROS communication.")
        if _executor is not None:
            _executor.shutdown()
            _executor = None
        _ros_client_node.destroy_node()
        rclpy.shutdown()
        _ros_client_node = None
        _spin_thread = None


def communicate(action_parts: List[int]) -> dict:
    """
    Send a single primitive action to the robot and wait for a response.

    Args:
        action_parts: A list containing the parts of a translated action,
                    e.g., ['PICK_UP', 'Cup', ''].

    Returns:
        A dict with at least ``{"success": bool}``.  For monitoring actions
        (instruction 20) the caller may enrich the dict with extra fields
        such as ``progress``.
    """
    global _ros_client_node
    if _ros_client_node is None:
        rclpy.logging.get_logger("ros_communicate").error(
            "ROS communication not initialized. Call init_ros_communication() first."
        )
        return {"success": False}

    if not isinstance(action_parts, list) or not action_parts:
        _ros_client_node.get_logger().error(f"Invalid action_parts received: {action_parts}")
        return {"success": False}

    try:
        robot_model = int(action_parts[0])
        instruction = int(action_parts[1])
        a = int(action_parts[2])
        b = int(action_parts[3])
    except (ValueError, IndexError) as e:
        _ros_client_node.get_logger().error(f"Failed to parse action parts: {e}")
        return {"success": False}

    action_str = f"{robot_model} {instruction} {a} {b}".strip()
    _ros_client_node.get_logger().info(f"Sending action: '{action_str}'")

    # 액션 시작 시간 기록
    start_time = time.time()

    future = _ros_client_node.send_request(robot_model, instruction, a, b)
    # Wait for future completion — the background executor handles spinning
    while not future.done():
        time.sleep(0.05)

    # 특정 instruction에 대해 최소 대기 시간 보장 (예: instruction 29번은 최소 5초)
    min_duration_map: dict[int, float] = {
        20: 5.9,  # instruction 20번: 최소 5초 대기
    }
    if instruction in min_duration_map:
        min_duration = min_duration_map[instruction]
        elapsed_time = time.time() - start_time
        _ros_client_node.get_logger().info(
                f"monitoring action {instruction}: Enforcing minimum duration. "
                f"elapsed: {elapsed_time:.2f}s, min: {min_duration}s"
            )
        if elapsed_time < min_duration:
            sleep_time = min_duration - elapsed_time
            _ros_client_node.get_logger().info(
                f"Instruction {instruction}: Enforcing minimum duration. "
                f"Waiting additional {sleep_time:.2f}s (elapsed: {elapsed_time:.2f}s, min: {min_duration}s)"
            )
            time.sleep(sleep_time)

    try:
        response = future.result()
        _ros_client_node.get_logger().info(f"DEBUG: Service response: {response}, Success: {response.success}")
        if response.success:
            _ros_client_node.get_logger().info(f"Action '{action_str}' succeeded.")
            return {"success": True}
        else:
            _ros_client_node.get_logger().error(
                f"Action '{action_str}' failed on robot side."
            )
            return {"success": False}
    except Exception as e:
        _ros_client_node.get_logger().error(
            f"Service call for action '{action_str}' failed with exception: {e!r}"
        )
        return {"success": False}


def main(args: list[str] | None = None) -> None:
    """Main function to run a test communication."""

    try:
        init_ros_communication(args=args)
        translated_primitive_actions = [
            [0 ,1 ,1 ,1],
            [0 ,1 ,1 ,1],
        ]
        for translated_primitive_action in translated_primitive_actions:
            result = communicate(translated_primitive_action)
            print(f"Test action result: {result}")
    finally:
        shutdown_ros_communication()


if __name__ == "__main__":
    main()