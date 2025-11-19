# ros2 기본 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

# ros2 기본 interface 모듈
from std_srvs.srv import Trigger
from geometry_msgs.msg import Pose

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.module.pose_calc_module import PoseCalcModule

class ManipulationNode(Node):
    def __init__(self):
        super().__init__('manipulator_test_node')
        # <핵심 기능 요소 포함 관계 선언> 
        self.manipulation_module = PoseCalcModule(self)

        # <ros2 기능요소 선언>
        self.trigger_service = self.create_service(Trigger, "test", self.callback_test)
        

    def callback_test(self, request:Trigger.Request, response:Trigger.Response):
        response = Trigger.Response()

        pose_obj = Pose() # object
        pose_obj.position.x = 1.0
        pose_obj.position.y = 2.0
        pose_obj.position.z = 3.0
        pose_obj.orientation.x = 0.0
        pose_obj.orientation.y = 0.0
        pose_obj.orientation.z = 0.0
        pose_obj.orientation.w = 1.0

        pose_robot = Pose() # robot
        pose_robot.position.x = 4.0
        pose_robot.position.y = 5.0
        pose_robot.position.z = 6.0
        pose_robot.orientation.x = 0.0
        pose_robot.orientation.y = 0.0
        pose_robot.orientation.z = 0.0
        pose_robot.orientation.w = 1.0

        pose_offset:Pose = self.manipulation_module.do_calc_frame_offset(pose_obj, pose_robot)
        pose_target:Pose = self.manipulation_module.do_calc_end_effector_position(pose_obj, pose_offset)

        print("test")
        print(pose_obj)
        print(pose_robot)
        print(pose_offset)
        print(pose_target)

        object_id_a = 0
        object_id_b = 0
        action_id = 0
        sub_action = "start"
        sequence_id = 1

        self.manipulation_module.set_manipulation_data(object_id_a, object_id_b, action_id, sequence_id, sub_action, pose_offset, is_relative=True)
        print("test")
        action_manipulation_data = self.manipulation_module.get_manipulation_data(object_id_a, object_id_b, action_id, sequence_id)
        print("test")
        self.manipulation_module.save_manipulation_data_to_json("data/object_data.json")
        print("test")
        self.manipulation_module.load_manipulation_data_from_json("data/object_data.json")
        print("test")
        action_manipulation_data = self.manipulation_module.get_manipulation_data(object_id_a, object_id_b, action_id, sequence_id)
        print(action_manipulation_data)
        sub_action:str = action_manipulation_data["sub_action"]
        pose_data:Pose = action_manipulation_data['pose']
        relativity_data:bool = action_manipulation_data['is_relative']

        print(pose_data)
        print(relativity_data)

        response.success = True
        return response


def main():
    rclpy.init()
    node = ManipulationNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
    executor.remove_node(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()