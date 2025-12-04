# ros2 노드 구현 파이썬 서비스 서버 
# 1. 서비스를 통해 명령 받기

# ROS2 기본 모듈
import rclpy
from rclpy.node import Node

# 사용자 정의 메시지 모듈
from marker_detect_interface.msg import MarkerData
from marker_detect_interface.srv import DetectMarkers

class MarkerDetector(Node):
    def __init__(self):
        super().__init__("marker_detector")
        # <맴버 변수 정의>
        # <ROS2 기능용소 정의>
        self.service_server_detect_markers = self.create_service(DetectMarkers, "detect_markers", self.callback_do_detect_markers)
        self.get_logger().info("marker_detector node start")

    def callback_do_detect_markers(self, request:DetectMarkers.Request, response:DetectMarkers.Response):
        #request는 empty 타입
        response.entity_num = 1
        marker_test_01 = MarkerData()
        marker_test_02 = MarkerData()
        marker_test_01.id = 1 
        marker_test_02.id = 2
        response.marker_list.append(marker_test_01)
        response.marker_list.append(marker_test_02)
        print(response.marker_list)
        return response
        

def main():
    rclpy.init()

    marker_detector = MarkerDetector()

    rclpy.spin(marker_detector)

    rclpy.shutdown()


if __name__ == '__main__':
    main()