import math
from geometry_msgs.msg import Pose
from moveit_proxy_interface.srv import SendPlan, ExecPlan, GetPose
import rclpy

class MoveitClient:
    def __init__(self, node):
        self.node = node
        self.goal_pose = Pose()  # geometry_msgs/Pose

        # do_plan service 선언
        self.cli_send_plan = self.node.create_client(SendPlan, '/moveit_proxy_send_plan')
        while not self.cli_send_plan.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('service not available, waiting again...')
        self.req_send_plan = SendPlan.Request()

        # do_exec service 선언
        self.cli_exec_plan = self.node.create_client(ExecPlan, '/moveit_proxy_exec_plan')
        while not self.cli_exec_plan.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('service not available, waiting again...')
        self.req_exec_plan = ExecPlan.Request()

        # get_pose service 선언
        self.cli_get_pose = self.node.create_client(GetPose, '/moveit_proxy_get_pose')
        while not self.cli_get_pose.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('service not available, waiting again...')
        self.req_get_pose = GetPose.Request()

    def do_send_plan_request(self, arg_goal_pose):
        print("moveit_proxy_client_test")
        self.req_send_plan.goal_pose = arg_goal_pose
        self.future_send_plan = self.cli_send_plan.call_async(self.req_send_plan)
        rclpy.spin_until_future_complete(self.node, self.future_send_plan)
        return self.future_send_plan.result()

    def do_exec_plan_request(self):
        print("moveit_proxy_client_test")
        self.future_exec_plan = self.cli_exec_plan.call_async(self.req_exec_plan)
        rclpy.spin_until_future_complete(self.node, self.future_exec_plan)
        return self.future_exec_plan.result()

    def get_pose_request(self):
        print("moveit_proxy_client_test")
        self.future_get_pose = self.cli_get_pose.call_async(self.req_get_pose)
        rclpy.spin_until_future_complete(self.node, self.future_get_pose)
        return self.future_get_pose.result()

    def get_current_pose(self):
        response = self.get_pose_request()
        return response.pose

    def do_send_plan_args(self, x, y, z, ox=0, oy=0, oz=0, ow=1):
        input_pose = Pose()
        input_pose.position.x = float(x)
        input_pose.position.y = float(y)
        input_pose.position.z = float(z)
        input_pose.orientation.x = float(ox)
        input_pose.orientation.y = float(oy)
        input_pose.orientation.z = float(oz)
        input_pose.orientation.w = float(ow)
        result = self.do_send_plan_rosmsg(input_pose)
        return result

    def do_send_plan_relative_args(self, x=0, y=0, z=0, ox=0, oy=0, oz=0, ow=0):
        input_displacement_pose = Pose()
        input_displacement_pose.position.x = float(x)
        input_displacement_pose.position.y = float(y)
        input_displacement_pose.position.z = float(z)
        input_displacement_pose.orientation.x = float(ox)
        input_displacement_pose.orientation.y = float(oy)
        input_displacement_pose.orientation.z = float(oz)
        input_displacement_pose.orientation.w = float(ow)

        result = self.do_send_plan_relative_rosmsg(input_displacement_pose)
        return result

    def do_send_plan_rosmsg(self, input_goal_pose: Pose):
        self.goal_pose = input_goal_pose
        response = self.do_send_plan_request(self.goal_pose)
        return response.result

    def do_send_plan_relative_rosmsg(self, input_displacement_pose: Pose):
        current_pose = self.get_current_pose()

        self.goal_pose.position.x = current_pose.position.x + input_displacement_pose.position.x
        self.goal_pose.position.y = current_pose.position.y + input_displacement_pose.position.y
        self.goal_pose.position.z = current_pose.position.z + input_displacement_pose.position.z
        self.goal_pose.orientation.x = current_pose.orientation.x + input_displacement_pose.orientation.x
        self.goal_pose.orientation.y = current_pose.orientation.y + input_displacement_pose.orientation.y
        self.goal_pose.orientation.z = current_pose.orientation.z + input_displacement_pose.orientation.z
        self.goal_pose.orientation.w = current_pose.orientation.w + input_displacement_pose.orientation.w

        response = self.do_send_plan_request(self.goal_pose)
        return response.result

    def do_exec_plan(self):
        response = self.do_exec_plan_request()
        return response.result
