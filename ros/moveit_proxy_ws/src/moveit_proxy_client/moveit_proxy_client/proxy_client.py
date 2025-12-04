import sys

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

    def do_send_plan_args(self, x, y, z, qw, qx, qy, qz):
        input_pose = Pose()
        input_pose.position.x = float(x)
        input_pose.position.y = float(y)
        input_pose.position.z = float(z)
        input_pose.orientation.w = float(qw)
        input_pose.orientation.x = float(qx)
        input_pose.orientation.y = float(qy)
        input_pose.orientation.z = float(qz)
        result = self.do_send_plan_rosmsg(input_pose)
        return result

    def do_send_plan_relative_args(self, x, y, z, qw, qx, qy, qz):
        input_displacement_pose = Pose()
        input_displacement_pose.position.x = float(x)
        input_displacement_pose.position.y = float(y)
        input_displacement_pose.position.z = float(z)
        input_displacement_pose.orientation.w = float(qw)
        input_displacement_pose.orientation.x = float(qx)
        input_displacement_pose.orientation.y = float(qy)
        input_displacement_pose.orientation.z = float(qz)

        result = self.do_send_plan_relative_rosmsg(input_displacement_pose)
        return result

    def do_send_plan_rosmsg(self, input_goal_pose):
        self.goal_pose = input_goal_pose
        response = self.do_send_plan_request(self.goal_pose)
        return response.result

    def do_send_plan_relative_rosmsg(self, input_displacement_pose):
        current_pose = self.get_pose_request()

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

def main():
    rclpy.init()

    moveit_proxy_client = MoveitProxyClient()


    plan_result = False
    exec_result = False
    iter = 0
    while(1):
        plan_result = False
        exec_result = False
        # 테스트용 반복 제한(불필요시 삭제)
        iter+=1
        if(iter > 5):
            print("iteration finished")
            break
        
        #----------------
        # 사용자 정의 코드 삽입 영역 

        # ~~~put your code here~~~
        

        # plan 단계
        # do_send_plan_args에 원하는 값 대입 후 전달

        # example code
        if(iter == 0):
            x = 0.5
            y = 0.2
            z = 0.0
            qw = 1.0
            qx = 0.0
            qy = 0.0
            qz = 0.0
            # 함수 사용 예시
            plan_result = moveit_proxy_client.do_send_plan_args(x, y, z, qw, qx, qy, qz) 
        
        elif(iter == 1):
            input_goal_pose = Pose()
            input_goal_pose.position.x = 0.3
            input_goal_pose.position.y = -0.2
            input_goal_pose.position.z = 0.5
            input_goal_pose.orientation.w = -1.0
        
            # ros2 geometry_msg를 통해 직접 입력하는 함수도 이용 가능
            plan_result = moveit_proxy_client.do_send_plan_rosmsg(input_goal_pose) 
        
        elif(iter >= 2):
            x = 0.5
            y = 0.2
            z = 0.0
            qw = 1.0
            qx = 0.0
            qy = 0.0
            qz = 0.0
            plan_result = moveit_proxy_client.do_send_plan_args(x, y, z, qw, qx, qy, qz) 

        #----------------

        if(plan_result == False):
            print("plan failed")
            break

        
        exec_result = moveit_proxy_client.do_exec_plan() # 함수 사용 예시
        if(exec_result == False):
            print("execution failed")
            break
        # plan 완료 후 exec 단계

        # 로봇의 동작이 끝날 때 까지 기다리기

    moveit_proxy_client.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()