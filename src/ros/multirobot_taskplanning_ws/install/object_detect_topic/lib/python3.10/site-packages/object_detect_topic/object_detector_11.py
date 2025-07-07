# ros2 노드 구현 파이썬 서비스 서버 
# 1. 서비스를 통해 명령 받기

# ROS2 기본 모듈
import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ROS2 기본 인터페이스
from geometry_msgs.msg import PoseArray
from sensor_msgs.msg import Image
from std_srvs.srv import Trigger

# 사용자 정의 인터페이스 모듈
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# ROS2 추가 모듈
from cv_bridge import CvBridge

# 오브젝트(ArUco 마커) 인식 모듈
from module.arucro_detect import realsense_camera
from module.arucro_detect import DetectArUco

# 파이썬 기본 모듈
import threading

# 사용자 정의 모듈
# 마커 탐지 모듈
# 코드 참고 자료
# https://github.com/JMU-ROBOTICS-VIVA/ros2_aruco/blob/main/ros2_aruco/ros2_aruco/aruco_node.py

class ObjectDetector(Node):
    def __init__(self):
        super().__init__("object_detector")
        # <맴버 변수 정의>
        # <ROS2 파라미터 정의>
        self.declare_parameter("marker_size", 29)
        self.declare_parameter("marker_type", 6)

        # self.declare_parameter("marker_size")
        # self.declare_parameter("marker_type")
        # <ROS2 기능요소 정의>
        # service 정의
        self.service_server_detect_objects = self.create_service(DetectObjects, "detect_objects", self.callback_do_detect_objects, callback_group=MutuallyExclusiveCallbackGroup())
        self.service_server_toggle = self.create_service(Trigger, "toggle", self.callback_do_toggle)
        # self.service_server_recode_toggle = self.create_service(Trigger, "recode_toggle", self.callback_do_recode_toggle, callback_group=MutuallyExclusiveCallbackGroup())

        # publisher 정의 
        self.publisher_pose_array = self.create_publisher(PoseArray, "aruco_markers", 10)
        self.publisher_image_processed = self.create_publisher(Image, "image_processed", 10)
        
        # subscriber 정의
        self.subscriber_img = self.create_subscription(Image, "camera/color/image_raw", self.callback_set_img, 10, callback_group=MutuallyExclusiveCallbackGroup()) 
        # 실제 활용에서는 네임스페이스를 로봇의 네임스페이스로 적용하여 로봇간 토픽이 구분되도록 바꾸어 주기
        # timer 정의
        # self.timer = self.create_timer(0.1, self.callback_do_publish_objects)
        # self.recode_timer = self.create_timer(0.1, self.callback_do_recode_video)
        # self.timer.cancel()

        self.get_logger().info("object_detector node start")

        # self.cam = realsense_camera(height=1080, width=1920, fps=30, use_color=True, use_depth=False)
        self.detector = DetectArUco()

        # <ROS2 tf 요소 정의>
        self.camera_frame = "cam"# 프레임의 기본 이름 

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

        # toggle 상태변수
        self.toggle_publish_pose = False

        # cv_bridge 선언
        self.bridge = CvBridge()

        # 이미지 데이터 버퍼
        # 이 부분은 먼저 토픽으로 이미지를 받아오는데 성공한 다음에 처리하기
        # 현재 당장은 이미지를 버퍼로 쌓아두지 않고 1개의 이미지만 저장
        self.img = None
        # 이미지 쓰기 뮤텍스
        self.lock_set_img = threading.Lock()
        self.lock_process_img = threading.Lock()

    def callback_set_img(self, msg:Image):
        with self.lock_set_img:
            self.img = msg
        if self.toggle_publish_pose:
            with self.lock_process_img:
                img_cv = self.bridge.imgmsg_to_cv2(self.img)
                self.detector.set_img(img_cv)
                self.detector.do_init_data()
                self.detector.do_detect_marker()
                img_cv_processed = self.detector.draw_detected_point()
                img_msg_processed = self.bridge.cv2_to_imgmsg(img_cv_processed, "rgb8")
                num_of_ids, object_lsit = self.detector.get_marker_list()
            # print(type(object_lsit))
            #request는 empty 타입
            aruco_marker_poses = PoseArray()
            
            for object in object_lsit:
                object_instance = ObjectData()# 메시지 타입 객체를 새로 생성
                # print(object.tvec)
                # print(object.id)
                # print(type(object.tvec))
                # print(type(object.id))
                object_instance.id = int(object.id)
                object_instance.pose.position.x = float(object.tvec[0][0])
                object_instance.pose.position.y = float(object.tvec[1][0])
                object_instance.pose.position.z = float(object.tvec[2][0])

                # object_instance.pose.orientation.x = float(object.quat[0])
                # object_instance.pose.orientation.y = float(object.quat[1])
                # object_instance.pose.orientation.z = float(object.quat[2])
                # object_instance.pose.orientation.w = float(object.quat[3])

                object_instance.pose.orientation.x = float(object.quat[1])
                object_instance.pose.orientation.y = float(object.quat[2])
                object_instance.pose.orientation.z = float(object.quat[3])
                object_instance.pose.orientation.w = float(object.quat[0])

                aruco_marker_poses.poses.append(object_instance.pose)

            aruco_marker_poses.header.stamp = self.get_clock().now().to_msg()
            aruco_marker_poses.header.frame_id = self.camera_frame
            self.publisher_pose_array.publish(aruco_marker_poses)
            self.publisher_image_processed.publish(img_msg_processed)
            # print(aruco_marker_poses)

    def callback_do_toggle(self, request:Trigger.Request, response:Trigger.Response):
        if self.toggle_publish_pose == False:
            self.toggle_publish_pose = True
            response.success = True
            response.message = "publish pose on"
        else:
            self.toggle_publish_pose = False
            response.success = False
            response.message = "publish pose off"
        return response

    def callback_do_detect_objects(self, request:DetectObjects.Request, response:DetectObjects.Response):
        if self.img is not None:
            with self.lock_set_img:
                img_cv = self.bridge.imgmsg_to_cv2(self.img, "bgr8")
            with self.lock_process_img:
                self.detector.set_img(img_cv) # 이미지를 set 하는 동안에 덮여 씌워지거나 지워지지 않도록 상호배제 처리
                self.detector.do_init_data()
                self.detector.do_detect_marker()
                # img = self.detector.draw_detected_point()
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

                # object_instance.pose.orientation.x = float(object.quat[0])
                # object_instance.pose.orientation.y = float(object.quat[1])
                # object_instance.pose.orientation.z = float(object.quat[2])
                # object_instance.pose.orientation.w = float(object.quat[3])

                object_instance.pose.orientation.x = float(object.quat[1])
                object_instance.pose.orientation.y = float(object.quat[2])
                object_instance.pose.orientation.z = float(object.quat[3])
                object_instance.pose.orientation.w = float(object.quat[0])

                response.object_list.append(object_instance)# sequence 타입의 객체
                aruco_marker_poses.poses.append(object_instance.pose)

            aruco_marker_poses.header.stamp = self.get_clock().now().to_msg()
            aruco_marker_poses.header.frame_id = self.camera_frame
            self.publisher_pose_array.publish(aruco_marker_poses)
            print(response.object_list)
            print(aruco_marker_poses)
        return response


    def set_camera_frame(self, camera_frame_arg:str):
        self.camera_frame = camera_frame_arg

def main():
    rclpy.init()
    object_detector = ObjectDetector()
    executor = MultiThreadedExecutor()
    executor.add_node(object_detector)
    try:
        executor.spin()
    finally:
        executor.remove_node(object_detector)
        rclpy.shutdown()

if __name__ == '__main__':
    main()