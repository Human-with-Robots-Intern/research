# ros2 노드 구현 파이썬 서비스 서버 
# 1. 서비스를 통해 명령 받기

# ROS2 기본 모듈
import rclpy
from rclpy.node import Node

# ROS2 기본 인터페이스
from geometry_msgs.msg import PoseArray
from std_srvs.srv import Trigger

# 사용자 정의 인터페이스 모듈
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 오브젝트(ArUco 마커) 인식 모듈
from module.arucro_detect import realsense_camera
from module.arucro_detect import DetectArUco

# 사용자 정의 모듈
# 마커 탐지 모듈
# 코드 참고 자료
# https://github.com/JMU-ROBOTICS-VIVA/ros2_aruco/blob/main/ros2_aruco/ros2_aruco/aruco_node.py

class ObjectDetector(Node):
    def __init__(self):
        super().__init__("object_detector")
        # <맴버 변수 정의>
        # <ROS2 파라미터 정의>
        self.declare_parameter("marker_size", 34)
        self.declare_parameter("marker_type", 6)

        # self.declare_parameter("marker_size")
        # self.declare_parameter("marker_type")
        # <ROS2 기능요소 정의>
        self.service_server_detect_objects = self.create_service(DetectObjects, "detect_objects", self.callback_do_detect_objects)
        self.service_server_toggle = self.create_service(Trigger, "toggle", self.callback_do_toggle)
        self.publisher_pose_array = self.create_publisher(PoseArray, "aruco_markers", 10)
        self.timer = self.create_timer(0.1, self.callback_do_publish_objects)
        self.timer.cancel()

        self.get_logger().info("object_detector node start")

        self.cam = realsense_camera(height=1080, width=1920, fps=30, use_color=True, use_depth=False)
        self.detector = DetectArUco(self.cam)

        # 카메라 왜곡 보정 파라미터
        fx = 1337.647906
        fy = 1337.647906
        cx = 960.000000
        cy = 540.000000
        cmtx = [[fx,0.0,cx],
                [0.0,fy,cy],
                [0.0,0.0,1.0],]
        
        k1 = 0.099619
        k2 = -0.240592
        p1 = 0.004100
        p2 = -0.001100
        dist = [k1, k2, p1, p2]

        self.detector.set_calibration_parameter(cmtx, dist)
        marker_type_value = self.get_parameter("marker_type").get_parameter_value().integer_value
        marker_size_value = self.get_parameter("marker_size").get_parameter_value().integer_value
        print("marker_type : {}".format(marker_type_value))
        print("marker_size : {}".format(marker_size_value))
        self.detector.set_marker_type(marker_type_value)
        self.detector.set_marker_size(marker_size_value)

    def callback_do_toggle(self, request:Trigger.Request, response:Trigger.Response):
        if self.timer.is_canceled():
            self.timer.reset()
            response.success = True
            response.message = "timer on"
        else:
            self.timer.cancel()
            response.success = False
            response.message = "timer off"
        return response

    def callback_do_detect_objects(self, request:DetectObjects.Request, response:DetectObjects.Response):
        self.detector.do_init_data()
        self.detector.do_detect_marker()
        img = self.detector.draw_detected_point()
        num_of_ids, object_lsit = self.detector.get_marker_list()
        print(type(object_lsit))
        #request는 empty 타입
        response.entity_num = num_of_ids
        
        aruco_marker_poses = PoseArray()

        for object in object_lsit:
            object_instance = ObjectData()# 메시지 타입 객체를 새로 생성
            print(object.tvec)
            print(object.id)
            print(type(object.tvec))
            print(type(object.id))
            object_instance.id = int(object.id)
            object_instance.pose.position.x = float(object.tvec[0][0])
            object_instance.pose.position.y = float(object.tvec[1][0])
            object_instance.pose.position.z = float(object.tvec[2][0])

            object_instance.pose.orientation.x = float(object.quat[0])
            object_instance.pose.orientation.y = float(object.quat[1])
            object_instance.pose.orientation.z = float(object.quat[2])
            object_instance.pose.orientation.w = float(object.quat[3])

            response.object_list.append(object_instance)# sequence 타입의 객체
            aruco_marker_poses.poses.append(object_instance.pose)

        aruco_marker_poses.header.stamp = self.get_clock().now().to_msg()
        aruco_marker_poses.header.frame_id = "frame1"
        self.publisher_pose_array.publish(aruco_marker_poses)
        print(response.object_list)
        print(aruco_marker_poses)
        return response
        
    def callback_do_publish_objects(self):
        self.detector.do_init_data()
        self.detector.do_detect_marker()
        img = self.detector.draw_detected_point()
        num_of_ids, object_lsit = self.detector.get_marker_list()
        print(type(object_lsit))
        #request는 empty 타입
        aruco_marker_poses = PoseArray()
        
        for object in object_lsit:
            object_instance = ObjectData()# 메시지 타입 객체를 새로 생성
            print(object.tvec)
            print(object.id)
            print(type(object.tvec))
            print(type(object.id))
            object_instance.id = int(object.id)
            object_instance.pose.position.x = float(object.tvec[0][0])
            object_instance.pose.position.y = float(object.tvec[1][0])
            object_instance.pose.position.z = float(object.tvec[2][0])

            object_instance.pose.orientation.x = float(object.quat[0])
            object_instance.pose.orientation.y = float(object.quat[1])
            object_instance.pose.orientation.z = float(object.quat[2])
            object_instance.pose.orientation.w = float(object.quat[3])

            aruco_marker_poses.poses.append(object_instance.pose)

        aruco_marker_poses.header.stamp = self.get_clock().now().to_msg()
        aruco_marker_poses.header.frame_id = "frame1"
        self.publisher_pose_array.publish(aruco_marker_poses)
        print(aruco_marker_poses)

def main():
    rclpy.init()

    object_detector = ObjectDetector()

    rclpy.spin(object_detector)

    rclpy.shutdown()


if __name__ == '__main__':
    main()