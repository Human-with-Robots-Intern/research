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

class Manipulation(Node):
    def __init__(self):
        super().__init__("manipulation_node")

        # <맴버 변수 정의>
        # <ROS2 기능용소 정의>
        # 디버깅용 토픽 퍼블리셔 정의
        self.publisher_pose = self.create_publisher(PoseStamped, "pose_manipulation", 10)
        self.publisher_pose_debug_0 = self.create_publisher(PoseStamped, "pose_manipulation_debug_0", 10)
        self.publisher_pose_debug_1 = self.create_publisher(PoseStamped, "pose_manipulation_debug_1", 10)
        self.publisher_pose_debug_2 = self.create_publisher(PoseStamped, "pose_manipulation_debug_2", 10)
        self.publisher_pose_debug_3 = self.create_publisher(PoseStamped, "pose_manipulation_debug_3", 10)
        self.publisher_pose_debug_4 = self.create_publisher(PoseStamped, "pose_manipulation_debug_4", 10)
        # 오브젝트 디텍트 서비스 클라이언트 생성
        self.service_client_detect_objects = self.create_client(DetectObjects, "detect_objects")
        # 서비스 클라이언트가 준비 될 때 까지 대기
        while not self.service_client_detect_objects.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.object_list = ObjectData()

        # <ros2 tf 기능요소 정의>
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # <사용자 정의 변수 정의>
        # world 기준 좌표계 정의
        self.world_frame = "map"
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
        rclpy.spin_until_future_complete(self, future_get_pose)
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

            rclpy.spin_until_future_complete(self, tf_future)
        
            try:
                t = self.tf_buffer.lookup_transform(
                    to_frame_rel,
                    from_frame_rel,
                    rclpy.time.Time())
            except TransformException as ex:
                self.get_logger().info(
                    f'Could not transform {to_frame_rel} to {from_frame_rel}: {ex}')
                            
            if t is not None:
                break

            iter = iter + 1 
            
            if iter >= 10:
                break

        return t
        
        ...

    def do_publish_pose(self, pose):
        print(type(pose))
        if pose is not None:
            pose_stamped_msg = PoseStamped()
            pose_stamped_msg.header.frame_id = self.world_frame
            pose_stamped_msg.header.stamp = self.get_clock().now().to_msg()
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
            pose_stamped_msg.header.stamp = self.get_clock().now().to_msg()
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

    def get_abs_object_pose(self, id_arg:int, camera_frame_arg = "cam"):
        pose_object_abs_rtn = None 
        # 초기 값은 None으로 설정하여 
        # 절대 좌표를 얻지 못한경우 None을 그대로 반환
        t = self.get_tf("cam")# TranslationStamped 타입을 반환
        if t is not None:
            pose_transform = self.do_convert_transform_to_pose(t.transform)

            self.get_object_list()# 카메라에 촬영된 마커를 나타내는 오브젝트 리스트 받아오기
            pose_object = self.get_object_pose(4)# 특정 오브젝트 만의 포즈 받아오기
            print(pose_object)
            # self.do_publish_pose(pose_transform)
            if pose_object is not None:
                pose_object_abs_rtn = self.do_calc_abs_pose(pose_transform, pose_object)

        return pose_object_abs_rtn

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

    def set_pose_offset(self, object_id: int, sequence_id: int, pose_offset: Pose, filename = "planner_instruction/marker_pose.json"):
            if object_id not in self.offset_dict:
                self.offset_dict[object_id] = {}
            self.offset_dict[object_id][sequence_id] = pose_offset
            self.save_offsets_to_json(filename)

    def get_pose_offset(self, object_id: int, sequence_id: int):
        if object_id in self.offset_dict and sequence_id in self.offset_dict[object_id]:
            return self.offset_dict[object_id][sequence_id]
        else:
            return None

    def save_offsets_to_json(self, filename="planner_instruction/marker_pose.json"):
        # 파일이 존재하는 경우 기존 데이터를 불러오기
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        # 기존 데이터를 업데이트
        for object_id, sequences in self.offset_dict.items():
            if str(object_id) not in existing_data:
                existing_data[str(object_id)] = {}
            for sequence_id, pose_offset in sequences.items():
                existing_data[str(object_id)][str(sequence_id)] = {
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
                    }
                }

        # 업데이트된 데이터를 파일에 저장
        with open(filename, 'w') as file:
            json.dump(existing_data, file, indent=4)

    def load_offsets_from_json(self, filename="planner_instruction/marker_pose.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                data = json.load(file)
                for object_id, sequences in data.items():
                    self.offset_dict[int(object_id)] = {}
                    for sequence_id, pose_data in sequences.items():
                        pose_offset = Pose()
                        pose_offset.position.x = pose_data['position']['x']
                        pose_offset.position.y = pose_data['position']['y']
                        pose_offset.position.z = pose_data['position']['z']
                        pose_offset.orientation.x = pose_data['orientation']['x']
                        pose_offset.orientation.y = pose_data['orientation']['y']
                        pose_offset.orientation.z = pose_data['orientation']['z']
                        pose_offset.orientation.w = pose_data['orientation']['w']
                        self.offset_dict[int(object_id)][int(sequence_id)] = pose_offset

    def do_calc_end_effector_position(self, pose_object:Pose, grap_offset:Pose):
        # pose 를 계산 가능한 형태인 매트릭스 형태로 변환
        mat_pose_object = self.do_convert_pose_to_matrix(pose_object)
        mat_grap_offset = self.do_convert_pose_to_matrix(grap_offset)

        # 마커로 부터 오프셋 만큼의 좌표변환을 수행
        mat_rtn = np.dot(mat_pose_object, mat_grap_offset)
        pose_rtn = self.do_convert_matrix_to_pose(mat_rtn) 

        return pose_rtn
        ...

# offset 저장용 코드 
def main():
    object_id = 4
    print("something_01")
    rclpy.init()
    manipulation_00 = Manipulation()

    input()

    manipulation_00.set_world_frame("world")
    manipulation_00.set_camera_frame("cam")

    input()

    # 현재 마커와 자신 사이의 위치를 기록
    # 마커의 위치는 처음 한 번만 읽는다.
    # 이후의 정보는 로봇 tf 정보의 변화로 부터 offset을 계산한다.
    manipulation_00.set_pose_pivot_obejct(object_id)
    manipulation_00.do_publish_pose_debug(manipulation_00.pose_pivot_object, "world", 0)
    
    iter = 0
    while True:
        print("offset logging loop")
        print("press q to quit the loop, or press anyother to proceed the loop")
        print("loop iter : {}".format(iter))
        if input() == "q":# q를 눌렀을 경우에는 반복 종료 다른 키를 눌렀늘 경우에는 계속 반복
            break
        # 마커 인식 후 로봇 엔드이펙터의 위치를 조정할 여유
        manipulation_00.set_pose_end_effector("panda_link8")# 이름이 panda_link8인 엔드이펙터의 tf를 자세를 바꿀 때 마다 받아옴 
        pose_offset = manipulation_00.do_calc_pose_offset()

        manipulation_00.do_publish_pose_debug(manipulation_00.pose_end_effector, "world", 1)
        manipulation_00.do_publish_pose_debug(pose_offset, "world", 2)
        if pose_offset is not None:# 오프셋을 잘 계산한 경우
            manipulation_00.set_pose_offset(object_id, iter, pose_offset, "marker_pose.json")# 기존 저장경로에 offset 데이터 저장

        iter = iter + 1

    manipulation_00.load_offsets_from_json("marker_pose.json")

    # 오브젝트의 좌표를 받아옴.
    # pose_object = manipulation_00.get_abs_object_pose(object_id)
    pose_object = manipulation_00.pose_pivot_object
    if pose_object is not None:
        iter = 0
        while True:
            print("review loop")
            print("press q to quit the loop, or press anyother to proceed the loop")
            print("loop iter : {}".format(iter))
            if input() == "q":
                break

            pose_offset = manipulation_00.get_pose_offset(object_id, iter)
            pose_new_robot_hand = manipulation_00.do_calc_end_effector_position(pose_object, pose_offset)
            manipulation_00.do_publish_pose_debug(pose_object, "world", 0)
            manipulation_00.do_publish_pose_debug(pose_new_robot_hand, "world", 3)

            
            iter = iter + 1


if __name__ == '__main__':
    main()