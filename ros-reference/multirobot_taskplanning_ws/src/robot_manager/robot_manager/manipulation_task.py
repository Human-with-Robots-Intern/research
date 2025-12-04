"""
계발 계획.
1. 마커의 좌표로 부터 로봇 gripper의 자세 생성하기
    마커 정보 받아오기
    마커 id 선택하기
    상대 좌표 tf 생성하기
        마커와 카메라 사이의 위치 차이

    절대 좌표 tf 계산하기
        tf 는 로봇 말단 까지만 구현
        -> 마커는 항상 존재 하지 않기 때문에 지속적으로 표현되는 tf 로는 마커의 위치를 표현하는 것이 부적합하다고 느껴짐.

        거쳐야하는 과정
            기준 원점으로부터 카메라까지의 좌표변환
                TF 를 통해 얻어옴
                테스트 단계에서는 static broadcastor를 이용하여 가상의 좌표에서 카메라를 만들기

            카메라부터 마커 사이의 좌표변환
                opencv PnP 솔버를 통해 계산한 마커의 위치 사용
            두 변환을 연결하여 기준점으로부터 마커사이의 좌표 구하기

            ->구현 후 검정 
                마커의 위치를 고정하고 로봇팔을 움직이며 여러 각도에서 마커를 촬영할 때
                기준 원점으로부터의 마커의 위치가 일정한지 Rviz를 통해 확인하기

    상대 좌표 오프셋 생성 코드 
        - 마커 위치 기억하기
        - 로봇 tf 와 기억된 마커사이의 상대 좌표 계산하기
            이때 계산하는 상대 좌표는 마커의 좌표에 곱하면 로봇팔의 좌표가 나오도록 구성하여 
            로봇 manipulation 동작 수행시, 마커에 대한 상대 위치를 편하게 계산 할 수 있도록 만들기

        - 계산된 상대 위치 정보 마커 id 와 함께 저장하기

        - ros2 서비스를 통해 마커혹은 엔드이펙터의 좌표를 기억하거나 리셋하기


    그리퍼 손 끝 기준으로 명령을 주는 방법이 필요
        마커의 절대 위치
        마커로 부터 로봇 손이 마커로부터 상대 위치 
        로봇손이 존재해야할 절대 위치

        변환 행렬 잘 복습해보기
        DH table 같은 것도 복습하면 도움이 될 듯

        moveit end-effector 의 기준점을 그리퍼의 손 끝으로 바꿀 수는 없을까?

작성자 : 김상우(kimz1121@naver.com) 권혁준(@naver.com)
마지막 수정일 : 2024-0911

"""

# ros2 기본 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

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

# 사용자 정의 파이썬 모듈
from robot_manager.moveit_client import MoveitClient

import numpy as np
# import tf.transformations as tft
from scipy.spatial.transform import Rotation as R

class ManipulationTask(MoveitClient):
    def __init__(self, node_arg):
        super().__init__(node_arg)
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
        # 오브젝트 디텍트 서비스 클라이언트 생성
        self.service_client_detect_objects = self.node.create_client(DetectObjects, "detect_objects")
        # 서비스 클라이언트가 준비 될 때 까지 대기
        while not self.service_client_detect_objects.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('service not available, waiting again...')
        self.object_list = ObjectData()

        # <ros2 tf 기능요소 정의>
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self.node)

        # <사용자 정의 변수 정의>
        # world 기준 좌표계 정의
        self.world_frame = "world"
        # 카메라 기준 좌표계 정의
        # 기본값은 "cam"으로 지정
        self.camera_frame = "cam" # 프레임은 문자열 타입으로 지정한다.

        # 임시 하드코딩 데이터 
        # 차후 json 이나 yaml 형식의 파일로 바꾸기
        self.offset_dict = {}

        # 로봇 그랩 자세 기억을 위한 맴버변수
        self.pose_pivot_object = None
        self.pose_end_effector = None

    def get_object_list(self):
        request = DetectObjects.Request()# Empty type request
        future_get_pose = self.service_client_detect_objects.call_async(request)
        rclpy.spin_until_future_complete(self.node, future_get_pose)
        self.object_num = future_get_pose.result().entity_num
        self.object_list = future_get_pose.result().object_list
        # 디버깅용 프린트
        print(self.object_num)

    def get_object_pose(self, id_arg):
        bool_is_in_list = False# 리스트 내에서 찾고자 하는 id 의 마커가 존재하지 않을 가능성도 고려
        pose_rtn = Pose()# 서비스의 리스폰스 타입은 Pose 타입
        for object in self.object_list:
            if(object.id == id_arg):
                bool_is_in_list = True
                pose_rtn = object.pose

        if (bool_is_in_list == True):
            self.do_publish_pose_debug(pose_rtn, self.camera_frame)
            print("bool_is_in_list : {}".format(bool_is_in_list))
        else:
            pose_rtn = None
        return pose_rtn

    def set_world_frame(self, world_frame_arg:str):
        self.world_frame = world_frame_arg

    def set_camera_frame(self, camera_frame_arg:str):
        self.camera_frame = camera_frame_arg

    def get_tf(self, frame_id = "cam"):
        to_frame_rel = self.world_frame
        from_frame_rel = frame_id

        t = None
        print(self.world_frame)
        print(frame_id)
        iter = 0
        while rclpy.ok():# tf 가 연속적인 연쇄 연결로 정의 되어있는 경우 여러번의 반복을 통해 tf lookup을 수행해야 한다.
            # tf topic이 업데이트 되지 않으면 
            # 토픽의 내용을 받기 위해 통신을 무한 대기하는 문제가 발생할 수 있다.
            # 토픽이 반복적으로 절달되지 못하는 환경에서 발생하는 특수한 문제로 주의가 필요하다.
            tf_future = self.tf_buffer.wait_for_transform_async(
                target_frame=to_frame_rel,
                source_frame=from_frame_rel,
                time=rclpy.time.Time()
            )

            rclpy.spin_until_future_complete(self.node, tf_future)
        
            try:
                t = self.tf_buffer.lookup_transform(
                    to_frame_rel,
                    from_frame_rel,
                    rclpy.time.Time())
            except TransformException as ex:
                # self.node.get_logger().info(
                #     f'Could not transform {to_frame_rel} to {from_frame_rel}: {ex}')
                ...

            if t is not None:
                break

            iter = iter + 1 
            
            if iter >= 100:
                break

        return t
        
        ...

    def do_publish_pose(self, pose):
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


    def do_publish_pose_debug(self, pose, frame = "world", pub_id = 0):
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

    def do_convert_transform_to_pose(self, tf_arg:Transform):
        pose_rtn = Pose()
        pose_rtn.position.x = tf_arg.translation.x
        pose_rtn.position.y = tf_arg.translation.y
        pose_rtn.position.z = tf_arg.translation.z

        pose_rtn.orientation.x = tf_arg.rotation.x
        pose_rtn.orientation.y = tf_arg.rotation.y
        pose_rtn.orientation.z = tf_arg.rotation.z
        pose_rtn.orientation.w = tf_arg.rotation.w
        return pose_rtn

    def do_convert_matrix_to_pose(self, mat_arg):
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

    def do_calc_abs_pose(self, frame_arg:Pose, target_arg:Pose):
        mat_frame = self.do_convert_pose_to_matrix(frame_arg)
        mat_target = self.do_convert_pose_to_matrix(target_arg)

        mat_rtn = np.dot(mat_frame, mat_target)
        print(mat_rtn)
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn)
        return pose_rtn
        ...

    def do_calc_relative_pose(self, pose_source_arg:Pose, pose_target_arg:Pose):
        mat_pose_source = self.do_convert_pose_to_matrix(pose_source_arg)# wolrd -> source
        mat_pose_target = self.do_convert_pose_to_matrix(pose_target_arg)# wolrd -> target

        mat_pose_source_inverse = np.linalg.inv(mat_pose_source)# 선형대수 모듈의 역행렬을 가져옴
        # source -> wolrd
        mat_rtn = np.dot(mat_pose_source_inverse, mat_pose_target)
        
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn)
        print("===================")
        print(mat_pose_source)
        print(mat_pose_target)

        print("===================")
        print(mat_pose_source_inverse)
        print(mat_rtn)
        print(pose_rtn)
        
        return pose_rtn

    def get_abs_object_pose_once(self, id_arg:int, camera_frame_arg = "cam"):
        pose_object_abs_rtn = None 
        # 초기 값은 None으로 설정하여 
        # 절대 좌표를 얻지 못한경우 None을 그대로 반환
        t = self.get_tf("cam")# TranslationStamped 타입을 반환
        print("====================")
        print("id_arg : {}".format(id_arg))
        if t is not None:
            pose_transform = self.do_convert_transform_to_pose(t.transform)

            self.get_object_list()# 카메라에 촬영된 마커를 나타내는 오브젝트 리스트 받아오기
            pose_object = self.get_object_pose(id_arg)# 특정 오브젝트 만의 포즈 받아오기
            print(pose_object)
            self.do_publish_pose_debug(pose_transform, "world", 1)
            if pose_object is not None:
                pose_object_abs_rtn = self.do_calc_abs_pose(pose_transform, pose_object)

        return pose_object_abs_rtn

    # def get_abs_object_pose(self, id_arg:int, camera_frame_arg = "cam"):

    #     이 부분에서 pose_object_abs_once를 10번 해서 평균을 내고, 표준편차를 구해서 일정 표준편차를 넘는 값들은 배제할거야. 그 뒤 다시 평균을 구한 값을 return 해주고 싶어. pose는 총 7개로 이뤄져있는데, 앞에껀 로봇팔의 xyz좌표이고, 뒤에껀 로봇손의 쿼터니안을 이루는 4가지 변수야. 이를 활용해서 잘 코드를 짜줘.
    #         pose_object_abs_once = self.get_abs_object_pose(id_arg, camera_frame_arg)
        
    #     return #평균구한값

#import tf.transformations as tft 버전
    # def get_abs_object_pose(self, id_arg: int, camera_frame_arg="cam"):
    #     poses = []
    #     num_samples = 10
        
    #     for _ in range(num_samples):
    #         pose = self.get_abs_object_pose_once(id_arg, camera_frame_arg)
    #         if pose:
    #             poses.append(pose)
        
    #     if not poses:
    #         return None

    #     # 평균 및 표준편차 계산
    #     positions = np.array([(p.position.x, p.position.y, p.position.z) for p in poses])
    #     orientations = np.array([(p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w) for p in poses])
        
    #     # 위치의 평균과 표준편차 계산
    #     mean_position = np.mean(positions, axis=0)
    #     std_position = np.std(positions, axis=0)
        
    #     # 회전 행렬로 변환 (쿼터니안을 회전 행렬로 변환)
    #     rotation_matrices = np.array([tft.quaternion_matrix(q)[:3, :3] for q in orientations])
        
    #     # 회전 행렬의 평균과 표준편차 계산
    #     mean_rotation_matrix = np.mean(rotation_matrices, axis=0)
    #     std_rotation_matrix = np.std(rotation_matrices, axis=0)
        
    #     # 위치와 회전 행렬 모두에서 표준편차가 너무 큰 값을 제외
    #     valid_indices = np.all(np.abs(positions - mean_position) < 2 * std_position, axis=1) & \
    #                     np.all(np.abs(rotation_matrices - mean_rotation_matrix) < 2 * std_rotation_matrix, axis=(1, 2))
        
    #     valid_positions = positions[valid_indices]
    #     valid_rotation_matrices = rotation_matrices[valid_indices]
        
    #     if valid_positions.size == 0 or valid_rotation_matrices.shape[0] == 0:
    #         return None
        
    #     # 유효한 값들에 대해 최종 평균 계산
    #     final_mean_position = np.mean(valid_positions, axis=0)
    #     final_mean_rotation_matrix = np.mean(valid_rotation_matrices, axis=0)
        
    #     # 최종 평균 회전 행렬을 쿼터니안으로 변환
    #     final_mean_orientation = tft.quaternion_from_matrix(final_mean_rotation_matrix)
        
    #     # Pose 객체로 변환
    #     pose_rtn = Pose()
    #     pose_rtn.position.x, pose_rtn.position.y, pose_rtn.position.z = final_mean_position
    #     pose_rtn.orientation.x, pose_rtn.orientation.y, pose_rtn.orientation.z, pose_rtn.orientation.w = final_mean_orientation
        
    #     return pose_rtn

    # def get_abs_object_pose(self, id_arg: int, camera_frame_arg="cam"):
    #     poses = []
    #     num_samples = 10
        
    #     for _ in range(num_samples):
    #         pose = self.get_abs_object_pose_once(id_arg, camera_frame_arg)
    #         if pose:
    #             poses.append(pose)
        
    #     if not poses:
    #         return None

    #     # 평균 및 표준편차 계산
    #     positions = np.array([(p.position.x, p.position.y, p.position.z) for p in poses])
    #     orientations = np.array([(p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w) for p in poses])
        
    #     # 위치의 평균과 표준편차 계산
    #     mean_position = np.mean(positions, axis=0)
    #     std_position = np.std(positions, axis=0)
        
    #     # 쿼터니안을 회전 행렬로 변환 (scipy 사용)
    #     rotation_matrices = np.array([R.from_quat(q).as_matrix() for q in orientations])
        
    #     # 회전 행렬의 평균과 표준편차 계산
    #     mean_rotation_matrix = np.mean(rotation_matrices, axis=0)
    #     std_rotation_matrix = np.std(rotation_matrices, axis=0)
        
    #     # 위치와 회전 행렬 모두에서 표준편차가 너무 큰 값을 제외
    #     valid_indices = np.all(np.abs(positions - mean_position) < 2 * std_position, axis=1) & \
    #                     np.all(np.abs(rotation_matrices - mean_rotation_matrix) < 2 * std_rotation_matrix, axis=(1, 2))
        
    #     valid_positions = positions[valid_indices]
    #     valid_rotation_matrices = rotation_matrices[valid_indices]
        
    #     if valid_positions.size == 0 or valid_rotation_matrices.shape[0] == 0:
    #         return None
        
    #     # 유효한 값들에 대해 최종 평균 계산
    #     final_mean_position = np.mean(valid_positions, axis=0)
    #     final_mean_rotation_matrix = np.mean(valid_rotation_matrices, axis=0)
        
    #     # 최종 평균 회전 행렬을 쿼터니안으로 변환
    #     final_mean_orientation = R.from_matrix(final_mean_rotation_matrix).as_quat()
        
    #     # Pose 객체로 변환
    #     pose_rtn = Pose()
    #     pose_rtn.position.x, pose_rtn.position.y, pose_rtn.position.z = final_mean_position
    #     pose_rtn.orientation.x, pose_rtn.orientation.y, pose_rtn.orientation.z, pose_rtn.orientation.w = final_mean_orientation
        
    #     return pose_rtn

    def get_abs_object_pose(self, id_arg: int, camera_frame_arg="cam"):
        poses = []
        num_samples = 10
        
        for _ in range(num_samples):
            pose = self.get_abs_object_pose_once(id_arg, camera_frame_arg)
            if pose:
                poses.append(pose)
        
        if not poses:
            return None

        # 평균 및 표준편차 계산
        positions = np.array([(p.position.x, p.position.y, p.position.z) for p in poses])
        orientations = np.array([(p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w) for p in poses])
        
        # 위치의 평균과 표준편차 계산
        mean_position = np.mean(positions, axis=0)
        std_position = np.std(positions, axis=0)

        # 쿼터니안을 RPY로 변환
        euler_angles = np.array([R.from_quat(q).as_euler('xyz') for q in orientations])  # RPY로 변환
        
        # RPY 각도의 평균과 표준편차 계산
        mean_euler = np.mean(euler_angles, axis=0)
        std_euler = np.std(euler_angles, axis=0)
        
        # 위치와 RPY 모두에서 표준편차가 너무 큰 값을 제외
        valid_indices = np.all(np.abs(positions - mean_position) < 2 * std_position, axis=1) & \
                        np.all(np.abs(euler_angles - mean_euler) < 2 * std_euler, axis=1)
        
        valid_positions = positions[valid_indices]
        valid_euler_angles = euler_angles[valid_indices]
        
        if valid_positions.size == 0 or valid_euler_angles.shape[0] == 0:
            return None
        
        # 유효한 값들에 대해 최종 평균 계산
        final_mean_position = np.mean(valid_positions, axis=0)
        final_mean_euler = np.mean(valid_euler_angles, axis=0)
        
        # 최종 평균 RPY를 쿼터니안으로 변환
        final_mean_orientation = R.from_euler('xyz', final_mean_euler).as_quat()
        
        # Pose 객체로 변환
        pose_rtn = Pose()
        pose_rtn.position.x, pose_rtn.position.y, pose_rtn.position.z = final_mean_position
        pose_rtn.orientation.x, pose_rtn.orientation.y, pose_rtn.orientation.z, pose_rtn.orientation.w = final_mean_orientation
        
        return pose_rtn

    def do_calc_pose_offset(self):
        # 로봇 팔과 마커사이의 상대 위치를 계산하는 함수
        # 기준 좌표는 마커, 목표 좌표는 로봇팔의 좌표
        pose_offset = None
        if (self.pose_pivot_object is not None) and (self.pose_end_effector is not None):
            pose_offset = self.do_calc_relative_pose(self.pose_pivot_object, self.pose_end_effector)
        return pose_offset

    def set_pose_pivot_obejct(self, id_arg, camera_frame_arg = "cam"):
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

    def set_pose_end_effector(self, end_effector_frame_arg = "ee_link"):
        success = False # 초기 상태에서는 False로 정의하여 업데이트 되지 못한 경우 그대로 False를 반환
        transform_end_effector = self.get_tf(end_effector_frame_arg)
        if transform_end_effector is not None:
            self.pose_end_effector = self.do_convert_transform_to_pose(transform_end_effector.transform)
            success = True
        else:
            self.pose_end_effector = None
            success = False
        return success

    def add_pose_sequence(self, object_id: int, action_id: int, sequence_id: int, pose_offset: Pose, is_relative: bool):
        if object_id not in self.offset_dict:
            self.offset_dict[object_id] = {}
        if action_id not in self.offset_dict[object_id]:
            self.offset_dict[object_id][action_id] = {}
        self.offset_dict[object_id][action_id][sequence_id] = {'pose': pose_offset, 'is_relative': is_relative}
        self.save_pose_data_to_json()

    def get_pose_sequence(self, object_id: int, action_id: int, sequence_id: int):
        if object_id in self.offset_dict and action_id in self.offset_dict[object_id] and sequence_id in self.offset_dict[object_id][action_id]:
            return self.offset_dict[object_id][action_id][sequence_id]
        else:
            return None

    def save_pose_data_to_json(self, filename="planner_instruction/marker_pose.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        for object_id, actions in self.offset_dict.items():
            if str(object_id) not in existing_data:
                existing_data[str(object_id)] = {}
            for action_id, sequences in actions.items():
                if str(action_id) not in existing_data[str(object_id)]:
                    existing_data[str(object_id)][str(action_id)] = {}
                for sequence_id, data in sequences.items():
                    pose_offset = data['pose']
                    is_relative = data['is_relative']
                    existing_data[str(object_id)][str(action_id)][str(sequence_id)] = {
                        'position': {
                            'x': pose_offset.position.x,
                            'y': pose_offset.position.y,
                            'z': pose_offset.position.z
                        },
                        'orientation': {
                            'x': pose_offset.orientation.x,
                            'y': pose_offset.orientation.y,
                            'z': pose_offset.orientation.z,
                            'w': pose_offset.orientation.w
                        },
                        'is_relative': is_relative
                    }

        with open(filename, 'w') as file:
            json.dump(existing_data, file, indent=4)

    def load_pose_data_from_json(self, filename="planner_instruction/marker_pose.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                data = json.load(file)
                for object_id, actions in data.items():
                    self.offset_dict[int(object_id)] = {}
                    for action_id, sequences in actions.items():
                        self.offset_dict[int(object_id)][int(action_id)] = {}
                        for sequence_id, pose_data in sequences.items():
                            pose_offset = Pose()
                            pose_offset.position.x = pose_data['position']['x']
                            pose_offset.position.y = pose_data['position']['y']
                            pose_offset.position.z = pose_data['position']['z']
                            pose_offset.orientation.x = pose_data['orientation']['x']
                            pose_offset.orientation.y = pose_data['orientation']['y']
                            pose_offset.orientation.z = pose_data['orientation']['z']
                            pose_offset.orientation.w = pose_data['orientation']['w']
                            is_relative = pose_data['is_relative']
                            self.offset_dict[int(object_id)][int(action_id)][int(sequence_id)] = {'pose': pose_offset, 'is_relative': is_relative}

    def do_calc_end_effector_position(self, pose_object:Pose, grap_offset:Pose):
        # pose 를 계산 가능한 형태인 매트릭스 형태로 변환
        mat_pose_object = self.do_convert_pose_to_matrix(pose_object)
        mat_grap_offset = self.do_convert_pose_to_matrix(grap_offset)

        # 마커로 부터 오프셋 만큼의 좌표변환을 수행
        mat_rtn = np.dot(mat_pose_object, mat_grap_offset)
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn) 

        return pose_rtn
        ...

