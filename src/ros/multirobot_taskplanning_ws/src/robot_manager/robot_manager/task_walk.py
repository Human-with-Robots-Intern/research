import rclpy
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
from robot_control_interface.action import MoveStraight
from geometry_msgs.msg import PoseStamped
from tf_transformations import quaternion_from_euler
import json
import time
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

class WalkTask:
    def __init__(self, node):
        self.node = node
        self._action_client_navigation = ActionClient(self.node, NavigateToPose, 'navigate_to_pose', callback_group=MutuallyExclusiveCallbackGroup())
        self._action_client_robotcontroller = ActionClient(self.node, MoveStraight, 'move_straight_control_action', callback_group=MutuallyExclusiveCallbackGroup())

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

    def do(self):
        location_now, self.coordinate = self.get_coordinates_by_id(self.node.planner_instruction[1])
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
                return True
            if(self.node.state_of_move == 'free_out'):
                yaw_arg = self.coordinate[2]
                x_arg = self.coordinate[0]
                y_arg = self.coordinate[1]
                self.node.state_of_task = 'task_ing'
                self.node.state_of_move = 'move_ing'
                self.send_goal_navigation(x_arg, y_arg, yaw_arg)
                rclpy.spin_until_future_complete(self.node, self._send_goal_future_navigation)
                self.goal_response_navigation(self._send_goal_future_navigation)
                rclpy.spin_until_future_complete(self.node, self._get_result_future_navigation)
                if hasattr(self._get_result_future_navigation, 'error_msg'):
                    self.node.state_of_move = 'error'
                    self.node.state_of_task = 'error'
                    return False
                else:
                    self.node.state_of_move = 'free_out'
                    self.node.state_of_task = 'free'
                    return True
            else:
                print('error ocurred') #move_ing, error 상태일때 error 출력
        if location_now == self.node.location:
            print("sleep")
            time.sleep(5)
            return True

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
            self.node.get_logger().info('Goal rejected :(')
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

    def send_goal_robotcontroller(self):
        goal_request = MoveStraight.Goal()
        goal_request.distance_target = self.node.distance_target
        self._action_client_robotcontroller.wait_for_server(10)
        self._send_goal_future_robot_control = self._action_client_robotcontroller.send_goal_async(goal_request)
        return self._send_goal_future_robot_control

    def goal_response_callback_robotcontroller(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.node.get_logger().info('Goal rejected :(')
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

    def send_goal_robotcontroller_out(self):
        goal_request = MoveStraight.Goal()
        goal_request.distance_target = -self.node.distance_target #minus distance_target
        self._action_client_robotcontroller.wait_for_server(10)
        self._send_goal_future_robot_control = self._action_client_robotcontroller.send_goal_async(goal_request)
        return self._send_goal_future_robot_control