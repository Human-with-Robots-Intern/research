# ros2 기본 모듈
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros2 기본 인터페이스
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped

# 사용자 정의 인터페이스
from robot_control_interface.action import MoveStraight

# 파이썬 기본 모듈
import math
import json
import time
import enum

# 파이썬 외부 모듈
from tf_transformations import quaternion_from_euler
# 해당 모듈 오류가 있는 좌표 변환 모듈이었던 것으로 확인됨 차후 다른 모듈로 교체하기 - 2024-0910-1122

# 파이썬 사용자 정의 모듈
from robot_manager.robot_manager.robot_entity.robot import Robot

class FindTask:
    def __init__(self, node_arg:rclpy.Node, robot_arg:Robot):
        self.robot = robot_arg
        self.node = node_arg

        # ros2 기능 요소 정의
        self._action_client_navigation = ActionClient(self.node, NavigateToPose, 'navigate_to_pose', callback_group=MutuallyExclusiveCallbackGroup)
        self._action_client_robotcontroller = ActionClient(self.node, MoveStraight, 'move_straight_control_action', callback_group=MutuallyExclusiveCallbackGroup)

        # 사용자 정의 객체 선언
        class Find_task_sequence_state(enum.Enum):
            action_send_goal_move_straight = enum.auto()
            action_wait_move_straight = enum.auto()
            action_complete_move_straight = enum.auto()
            action_send_goal_navigate_to_pose = enum.auto()
            action_wait_navigate_to_pose = enum.auto()
            action_complete_navigate_to_pose = enum.auto()
            wait_action_transition = enum.auto()
            init = enum.auto()
            ready = enum.auto()
            error = enum.auto()

        self.task_sequence_state_enum = Find_task_sequence_state
        self.task_sequence_state = self.task_sequence_state_enum.init.value

        # 초기화 실행 문
        if self.robot.get_mobilebase_property_instance().get_is_enabled() == False:
            assert 0, "로봇에 이동 속성이 없거나 활성화 되지 않았습니다."

        # 액션 서버가 준비 되어있는지 확인
        wait_nav_action = self._action_client_navigation.wait_for_server(10)
        wait_move_action = self._action_client_robotcontroller.wait_for_server(10)

        if wait_nav_action and wait_move_action == True:
            self.task_sequence_state = self.task_sequence_state_enum.ready.value
            # 액션 서버가 준비되어 있다면 task 또한 준비 상태로 변경

    def get_coordinates_by_id(self, id_number):
        with open('planner_instruction/instruction_position.json', 'r') as f:
            data = json.load(f)
        found = False
        coordinates = None
        for node in data['nodes']:
            if node['id'] == id_number:
                found = True
                location = node['location']
                coordinates = data['positions'][0][location]
                break
        if not found:
            print(f"ID '{id_number}' not found in the data.")
        return location, coordinates

    def set_request(self, request_arg):
        ...

    def do(self):
        location_now, self.coordinate = self.get_coordinates_by_id(self.node.planner_instruction[1])
        # time.sleep(10)
        if location_now != self.node.location:
            self.node.location = location_now
            if(self.node.state_of_move == 'free_in'):
                self.node.state_of_task = 'task_ing'
                self.node.state_of_move = 'move_ing'
                self.send_goal_robotcontroller_out()
                rclpy.spin_until_future_complete(self.node, self._send_goal_future_robot_control)
                self.goal_response_callback_robotcontroller(self._send_goal_future_robot_control)
                rclpy.spin_until_future_complete(self.node, self._get_result_future_robot_control)
                self.node.state_of_move = 'free_out'
                time.sleep(1.5)
                return True
            if(self.node.state_of_move == 'free_out'):
                yaw = self.coordinate[2]
                x = self.coordinate[0] - (self.node.distance_target)*(math.cos(yaw))
                y = self.coordinate[1] - (self.node.distance_target)*(math.sin(yaw))
                print(self.node.state_of_move)
                self.node.state_of_task = 'task_ing'
                self.node.state_of_move = 'move_ing'
                self.send_goal_navigation(x, y, yaw)
                rclpy.spin_until_future_complete(self.node, self._send_goal_future_navigation)
                self.goal_response_navigation(self._send_goal_future_navigation)
                rclpy.spin_until_future_complete(self.node, self._get_result_future_navigation)
                if hasattr(self._get_result_future_navigation, 'error_msg'):
                    self.node.state_of_move = 'error'
                    self.node.state_of_task = 'error'
                    return False
                else:
                    time.sleep(1.5)
                    self.send_goal_robotcontroller()
                    rclpy.spin_until_future_complete(self.node, self._send_goal_future_robot_control)
                    self.goal_response_callback_robotcontroller(self._send_goal_future_robot_control)
                    rclpy.spin_until_future_complete(self.node, self._get_result_future_robot_control)
                    self.node.state_of_move = 'free_in'
                    self.node.state_of_task = 'free'
                    return True
            else:
                print('error ocurred') #move_ing, error 상태일때 error 출력

    def do_update_state(self):
        # 주기적으로 변수들의 상태를 확인하여 
        # 흐름제어를 결정하는 역할
        mobile_properties = self.robot.get_mobilebase_property_instance()
        job_properties = self.robot.get_worker_property_instance()

        mobile_state = mobile_properties.get_state()
        job_state = job_properties.get_state()

        # 첫 명령을 전달 받을 때
        if self.task_sequence_state == self.task_sequence_state_enum.ready.value:
            if mobile_state == mobile_properties.mobilebase_state_enum.safe_zone:
                # 안전지대에서 출발할 경우 naviagtion 을 바로 수행
                self.task_sequence_state = self.task_sequence_state_enum.action_send_goal_navigate_to_pose
                self.robot.get_worker_property_instance().set_state(job_properties.job_state_enum.working.value)

            

        ...



    def send_goal_navigation(self, x, y, yaw):
        goal_msg = NavigateToPose.Goal()
        PoseStamped_msg = PoseStamped()
        PoseStamped_msg.pose.position.x = x
        PoseStamped_msg.pose.position.y = y
        PoseStamped_msg.pose.position.z = 0.0
        roll = 0.0; pitch = 0.0
        quaternion = quaternion_from_euler(roll, pitch, yaw)
        ori_x = quaternion[0]
        ori_y = quaternion[1]
        ori_z = quaternion[2]
        ori_w = quaternion[3]
        PoseStamped_msg.pose.orientation.w = ori_w
        PoseStamped_msg.pose.orientation.x = ori_x
        PoseStamped_msg.pose.orientation.y = ori_y
        PoseStamped_msg.pose.orientation.z = ori_z
        PoseStamped_msg.header.frame_id = 'map'
        goal_msg._pose = PoseStamped_msg
        self._action_client_navigation.wait_for_server(10)
        self._send_goal_future_navigation = self._action_client_navigation.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback)
        return self._send_goal_future_navigation
    
    def goal_response_navigation(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.node.get_logger().info('Nav Goal rejected :(')
            return 
        self.node.get_logger().info('Goal accepted :)')
        self._get_result_future_navigation = goal_handle.get_result_async()
        self._get_result_future_navigation.add_done_callback(self.get_result_callback_navigation)

    def get_result_callback_navigation(self, future):
        result = future.result().result
        self.node.get_logger().info('Result: {0}'.format("END"))
        return result

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback.distance_remaining
        self.node.get_logger().info('Received distance remaining: {0}'.format(feedback))

    def send_goal_robotcontroller(self, distance_target_arg:float):
        goal_request = MoveStraight.Goal()
        goal_request.distance_target = distance_target_arg
        self._action_client_robotcontroller.wait_for_server(10)
        self._send_goal_future_robot_control = self._action_client_robotcontroller.send_goal_async(goal_request)
        return self._send_goal_future_robot_control

    def goal_response_callback_robotcontroller(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.node.get_logger().info('Control Goal rejected :(')
            return
        self.node.get_logger().info('Goal accepted :)')
        self._get_result_future_robot_control = goal_handle.get_result_async()
        self._get_result_future_robot_control.add_done_callback(self.get_result_callback_robotcontroller)

    def get_result_callback_robotcontroller(self, future):
        result = future.result().result
        if result:
            self.node.get_logger().info('Goal succeeded!')
        else:
            self.node.get_logger().info('Goal failed!') #move error
