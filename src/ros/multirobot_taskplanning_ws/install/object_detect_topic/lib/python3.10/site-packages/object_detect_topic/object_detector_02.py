# ros2 노드 구현 파이썬 서비스 서버 
# 1. 서비스를 통해 명령 받기

# ROS2 기본 모듈
import rclpy
from rclpy.node import Node

# 사용자 정의 메시지 모듈
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 사용자 정의 모듈
# 마커 탐지 모듈

class ObjectDetector(Node):
    def __init__(self):
        super().__init__("object_detector")
        # <맴버 변수 정의>
        # <ROS2 기능용소 정의>
        self.service_server_detect_objects = self.create_service(DetectObjects, "detect_objects", self.callback_do_detect_objects)
        self.get_logger().info("object_detector node start")

    def callback_do_detect_objects(self, request:DetectObjects.Request, response:DetectObjects.Response):
        #request는 empty 타입
        response.entity_num = 1
        object_test_01 = ObjectData()
        object_test_02 = ObjectData()
        object_test_01.id = 1
        object_test_02.id = 2
        response.object_list.append(object_test_01)
        response.object_list.append(object_test_02)
        print(response.object_list)
        return response

def main():
    rclpy.init()

    object_detector = ObjectDetector()

    rclpy.spin(object_detector)

    rclpy.shutdown()


if __name__ == '__main__':
    main()