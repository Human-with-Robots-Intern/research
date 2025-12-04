import sys
import argparse

from example_interfaces.srv import AddTwoInts
from geometry_msgs.msg import Pose
from moveit_proxy_interface.srv import SendPlan
from moveit_proxy_interface.srv import ExecPlan
from moveit_proxy_interface.srv import GetPose

import rclpy
from rclpy.node import Node

class MoveitProxyClient(Node):

    def __init__(self):
        super().__init__('moveit_proxy_client')
        # 상수 선언

        self.goal_pose = Pose() # geometry_msgs/Pose

        # do_plan service 선언
        self.cli_send_plan = self.create_client(SendPlan, 'moveit_proxy_send_plan')
        while not self.cli_send_plan.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req_send_plan = SendPlan.Request()

        # do_exec service 선언
        self.cli_exec_plan = self.create_client(ExecPlan, 'moveit_proxy_exec_plan')
        while not self.cli_exec_plan.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req_exec_plan = ExecPlan.Request()

        # get_pose service 선언
        self.cli_get_pose = self.create_client(GetPose, 'moveit_proxy_get_pose')
        while not self.cli_get_pose.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req_get_pose = GetPose.Request()

    # do_plan request function
    def do_send_plan_request(self, arg_goal_pose):
        print("moveit_proxy_client_test")
        self.req_send_plan.goal_pose = arg_goal_pose
        self.future_send_plan = self.cli_send_plan.call_async(self.req_send_plan)
        rclpy.spin_until_future_complete(self, self.future_send_plan)
        return self.future_send_plan.result()
    
    # do_exec request function
    def do_exec_plan_request(self):
        print("moveit_proxy_client_test")
        self.future_exec_plan = self.cli_exec_plan.call_async(self.req_exec_plan)
        rclpy.spin_until_future_complete(self, self.future_exec_plan)
        return self.future_exec_plan.result()

    # do_exec request function
    def get_pose_request(self):
        print("moveit_proxy_client_test")
        self.future_get_pose = self.cli_get_pose.call_async(self.req_get_pose)
        rclpy.spin_until_future_complete(self, self.future_get_pose)
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

    def do_send_plan_rosmsg(self, input_goal_pose):
        self.goal_pose = input_goal_pose
        response = self.do_send_plan_request(self.goal_pose)
        return response.result

    def do_send_plan_relative_rosmsg(self, input_displacement_pose):
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

def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-m', 
                        "--plan_mode",
                        type=int,
                        help="0 : absolute_position_mode, 1 : relative_position_mode", 
                        default=0)
    parser.add_argument('-x', 
                        "--position_x",
                        type=float,
                        help="posotion target of x(float_type)")
    parser.add_argument('-y', 
                        "--position_y",
                        type=float,
                        help="posotion target of y(float_type)")
    parser.add_argument('-z', 
                        "--position_z",
                        type=float,
                        help="posotion target of z(float_type)")
    parser.add_argument('-ow', 
                        "--orientation_w",
                        type=float,
                        default=1,
                        help="posotion target of w(float_type)")
    parser.add_argument('-ox', 
                        "--orientation_x",
                        type=float,
                        default=0,
                        help="posotion target of w(float_type)")
    parser.add_argument('-oy', 
                        "--orientation_y",
                        type=float,
                        default=0,
                        help="posotion target of w(float_type)")
    parser.add_argument('-oz', 
                        "--orientation_z",
                        type=float,
                        default=0,
                        help="posotion target of w(float_type)")

    args = parser.parse_args()

    print(args.plan_mode)
    print(args.position_x)
    print(args.position_y)
    print(args.position_z)
    print(args.orientation_w)
    print(args.orientation_x)
    print(args.orientation_y)
    print(args.orientation_z)

    rclpy.init()

    moveit_proxy_client = MoveitProxyClient()

    # geometry_msgs.pose에 원하는 값 대입 후 전달
    input_pose = Pose()
    input_pose.position.x = float(args.position_x)
    input_pose.position.y = float(args.position_y)
    input_pose.position.z = float(args.position_z)
    input_pose.orientation.w = float(args.orientation_w)
    input_pose.orientation.x = float(args.orientation_x)
    input_pose.orientation.y = float(args.orientation_y)
    input_pose.orientation.z = float(args.orientation_z)

    # plan mode에 따라 plan 방식 변경
    plan_mode = args.plan_mode
    if(plan_mode == 0):
        result = moveit_proxy_client.do_send_plan_rosmsg(input_pose)
    elif(plan_mode == 1):
        result = moveit_proxy_client.do_send_plan_relative_rosmsg(input_pose)
    else:
        assert 0, "wrong plan mode value"
    
    # send_plan 결과 확인
    moveit_proxy_client.get_logger().info(
        'send_plan result {}'.format(result))
    
    # plan 완료 후 exec 단계
    result = moveit_proxy_client.do_exec_plan()
    moveit_proxy_client.get_logger().info(
        "exec_plan result : {}".format(result))
    
    moveit_proxy_client.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
