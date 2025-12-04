"""
계발 계획.
1. 마커의 좌표로 부터 로봇 gripper의 자세 생성하기
    오브젝트 정보 받아오기
    오브젝트 id 선택하기
    상대 좌표 tf 생성하기
        마커와 카메라 사이의 위치 차이

    절대 좌표 tf 계산하기
        tf 는 로봇 말단 까지만 구현
        -> 마커는 항상 존재 하지 않기 때문에 지속적으로 표현되는 tf 로는 마커의 위치를 표현하는 것이 부적합하다고 느껴짐.

        거쳐야하는 과정
            기준 원점으로부터 카메라까지의 좌표변환
                TF 를 통해 얻어옴
                테스트 단계에서는 static broadcastor를 이용하여 가상의 좌표에서 카메라를 만들기

            카메라부터 오브젝트 사이의 좌표변환
                opencv PnP 솔버를 통해 계산한 마커의 위치 사용
            두 변환을 연결하여 기준점으로부터 마커사이의 좌표 구하기

            ->구현 후 검정 
                마커의 위치를 고정하고 로봇팔을 움직이며 여러 각도에서 마커를 촬영할 때
                기준 원점으로부터의 마커의 위치가 일정한지 Rviz를 통해 확인하기

    상대 좌표 오프셋 생성 코드 
        - 오브젝트 위치 기억하기
        - 로봇 tf 와 기억된 마커사이의 상대 좌표 계산하기
            이때 계산하는 상대 좌표는 마커의 좌표에 곱하면 로봇팔의 좌표가 나오도록 구성하여 
            로봇 manipulation 동작 수행시, 마커에 대한 상대 위치를 편하게 계산 할 수 있도록 만들기

        - 계산된 상대 위치 정보 오브젝트 id 와 함께 저장하기

        - ros2 서비스를 통해 마커혹은 엔드이펙터의 좌표를 기억하거나 리셋하기


    그리퍼 손 끝 기준으로 명령을 주는 방법이 필요
        마커의 절대 위치
        마커로 부터 로봇 손이 마커로부터 상대 위치 
        로봇손이 존재해야할 절대 위치

        변환 행렬 잘 복습해보기
        DH table 같은 것도 복습하면 도움이 될 듯

        moveit end-effector 의 기준점을 그리퍼의 손 끝으로 바꿀 수는 없을까?

"""

# ros2 기본 모듈
import rclpy
from rclpy.node import Node

from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

# ros2 기본 메시지 타입
from geometry_msgs.msg import Pose
from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Transform
from geometry_msgs.msg import TransformStamped

# ros2 사용자정의 메시지 타입
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 파이썬 모듈
import transforms3d
import numpy as np
import json
import os

class PoseCalcModule():
    def __init__(self, node_arg:Node):
        self.node = node_arg

        # <맴버 변수 정의>
        # <ROS2 기능용소 정의>
        # 디버깅용 토픽 퍼블리셔 정의
        self.publisher_pose = self.node.create_publisher(PoseStamped, "pose_manipulation", 10)
        self.publisher_pose_debug_0 = self.node.create_publisher(PoseStamped, "pose_manipulation_debug_0", 10)
        self.publisher_pose_debug_1 = self.node.create_publisher(PoseStamped, "pose_manipulation_debug_1", 10)
        self.publisher_pose_debug_2 = self.node.create_publisher(PoseStamped, "pose_manipulation_debug_2", 10)
        self.publisher_pose_debug_3 = self.node.create_publisher(PoseStamped, "pose_manipulation_debug_3", 10)
        self.publisher_pose_debug_4 = self.node.create_publisher(PoseStamped, "pose_manipulation_debug_4", 10)
        # # 오브젝트 디텍트 서비스 클라이언트 생성
        # self.service_client_detect_objects = self.node.create_client(DetectObjects, "detect_objects")
        # # 서비스 클라이언트가 준비 될 때 까지 대기
        # while not self.service_client_detect_objects.wait_for_service(timeout_sec=1.0):
        #     self.node.get_logger().info("service not available, waiting again...")

        # <ros2 tf 기능요소 정의>
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self.node)

        # <사용자 정의 변수 정의>
        # world 기준 좌표계 정의
        self.world_frame:str = "world"
        # 카메라 기준 좌표계 정의
        # 기본값은 "cam"으로 지정
        self.camera_frame:str = "cam" # 프레임은 문자열 타입으로 지정한다.
        self.end_effector_frame:str = None # 프레임은 문자열 타입으로 지정한다.

        # json 파일에서 읽어온 데이터를 메모리에 로드해 두는 목적의 딕셔너리 객체 
        self.manipulation_data_dict = {}

        # 로봇 그랩 자세 기억을 위한 맴버변수
        self.pose_pivot_object:Pose = None
        self.pose_end_effector:Pose = None
        
        # object data 관리용 변수 
        self.object_num:int = None
        self.object_list:list[ObjectData] = None

    def set_object_list(self, object_data_arg:DetectObjects.Response): # 앞으로는 값으로 받아올 예정, 자신이 직접 받아오지 않고 함수의 인자로 전달 받을 예정
        self.object_num = object_data_arg.entity_num
        self.object_list = object_data_arg.object_list
        # 디버깅용 프린트
        # print(self.object_num)

    def clear_object_list(self):
        self.object_num = None
        self.object_list = None

    def get_object_pose(self, id_arg):# object_list 에서 지정한 아이디의 오브젝트 정보를 추출하는 함수
        bool_is_in_list = False# 리스트 내에서 찾고자 하는 id 의 마커가 존재하지 않을 가능성도 고려
        pose_rtn = Pose()# 서비스의 리스폰스 타입은 Pose 타입
        for object in self.object_list:
            if(object.id == id_arg):
                bool_is_in_list = True
                pose_rtn = object.pose
        
        if (bool_is_in_list == True):
            self.do_publish_pose_debug(pose_rtn, self.camera_frame)
            # print("bool_is_in_list : {}".format(bool_is_in_list))
        else:
            pose_rtn = None
        return pose_rtn # the position of obj what we want (cam->obj)

    def set_world_frame(self, world_frame_arg:str):
        self.world_frame = world_frame_arg

    def set_camera_frame(self, camera_frame_arg:str):
        self.camera_frame = camera_frame_arg

    def set_end_effector_frame(self, end_effector_frame_arg:str):
        self.end_effector_frame = end_effector_frame_arg

    def get_tf(self, frame_id = "cam") -> TransformStamped:
        to_frame_rel = self.world_frame
        from_frame_rel = frame_id

        tf_stamped_instance = None
        print(self.world_frame)
        print(frame_id)
        
        try: 
            tf_stamped_instance = self.tf_buffer.lookup_transform(# loopup transform : get position (map-> (somewhere))
                to_frame_rel,
                from_frame_rel,
                rclpy.time.Time())
        except TransformException as ex:
            self.node.get_logger().info(
                f"Could not transform {to_frame_rel} to {from_frame_rel}: {ex}")

        return tf_stamped_instance # map-> cam
        
        ...

    def do_publish_pose(self, pose:Pose):
        print(type(pose))
        if pose is not None:
            pose_stamped_msg = PoseStamped()
            pose_stamped_msg.header.frame_id = self.world_frame
            pose_stamped_msg.header.stamp = self.node.get_clock().now().to_msg()
            pose_stamped_msg.pose = pose
            self.publisher_pose.publish(pose_stamped_msg)
            print("pose is published")
        else:
            print("pose wasn't published")


    def do_publish_pose_debug(self, pose:Pose, pub_id:int = 0, frame:str = "world"):
        print(type(pose))
        if pose is not None:
            pose_stamped_msg = PoseStamped()
            pose_stamped_msg.header.frame_id = frame
            pose_stamped_msg.header.stamp = self.node.get_clock().now().to_msg()
            pose_stamped_msg.pose = pose
            if pub_id == 0:
                self.publisher_pose_debug_0.publish(pose_stamped_msg)
            elif pub_id == 1:
                self.publisher_pose_debug_1.publish(pose_stamped_msg)
            elif pub_id == 2:
                self.publisher_pose_debug_2.publish(pose_stamped_msg)
            elif pub_id == 3:
                self.publisher_pose_debug_3.publish(pose_stamped_msg)
            elif pub_id == 4:
                self.publisher_pose_debug_4.publish(pose_stamped_msg)
            print("pose is published")
        else:
            print("pose wasn't published")

    def do_convert_transform_to_pose(self, tf_arg:Transform) -> Pose:
        pose_rtn = Pose()
        pose_rtn.position.x = tf_arg.translation.x
        pose_rtn.position.y = tf_arg.translation.y
        pose_rtn.position.z = tf_arg.translation.z

        pose_rtn.orientation.x = tf_arg.rotation.x
        pose_rtn.orientation.y = tf_arg.rotation.y
        pose_rtn.orientation.z = tf_arg.rotation.z
        pose_rtn.orientation.w = tf_arg.rotation.w
        return pose_rtn

    def do_convert_matrix_to_pose(self, mat_arg) -> Pose:
        pose_rtn = Pose()
        trans, rot, zoom, share = transforms3d.affines.decompose(mat_arg)

        quat = transforms3d.quaternions.mat2quat(rot)

        pose_rtn.position.x = trans[0]
        pose_rtn.position.y = trans[1]
        pose_rtn.position.z = trans[2]

        pose_rtn.orientation.w = quat[0]
        pose_rtn.orientation.x = quat[1]
        pose_rtn.orientation.y = quat[2]
        pose_rtn.orientation.z = quat[3]
        return pose_rtn

    def do_convert_pose_to_matrix(self, pose_arg:Pose):
        mat_pose_trans = [pose_arg.position.x, pose_arg.position.y, pose_arg.position.z]
        # quat2mat 연산은 정해진 범위를 벗어난 값을 갖는 형태의 잘못된 쿼터니언이 입력되면
        # 그 출력인 행렬도 잘못된 값이 생성된다
        # 따라서 항상 올바른 형태의 쿼터니언을 입력해 주는 것이 중요하다.
        mat_pose_rot = transforms3d.quaternions.quat2mat([pose_arg.orientation.w, pose_arg.orientation.x, pose_arg.orientation.y, pose_arg.orientation.z])
        mat_pose_rtn = transforms3d.affines.compose(mat_pose_trans, mat_pose_rot, np.ones(3))
        return mat_pose_rtn

    def do_calc_frame_stack(self, pose_pivot_arg:Pose, pose_target_arg:Pose) -> Pose:
        mat_pivot_frame = self.do_convert_pose_to_matrix(pose_pivot_arg)
        mat_target_frame = self.do_convert_pose_to_matrix(pose_target_arg)

        mat_rtn = np.dot(mat_pivot_frame, mat_target_frame)
        # print(mat_rtn)
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn)
        return pose_rtn
        ...

    def do_calc_frame_offset(self, pose_pivot_arg:Pose, pose_target_arg:Pose):
        mat_pivot_frame = self.do_convert_pose_to_matrix(pose_pivot_arg)# wolrd -> source
        mat_target_frame = self.do_convert_pose_to_matrix(pose_target_arg)# wolrd -> target

        mat_pivot_frame_inverse = np.linalg.inv(mat_pivot_frame)# 선형대수 모듈의 역행렬을 가져옴
        # source -> wolrd
        mat_rtn = np.dot(mat_pivot_frame_inverse, mat_target_frame)
        
        frame_offset_rtn = self.do_convert_matrix_to_pose(mat_rtn)
        # print("===================")
        # print(mat_pivot_frame)
        # print(mat_target_frame)

        # print("===================")
        # print(mat_pivot_frame_inverse)
        # print(mat_rtn)
        # print(frame_offset_rtn)
        
        return frame_offset_rtn
    
    def get_abs_object_pose(self, id_arg:int, camera_frame_arg:str = "cam") -> Pose:
        pose_object_abs_rtn = None 
        # 초기 값은 None으로 설정하여 
        # 절대 좌표를 얻지 못한경우 None을 그대로 반환
        tf_stamped_instance = self.get_tf(camera_frame_arg)# TranslationStamped 타입을 반환
        if tf_stamped_instance is not None:
            pose_transform = self.do_convert_transform_to_pose(tf_stamped_instance.transform) # posiotion(map->cam)
            if self.object_list is not None:
                pose_object = self.get_object_pose(id_arg)# 특정 오브젝트 만의 포즈 받아오기
                # print(pose_object)
                # self.do_publish_pose(pose_transform)
                if pose_object is not None:
                    pose_object_abs_rtn = self.do_calc_frame_stack(pose_transform, pose_object)

        return pose_object_abs_rtn # the location of obj ( map -> obj)
    
    def set_pose_pivot_obejct(self, id_arg, camera_frame_arg:str = "cam"):
        # 마커의 절대좌표(world 기준 좌표)를 기억하는 코드 
        # 마커의 위치가 저장된 이후에 마커를 이동하면 실제 마커의 위치와 저장된 마커위치 사이의 오차가 발생하므로 유의할 것
        success = False # 초기 상태에서는 False로 정의하여 업데이트 되지 못한 경우 그대로 False를 반환
        pose_object_abs = self.get_abs_object_pose(id_arg, camera_frame_arg)
        if pose_object_abs is not None:
            self.pose_pivot_object = pose_object_abs
            success = True
        else:
            self.pose_pivot_object = None
            success = False
        return success
    
    def get_pose_pivot_object(self):
        return self.pose_pivot_object

    def set_pose_end_effector(self, end_effector_frame_arg:str = None):
        end_effector_frame = end_effector_frame_arg
        if end_effector_frame is None:
            end_effector_frame = self.end_effector_frame
        success = False # 초기 상태에서는 False로 정의하여 업데이트 되지 못한 경우 그대로 False를 반환
        tf_stamped_end_effector = self.get_tf(end_effector_frame)
        if tf_stamped_end_effector is not None:
            self.pose_end_effector = self.do_convert_transform_to_pose(tf_stamped_end_effector.transform)
            success = True
        else:
            self.pose_end_effector = None
            success = False
        return success
    
    def get_pose_end_effector(self, end_effector_frame_arg:str=None):# object_list 에서 지정한 아이디의 오브젝트 정보를 추출하는 함수
        end_effector_frame = end_effector_frame_arg
        if end_effector_frame is None:
            end_effector_frame = self.end_effector_frame
        tf_stamped_end_effector = self.get_tf(end_effector_frame)
        if tf_stamped_end_effector is not None:
            self.pose_end_effector = self.do_convert_transform_to_pose(tf_stamped_end_effector.transform)
        else:
            self.pose_end_effector = None
        return self.pose_end_effector
    
    def set_manipulation_data(self, object_a_id: int, object_b_id: int, action_id: int, sequence_id: int, sub_action: str, pose_offset: Pose, is_relative: bool):
        if object_a_id not in self.manipulation_data_dict:
            self.manipulation_data_dict[object_a_id] = {}
        if object_b_id not in self.manipulation_data_dict[object_a_id]:
            self.manipulation_data_dict[object_a_id][object_b_id] = {}
        if action_id not in self.manipulation_data_dict[object_a_id][object_b_id]:
            self.manipulation_data_dict[object_a_id][object_b_id][action_id] = {}
        if sequence_id not in self.manipulation_data_dict[object_a_id][object_b_id][action_id]:
            self.manipulation_data_dict[object_a_id][object_b_id][action_id][sequence_id] = {}
        self.manipulation_data_dict[object_a_id][object_b_id][action_id][sequence_id] = {"sub_action": sub_action, "pose": pose_offset, "is_relative": is_relative}

        # print(self.manipulation_data_dict)

    def get_manipulation_data(self, object_a_id: int, object_b_id: int, action_id: int, sequence_id: int) -> dict:
        if (object_a_id in self.manipulation_data_dict and
            object_b_id in self.manipulation_data_dict[object_a_id] and
            action_id in self.manipulation_data_dict[object_a_id][object_b_id] and
            sequence_id in self.manipulation_data_dict[object_a_id][object_b_id][action_id]):
            return self.manipulation_data_dict[object_a_id][object_b_id][action_id][sequence_id]
        else:
            return None


    def save_manipulation_data_to_json(self, filename="data/object_pose.json"):
        # print("save_test : {}".format(os.path.exists(filename)))
        if os.path.exists(filename):
            with open(filename, "r") as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        for object_a_id, object_b_dict in self.manipulation_data_dict.items():
            if str(object_a_id) not in existing_data:
                existing_data[str(object_a_id)] = {}
            for object_b_id, action_dict in object_b_dict.items():
                if str(object_b_id) not in existing_data[str(object_a_id)]:
                    existing_data[str(object_a_id)][str(object_b_id)] = {}
                for action_id, sequence_dict in action_dict.items():
                    if str(action_id) not in existing_data[str(object_a_id)][str(object_b_id)]:
                        existing_data[str(object_a_id)][str(object_b_id)][str(action_id)] = {}
                    for sequence_id, data in sequence_dict.items():
                        sub_action:str = data["sub_action"]
                        pose_offset:Pose = data["pose"]
                        is_relative:bool = data["is_relative"]
                        existing_data[str(object_a_id)][str(object_b_id)][str(action_id)][str(sequence_id)] = {
                            "sub_action": sub_action,
                            "position": {
                                "x": pose_offset.position.x,
                                "y": pose_offset.position.y,
                                "z": pose_offset.position.z
                            },
                            "orientation": {
                                "x": pose_offset.orientation.x,
                                "y": pose_offset.orientation.y,
                                "z": pose_offset.orientation.z,
                                "w": pose_offset.orientation.w
                            },
                            "is_relative": is_relative
                        }

        with open(filename, "w") as file:
            json.dump(existing_data, file, indent=4)

    def load_manipulation_data_from_json(self, filename="data/object_pose.json"):
        if os.path.exists(filename):
            with open(filename, "r") as file:
                data = json.load(file)
                # print("load_test : {}".format(data))
                for object_a_id, object_b_dict in data.items():
                    self.manipulation_data_dict[int(object_a_id)] = {}
                    for object_b_id, action_dict in object_b_dict.items():
                        self.manipulation_data_dict[int(object_a_id)][int(object_b_id)] = {}
                        for action_id, sequence_dict in action_dict.items():
                            self.manipulation_data_dict[int(object_a_id)][int(object_b_id)][int(action_id)] = {}
                            for sequence_id, data in sequence_dict.items():
                                sub_action:str = data["sub_action"]
                                pose_offset = Pose()
                                pose_offset.position.x = data["position"]["x"]
                                pose_offset.position.y = data["position"]["y"]
                                pose_offset.position.z = data["position"]["z"]
                                pose_offset.orientation.x = data["orientation"]["x"]
                                pose_offset.orientation.y = data["orientation"]["y"]
                                pose_offset.orientation.z = data["orientation"]["z"]
                                pose_offset.orientation.w = data["orientation"]["w"]
                                is_relative:bool = data["is_relative"]
                                self.manipulation_data_dict[int(object_a_id)][int(object_b_id)][int(action_id)][int(sequence_id)] = {"sub_action": sub_action, "pose": pose_offset, "is_relative": is_relative}

    def do_calc_offset_data(self):
        # 저장된 좌표 데이터로부터 필요한 정보인 pose offset 데이터를 구하는 과정 
        pose_offset = None
        if (self.pose_pivot_object is not None) and (self.pose_end_effector is not None):
            pose_offset = self.do_calc_frame_offset(self.pose_pivot_object, self.pose_end_effector)
        return pose_offset

    def do_calc_end_effector_position(self, pose_object:Pose, pose_offset:Pose):
        # pose 를 계산 가능한 형태인 매트릭스 형태로 변환
        mat_pose_object = self.do_convert_pose_to_matrix(pose_object)
        mat_grap_offset = self.do_convert_pose_to_matrix(pose_offset)

        # 마커로 부터 오프셋 만큼의 좌표변환을 수행
        mat_rtn = np.dot(mat_pose_object, mat_grap_offset)
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn) 

        return pose_rtn
        ...

