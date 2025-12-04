import sys

from example_interfaces.srv import AddTwoInts
from geometry_msgs.msg import Pose
from moveit_proxy_interface.srv import SendPlan
from moveit_proxy_interface.srv import ExecPlan


import rclpy
from rclpy.node import Node


class MoveitProxyClient(Node):

    def __init__(self):
        super().__init__('moveit_proxy_client')

        # plan service 선언
        self.cli_send_plan = self.create_client(SendPlan, 'moveit_proxy_send_plan')
        while not self.cli_send_plan.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req_send_plan = SendPlan.Request()

        # exec service 선언
        self.cli_exec_plan = self.create_client(ExecPlan, 'moveit_proxy_exec_plan')
        while not self.cli_exec_plan.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req_exec_plan = ExecPlan.Request()

    # plan request callback
    def do_send_plan_request(self, arg_goal_pose):
        print("moveit_proxy_client_test")
        self.req_send_plan.goal_pose = arg_goal_pose
        self.future = self.cli_send_plan.call_async(self.req_send_plan)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()
    
    # exec request callback
    def do_exec_plan_request(self):
        print("moveit_proxy_client_test")
        self.future = self.cli_exec_plan.call_async(self.req_exec_plan)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()


def main():
    rclpy.init()

    moveit_proxy_client = MoveitProxyClient()

    # plan 단계

    # geometry_msgs.pose에 원하는 값 대입 후 전달
    input_goal_pose = Pose()
    input_goal_pose.position.x = float(sys.argv[1])
    input_goal_pose.position.y = float(sys.argv[2])
    input_goal_pose.position.z = float(sys.argv[3])

    response = moveit_proxy_client.do_send_plan_request(input_goal_pose)
    moveit_proxy_client.get_logger().info(
        'exec_plan result {}'.format(response.result))
    
    # plan 완료 후 exec 단계
    response = moveit_proxy_client.do_exec_plan_request()
    moveit_proxy_client.get_logger().info(
        "exec_plan result : {}".format(response.result))
    
    moveit_proxy_client.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()