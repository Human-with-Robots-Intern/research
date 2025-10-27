# ros2 기본 요소 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

# ros2 사용자 정의 인터페이스 모듈
from robot_manager_interface.srv import RobotManager

# 기본 파이썬 모듈
import enum

class RobotManagerServer(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(RobotManager, 'robot_command', self.do_execute_job, callback_group=MutuallyExclusiveCallbackGroup())

        self.get_logger().info("robot tester is ready")

    def do_execute_job(self, request:RobotManager.Request, response:RobotManager.Response):
        self.get_logger().info("request.robot : {}".format(request.robot_model))
        self.get_logger().info("request.instruction : {}".format(request.instruction))
        self.get_logger().info("request.a : {}".format(request.a))
        self.get_logger().info("request.b : {}".format(request.b))

        response.success = True
        return response

def main():
    rclpy.init()
    node = RobotManagerServer()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
        node.process_entity.do_print_log()
    executor.remove_node(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()