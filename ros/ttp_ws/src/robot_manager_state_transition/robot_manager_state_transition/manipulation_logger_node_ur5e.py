# ros2 기본 요소 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

# ros2 사용자 정의 인터페이스 모듈
from robot_manager_interface.srv import TaskLogging
from geometry_msgs.msg import Pose
from std_msgs.msg import Empty
from control_msgs.action import GripperCommand
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 기본 파이썬 모듈
import enum
import os
from ament_index_python.packages import get_package_share_directory

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.robot_entity.robot_mobile_manipulator import Robot_mobile_manipulator
from robot_manager_state_transition.robot_entity.worker_properties import Worker_properties

from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.process.moveit_client_process import MoveitClient
from robot_manager_state_transition.process.object_detector_process import ObjectDetector 
from robot_manager_state_transition.process.gripper_client_process import GripperClient 

from robot_manager_state_transition.module.pose_calc_module import PoseCalcModule


class ManipulationDataLogging(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(TaskLogging, 'task_logging', self.do_execute_job, callback_group=MutuallyExclusiveCallbackGroup())
        # self.parameter_end_effector_frame = self.declare_parameter("end_effector_frame")

        # 로봇 객체 초기화
        self.robot = Robot_mobile_manipulator()
        self.robot.set_name("husky")
        self.robot.set_type("mobile_manipulator")
        self.robot.set_enable_robot()

        self.robot_worker_properties = self.robot.get_worker_property_instance()
        self.job_state_enum = self.robot_worker_properties.job_state_enum
        self.robot_worker_properties.set_state(self.job_state_enum.ready.value) 

        self.mobilebase_properties = self.robot.get_mobilebase_property_instance()
        self.mobilebase_state_enum = self.mobilebase_properties.mobilebase_state_enum
        self.mobilebase_properties.set_state(self.mobilebase_state_enum.safe_zone.value)

        self.manipulatior_properties = self.robot.get_manipulator_property_instance()
        self.manipulator_state_enum = self.manipulatior_properties.manipulator_state_enum
        self.manipulatior_properties.set_state(self.manipulator_state_enum.ready.value) 
        
        # ament_index를 사용하여 워크스페이스 루트의 data_ur 경로 추적
        # install/pkg/share/pkg -> 4단계 상위 -> workspace root
        package_share_directory = get_package_share_directory('robot_manager_state_transition')
        workspace_path = os.path.abspath(os.path.join(package_share_directory, "../../../.."))
        data_dir_path = os.path.join(workspace_path, "data_ur")
        
        self.manipulatior_properties.set_data_dir_path(data_dir_path)

        self.gripper_properties = self.robot.get_gripper_property_instance()
        self.gripper_state_enum = self.gripper_properties.gripper_state_enum
        self.gripper_properties.set_state(self.gripper_state_enum.ready.value)
        # 그리퍼 타입 설정
        self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.robotiq.value)
        # self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.panda.value)

        self.detector_properties = self.robot.get_detector_property_instance()
        self.detector_state_enum = self.detector_properties.detector_state_enum
        self.detector_properties.set_state(self.detector_state_enum.ready.value)


        # worker property
        self.robot_manager_worker_properties = Worker_properties()
        # 초기화 실행 문
        self.robot_manager_worker_properties.set_state(self.robot_manager_worker_properties.job_state_enum.ready.value)

        # 좌표 계산 모듈

        self.module_pose_clac = PoseCalcModule(self)
        self.module_pose_clac.set_world_frame("world")
        self.module_pose_clac.set_camera_frame("cam")
        self.module_pose_clac.set_end_effector_frame("tool0")# ur5e 로봇의 경우
        # self.module_pose_clac.set_end_effector_frame("panda_link8")# franka panda robot 의 경우
        
        # 개별 프로세스 객체 초기화
        # self.moveit_client_process = MoveitClient(self, self.robot)# find 하나만 먼저 초기화
        self.object_detector_process = ObjectDetector(self, self.robot)# find 하나만 먼저 초기화
        # self.gripper_client_process = GripperClient(self, self.robot)
        # 사용자 변수 정의
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_success = False
        self.job_result = None

        self.process_entity = None

        self.sequence_id = 0
        self.flag_pivot_set = False

        self.object_id_a_old:int = None
        self.object_id_b_old:int = None
        self.action_id_old:int = None

        self.save_data_path_manipulation = "{}/manipulation_data.json".format(self.manipulatior_properties.get_data_dir_path())
        self.save_data_path_gripper = "{}/gripper_data.json".format(self.manipulatior_properties.get_data_dir_path())
        print("robot is ready")

    def do_calc_pose_offset(self, request_arg:TaskLogging.Request, object_list_arg:DetectObjects.Response):
        # 파라미터로 부터 엔드이펙터 프레임에 대한 정보를 전달받음
        # end_effector_frame = self.parameter_end_effector_frame.get_parameter_value().string_value

        self.module_pose_clac.set_pose_end_effector()
        pose_offset = self.module_pose_clac.do_calc_offset_data()
        return pose_offset

    def do_save_task_logging(self, request_arg:TaskLogging.Request, sub_action_arg:str, pose_arg:Pose = Pose(), relativity_arg:bool=False) -> Pose:
        # 상대 좌표로 저장하는 경우
        print(pose_arg)
        self.module_pose_clac.set_manipulation_data(request_arg.object_id_a, request_arg.object_id_b, request_arg.instruction, self.sequence_id, request_arg.sub_action, pose_arg, relativity_arg)
        self.module_pose_clac.save_manipulation_data_to_json(self.save_data_path_manipulation)
        self.module_pose_clac.load_manipulation_data_from_json(self.save_data_path_manipulation)
        manipulation_data = self.module_pose_clac.get_manipulation_data(request_arg.object_id_a, request_arg.object_id_b, request_arg.instruction, self.sequence_id)
        pose_offset_from_data = manipulation_data["pose"]
        return pose_offset_from_data
        ...

    def do_execute_job(self, request:TaskLogging.Request, response:TaskLogging.Response):
        print("do_execute_job")
        debug_pose_object:Pose = None
        debug_pose_offset_from_data:Pose = None
        debug_pose_end_effector:Pose = None

        object_id_a = request.object_id_a
        object_id_b = request.object_id_b
        action_id = request.instruction
        sub_action = request.sub_action
        relativity = request.relativity
        
        check_change_object_id_a = self.object_id_a_old != object_id_a
        check_change_object_id_b =  self.object_id_b_old != object_id_b
        check_change_action_id = self.action_id_old != action_id

        if check_change_object_id_a or check_change_object_id_a or check_change_action_id:
            self.object_id_a_old = object_id_a
            self.object_id_b_old = object_id_b
            self.action_id_old = action_id
            self.sequence_id = 0
            self.flag_pivot_set = False
        # 응답 기본 값 설정
        response.success = False
        
        if request.sequence_id >= 0:# 전달된 sequence_id의 값이 0 보다 크거나 같으면 해당 sequence_id 로 이동 
            self.sequence_id = request.sequence_id
        if sub_action == "move":
            if relativity == True:
            # 오브젝트 기준의 상대 좌표를 저장
                if self.flag_pivot_set is not None:# 이전 단게에서 pivot 좌표가 이미 설정되어 있는 경우만 수행 가능
                    self.module_pose_clac.set_pose_end_effector()
                    pose_offset_data = self.module_pose_clac.do_calc_offset_data()
                    debug_pose_offset_from_data = self.do_save_task_logging(request, sub_action, pose_offset_data, True)# 데이터 저장1
                    debug_pose_object = self.module_pose_clac.get_pose_pivot_object()# object_id_a 가 아닌 object_id_b 를 적용 
                    debug_pose_end_effector = self.module_pose_clac.do_calc_end_effector_position(debug_pose_object, debug_pose_offset_from_data)
                    response.success = True
                else:
                    print("detector 를 통해 수집한 위치 데이터가 없습니다. 상대좌표로 위치를 기록할 수 없습니다.")
            else:
            # 로봇 기준의 절대 좌표를 저장
                pose_data = self.module_pose_clac.get_pose_end_effector()
                if pose_data is not None:
                    debug_pose_end_effector = self.do_save_task_logging(request, sub_action, pose_data, False)# 데이터 저장3
                    response.success = True

        elif sub_action == "detect":
            # 오브젝트들의 위치 데이터를 수집 및 기준 좌표 설정
            # self.process_entity = self.get_process_entity(request)
            self.process_entity = self.object_detector_process# 데이터 로깅 중에 활용하는 프로세스 객체는 object_detect_process 
            self.process_entity.do_reset_log()
            self.do_assign_task(self.process_entity, request)
            while True:
                self.do_execute_task(self.process_entity)
                self.do_update_job_state(self.process_entity)
                if self.do_check_completion() == True:
                    if self.process_entity.get_success() == True:
                        self.job_result:DetectObjects.Response = self.process_entity.get_result()
                        self.module_pose_clac.set_object_list(self.job_result)
                        # 기준 좌표 설정
                        if action_id in [4, 5]:#putback, putin 처럼 인식해야하는 오브젝트(마커)의 위치 object_b 가 기준이 되는 경우
                            self.flag_pivot_set = self.module_pose_clac.set_pose_pivot_obejct(request.object_id_b)
                            if self.flag_pivot_set == True:
                                debug_pose_object = self.module_pose_clac.get_abs_object_pose(request.object_id_b)
                                response.success = True
                        else:
                            self.flag_pivot_set = self.module_pose_clac.set_pose_pivot_obejct(request.object_id_a)
                            if self.flag_pivot_set == True:
                                debug_pose_object = self.module_pose_clac.get_abs_object_pose(request.object_id_a)
                                response.success = True 
                    self.process_entity.do_print_log()
                    break
            debug_pose_end_effector = self.do_save_task_logging(request, sub_action)# 데이터 저장4
        elif sub_action in ["gripper_open", "gripper_close", "gripper_hold"]:
            # 그리퍼 동작에 대해서는 좌표 정보를 저장하지 않고 sub_action 값만을 확인하여 데이터를 저장한다. 
            self.do_save_task_logging(request, sub_action)
            response.success = True
        elif sub_action == "terminate":
            # 종료 조건은 좌표 정보를 저장하지 않고 sub_action 값만을 확인하여 데이터를 저장한다. 
            self.do_save_task_logging(request, "terminate")
            response.success = True
        iter = 0
        for pose in [debug_pose_object, debug_pose_offset_from_data, debug_pose_end_effector]:
            if pose is not None:
                self.module_pose_clac.do_publish_pose_debug(pose, iter)# 오프젝트의 위치
            iter += 1
        
        print("sequence_id : {}".format(self.sequence_id))
        if response.success == True:
            self.sequence_id += 1
        
        return response

    def get_process_entity(self, request:TaskLogging.Request) -> Process:
        process_entity_rtn = None
        if request.instruction == 1:
            process_entity_rtn = self.moveit_client_process
        elif request.instruction == 2:
            process_entity_rtn = self.object_detector_process
        elif request.instruction == 3:
            process_entity_rtn = self.gripper_client_process
        return process_entity_rtn

    def do_assign_task(self, process_entity:Process, request_arg:TaskLogging.Request):
        print("task_assigning")
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_success = False

        request = Empty()

        job_state = self.robot_manager_worker_properties.get_state()
        print("task_assigning")
        print("job_state : {}".format(job_state))
        if job_state == self.job_state_enum.ready.value:
            print("requset_task")
            self.flag_job_set = process_entity.do_assign_request(request)
            self.robot_manager_worker_properties.set_state(self.job_state_enum.request.value)# task가 할당되어 작업상태로 상태 변화
            print("self.flag_job_set : {}".format(self.flag_job_set))
            if self.flag_job_set == True:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.request.value)
            else:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.error.value)
        print(self.robot_manager_worker_properties.get_state())

        return self.flag_job_set

    def do_execute_task(self, process_entity:Process):
        job_state = self.robot_manager_worker_properties.get_state()
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            ...
        elif job_state == self.job_state_enum.working.value:
            ...
            process_entity.do_execute()
        elif job_state == self.job_state_enum.complete.value:
            self.flag_job_complete = True
            self.job_success = True
            ...
        elif job_state == self.job_state_enum.error.value:
            self.flag_job_complete = True
            self.job_success = False
            ...

    def do_update_job_state(self, process_entity:Process):
        job_state = self.robot_manager_worker_properties.get_state()
        
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            if self.flag_job_set == True:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.working.value)
        elif job_state == self.job_state_enum.working.value:
            process_entity.do_update()
            if process_entity.do_check_completion() == True:
                print("process_entity.get_success() {}".format(process_entity.get_success()))
                if process_entity.get_success() == True:
                    self.robot_manager_worker_properties.set_state(self.job_state_enum.complete.value)
                else:
                    self.robot_manager_worker_properties.set_state(self.job_state_enum.error.value)
        elif job_state == self.job_state_enum.complete.value:
            self.robot_manager_worker_properties.set_state(self.job_state_enum.ready.value)
        elif job_state == self.job_state_enum.error.value:
            job_state = self.job_state_enum.halt.value
            print("robot_mananger error 발생")
            # assert 0, "error 발생"
        elif job_state == self.job_state_enum.halt.value:
            ...
            print("robot_mananger Halt 상태")
        ...
    
    def do_check_completion(self):
        job_complete_rtn = False
        job_state = self.robot.get_worker_property_instance().get_state()
        
        if job_state == self.job_state_enum.ready.value or job_state == self.job_state_enum.error.value:
            if self.flag_job_set == True:
                if self.flag_job_complete == True:
                    job_complete_rtn = True
                    self.flag_job_set = False
                    self.flag_job_complete = False
                    if job_state == self.job_state_enum.error.value:
                        self.robot.get_worker_property_instance().set_state(self.job_state_enum.halt.value)
        if job_state == self.job_state_enum.halt.value:
            job_complete_rtn = True
            self.job_success = False
        return job_complete_rtn

    def get_result(self):
        return self.job_success

def main():
    rclpy.init()
    node = ManipulationDataLogging()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
        node.process_entity.do_print_log()
    executor.remove_node(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()