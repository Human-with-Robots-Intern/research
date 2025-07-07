#변경점1 : 목표 지점 조정 (controller로 움직이는 거리만큼 nav2 목표에서 벡터로 빼줌)
#변경점2 : controller로 움직이는 거리 파라미터로 받기, nav2 목표 지점 파라미터로 받기

from nav2_msgs.action import NavigateToPose
from robot_control_interface.action import MoveStraight
from geometry_msgs.msg import PoseStamped
import math
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from tf_transformations import quaternion_from_euler


class NavigateActionClient(Node):

    def __init__(self):
        super().__init__('navigate_action_client')
        self.declare_parameters(
            namespace='',
            parameters=[
                ('distance_target', 0.5),  # Default distance target, can be overridden
            ]
        )
        self.distance_target = self.get_parameter('distance_target').value
        self._action_client_navigation = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._action_client_robotcontroller = ActionClient(self, MoveStraight, 'move_straight_control_action')
        
    def send_goal_navigation(self, x, y, yaw):
        goal_msg = NavigateToPose.Goal()
        # goal_msg._pose
        PoseStamped_msg = PoseStamped()

        PoseStamped_msg.pose.position.x = x - (self.distance_target)*(math.cos(yaw))
        PoseStamped_msg.pose.position.y = y - (self.distance_target)*(math.sin(yaw))
        PoseStamped_msg.pose.position.z = 0.0

        # Quaternion 
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
        self._send_goal_future = self._action_client_navigation.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback)
        self._send_goal_future.add_done_callback(self.goal_response_callback_navigation)

    def goal_response_callback_navigation(self, future):
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback_navigation)

    def get_result_callback_navigation(self, future):
        result = future.result().result
        self.get_logger().info('Result: {0}'.format("END"))
        if hasattr(result, 'error_msg'):
            ...
        else:
            self.send_goal_robotcontroller()
        rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback.distance_remaining
        self.get_logger().info('Received distance remaining: {0}'.format(feedback))

    def send_goal_robotcontroller(self):
        goal_request = MoveStraight.Goal()
        goal_request.distance_target = self.distance_target
        self._action_client_robotcontroller.wait_for_server(10)
        future = self._action_client_robotcontroller.send_goal_async(goal_request)
        future.add_done_callback(self.goal_response_callback_robotcontroller)

    def goal_response_callback_robotcontroller(self, future):
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return
        
        self.get_logger().info('Goal accepted :)')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback_robotcontroller)

    def get_result_callback_robotcontroller(self, future):
        result = future.result().result
        if result:
            self.get_logger().info('Goal succeeded!')
        else:
            self.get_logger().info('Goal failed!')

def main(args=None):
    rclpy.init(args=args)

    action_client_run = NavigateActionClient()
    action_client_run.send_goal_navigation(2.0, 2.0, 0.0)

    rclpy.spin(action_client_run)

if __name__ == '__main__':
    main()