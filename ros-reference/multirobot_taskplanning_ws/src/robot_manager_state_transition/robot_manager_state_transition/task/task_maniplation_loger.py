"""

확인해야할 상태의 요소
완료 여부
성공 여부
완료 상태와 성공상태는 구분할 것

"""

# ros2 기본 모듈
import rclpy
import rclpy.node
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros2 기본 인터페이스
from std_msgs.msg import Empty
from geometry_msgs.msg import Pose
from control_msgs.action import GripperCommand

# 사용자 정의 인터페이스
from robot_manager_interface.srv import RobotManager
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 파이썬 기본 모듈
import math
import json
import time
import enum

# 파이썬 외부 모듈

# 파이썬 사용자 정의 모듈
# 주요 타입 모듈
from robot_manager_state_transition.robot_entity.robot import Robot
from robot_manager_state_transition.process.process import Process
# Process 모듈
from robot_manager_state_transition.process.object_detector_process import ObjectDetector
from robot_manager_state_transition.process.moveit_client_process import MoveitClient
from robot_manager_state_transition.process.gripper_client_process import GripperClient
# 로봇 자세 표현 관리 모듈
from robot_manager_state_transition.module.pose_calc_module import PoseCalcModule

class ManipulationTask(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        self.robot = robot_arg
        self.node = node_arg

        self.module_pose_clac = PoseCalcModule(self.node)
        self.module_pose_clac.set_world_frame("world")
        
        self.process_instance_object_detector = ObjectDetector(self.node, self.robot)
        self.process_instance_moveit_clinet = MoveitClient(self.node, self.robot)
        self.process_instance_gripper_client = GripperClient(self.node, self.robot)
        
        # <사용자 정의 객체 선언>
        class Manipulation_task_sequence_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            request_task = enum.auto()
            wait = enum.auto()
            request_sub_process = enum.auto()
            
            working_sub_process = enum.auto()
            complete_sub_process = enum.auto()
            complete_task = enum.auto()
            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태

        self.process_state_enum = Manipulation_task_sequence_state_enum
        self.process_state = self.process_state_enum.error.value

        # Process 간 대기시간 관리 변수
        self.robot_setteling_time = 1.0# 로봇팔의 안정화 시간 1초
        self.flag_sub_precess_completed_time = None

        # 흐름 관리 변수
        self.obj_id_a:int = None
        self.obj_id_b:int = None
        self.action_id:int = None
        self.sequence_id:int = None

        self.request:RobotManager.Request = None
        self.flag_job_set:bool = False
        self.flag_job_completed:bool = False
        self.success:bool = False
        self.result = None

        self.sub_process_type:str = None 
        self.sub_process_instance:Process = None
        self.sub_process_flag_job_set:bool = False
        self.sub_process_flag_job_complete:bool = False
        self.sub_process_success = None
        self.sub_process_request = None


        # worker property
        self.robot_worker_property = self.robot.get_worker_property_instance()

        # 초기화 실행 문
        self.save_data_path_manipulation = "{}/manipulation_data.json".format(self.robot.get_manipulator_property_instance().get_data_dir_path())
        self.save_data_path_gripper = "{}/gripper_data.json".format(self.robot.get_manipulator_property_instance().get_data_dir_path())
        self.module_pose_clac.load_manipulation_data_from_json(filename=self.save_data_path_manipulation)

        if self.robot.get_detector_property_instance().get_is_enabled() == False:
            assert 0, "로봇에 디텍터 속성이 없거나 활성화 되지 않았습니다."
        if self.robot.get_manipulator_property_instance().get_is_enabled() == False:
            assert 0, "로봇에 메니퓰레이션 속성이 없거나 활성화 되지 않았습니다."
        if self.robot.get_gripper_property_instance().get_is_enabled() == False:
            assert 0, "로봇에 그리퍼 속성이 없거나 활성화 되지 않았습니다."

        # 초기화 완료 후에 process state 를 ready 로 설정
        self.process_state = self.process_state_enum.ready.value

    def get_gripper_info_from_json(self, id_number_arg, file_path:str='data/gripper_data.json'):
        id_number = str(id_number_arg)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if id_number in data:
                    print("<test01>")
                    return data[id_number]
                else:
                    print("<test02>")
                    return None
        except FileNotFoundError:
            print(f"File '{file_path}' not found.")
            return None
        except json.JSONDecodeError:
            print(f"Error decoding JSON from file '{file_path}'.")
            return None

    def get_sub_action_type(self, request_arg:RobotManager.Request, sequnce_id_arg:int):
        process_instance:Process = None

        obj_id_a = request_arg.a
        obj_id_b = request_arg.b
        action_id = request_arg.instruction
        sequnce_id = sequnce_id_arg

        manipulation_data:dict = self.module_pose_clac.get_manipulation_data(obj_id_a, obj_id_b, action_id, sequnce_id)
        self.sub_action_type = manipulation_data["sub_action"]

        return self.sub_action_type

    def get_process_instance(self) -> Process:
        process_instance:Process = None

        sub_action_type = self.get_sub_action_type(self.request, self.sequence_id)

        if sub_action_type == "move":
            process_instance = self.process_instance_moveit_clinet
        elif sub_action_type == "detect":
            process_instance = self.process_instance_object_detector
        elif sub_action_type == "gripper_open":
            process_instance = self.process_instance_gripper_client
        elif sub_action_type == "gripper_close":
            process_instance = self.process_instance_gripper_client
        elif sub_action_type == "gripper_hold":
            process_instance = self.process_instance_gripper_client
        elif sub_action_type == "termination":
            process_instance = None
        
        return process_instance

    def get_request(self):
        request_rtn = None

        manipulation_data:dict = self.module_pose_clac.get_manipulation_data(self.obj_id_a, self.obj_id_b, self.action_id, self.sequence_id)
        sub_action_type = manipulation_data["sub_action"]
        pose = manipulation_data["pose"]
        relativity = manipulation_data["is_relative"]

        if sub_action_type == "move":
            request_rtn = self.get_request_moveit(self.obj_id_a, pose, relativity)
        elif sub_action_type == "detect":
            request_rtn = self.get_request_detector()
        elif sub_action_type == "gripper_open":
            request_rtn = self.get_request_gripper(sub_action_type)
        elif sub_action_type == "gripper_close":
            request_rtn = self.get_request_gripper(sub_action_type)
        elif sub_action_type == "gripper_hold":
            request_rtn = self.get_request_gripper(sub_action_type, self.obj_id_a)
        elif sub_action_type == "terminate":
            request_rtn = None

        return request_rtn

    def get_request_moveit(self, target_obj_id:int, pose_arg:Pose, relativity_arg:bool) -> Pose:
        request_rtn = None
        if relativity_arg == True:
            object_pose = self.module_pose_clac.get_abs_object_pose(target_obj_id)
            if object_pose is not None:
                pose_offset = pose_arg
                request_rtn = self.module_pose_clac.do_calc_end_effector_position(object_pose, pose_offset)
            else:
                # 에러 발생
                print("object_pose is None")
                self.process_state = self.process_state_enum.error.value
        else:
            request_rtn = pose_arg
        return request_rtn

    def get_request_gripper(self, sub_action_type, object_id:int=None) -> GripperCommand:
        request_rtn= GripperCommand.Goal()
        if sub_action_type == "gripper_open":
            request_rtn.command.position = 0.04
            request_rtn.command.max_effort = 0.0
        elif sub_action_type == "gripper_close":
            request_rtn.command.position = 0.0
            request_rtn.command.max_effort = 0.0
        elif sub_action_type == "gripper_hold":
            if object_id is not None:
                data = self.get_gripper_info_from_json(object_id, self.save_data_path_gripper)
                request_rtn.command.position = data["data"]["position"]
                request_rtn.command.max_effort = data["data"]["max_effort"]
            else:
                ...# 에러 
                print("object_id is None")
                self.process_state = self.process_state_enum.error.value
        print("gripper request_rtn : {}".format(request_rtn))
        return request_rtn

    def get_request_detector(self):
        return Empty()

    def do_assign_request(self, request_arg:RobotManager.Request) -> bool:
        # job_accepted 
        self.flag_job_set = False
        self.flag_job_completed = False
        self.success = False
        self.result = None
        
        if self.process_state == self.process_state_enum.ready.value:
            if self.robot_worker_property.get_state() == self.robot_worker_property.job_state_enum.ready.value:
                self.request = request_arg
                self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.request.value)
                self.flag_job_set = True
        print("self.process_state {}".format(self.process_state))
        print("self.robot_worker_property.get_state() {}".format(self.robot_worker_property.get_state()))
        print("self.flag_job_set {}".format(self.flag_job_set))
        return self.flag_job_set

    def do_execute(self) -> None:
        # ready
        if self.process_state == self.process_state_enum.ready.value:
            ...
        # request_task
        elif self.process_state  == self.process_state_enum.request_task.value:
            # sub process가 시작하기 전에 반복하여 사용하게 될 정보를 미리 초기화 및 준비하는 단계로 활용
            self.obj_id_a:int = self.request.a
            self.obj_id_b:int = self.request.b
            self.action_id:int = self.request.instruction
            self.sequence_id:int = 0
        # wait
        elif self.process_state == self.process_state_enum.wait.value:
            ...
        # request_sub_process
        elif self.process_state == self.process_state_enum.request_sub_process.value:
            self.sub_process_instance = self.get_process_instance()# 맴버 변수를 통해 정보를 전달 받아 상황에 적절한 값을 가져옴
            self.sub_process_request = self.get_request()# 맴버 변수를 통해 정보를 전달 받아 상황에 적절한 값을 가져옴
            self.sub_process_flag_job_set = self.sub_process_instance.do_assign_request(self.sub_process_request)
            sub_action_type = self.get_sub_action_type(self.request, self.sequence_id)
            print("sub_process start : {}".format(sub_action_type))
            ...
        # working_sub_process
        elif self.process_state == self.process_state_enum.working_sub_process.value:
            self.sub_process_instance.do_execute()
            ...
        # complete_sub_process
        elif self.process_state == self.process_state_enum.complete_sub_process.value:
            # object detect sub_process의 종료 이후 에는 측정한 좌표값들을 저장
            sub_action_type = self.get_sub_action_type(self.request, self.sequence_id)
            print("sub_process end : {}".format(sub_action_type))
            if self.get_sub_action_type(self.request, self.sequence_id) == "detect":
                object_data_list:DetectObjects.Response = self.sub_process_instance.get_result()
                self.module_pose_clac.set_object_list(object_data_list)
            ...
        # complete_task
        elif self.process_state == self.process_state_enum.complete_task.value:
            ...
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            self.obj_id_a:int = self.request.a
            self.obj_id_b:int = self.request.b
            self.action_id:int = self.request.instruction
            self.sequence_id:int = 0

            self.sub_process_type:str = None 
            self.sub_process_instance:Process = None
            self.sub_process_flag_job_set:bool = False
            self.sub_process_flag_job_complete:bool = False
            self.sub_process_request = None
        # error
        elif self.process_state == self.process_state_enum.error.value:
            # self.process_state_move_control = self.process_state_enum.error.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = False
                self.result = None
        # halt
        elif self.process_state == self.process_state_enum.halt.value:
            ...
    
    def do_update(self) -> None:
        self.do_log_state_trasition()
        # ready
        if self.process_state == self.process_state_enum.ready.value:
            if self.flag_job_set == True:
                self.process_state = self.process_state_enum.request_task.value
        # request_task
        elif self.process_state == self.process_state_enum.request_task.value:
            self.process_state = self.process_state_enum.request_sub_process.value
            self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.working.value)
        # wait
        elif self.process_state == self.process_state_enum.wait.value:
            if time.time_ns() - self.flag_sub_precess_completed_time > self.robot_setteling_time * 1e+9:# 초단위 시간 1을 ns 단위로 변환함
                self.process_state = self.process_state_enum.request_sub_process.value
        # request_sub_process
        elif self.process_state == self.process_state_enum.request_sub_process.value:
            if self.sub_process_flag_job_set == True:
                self.process_state = self.process_state_enum.working_sub_process.value
            else:
                self.process_state = self.process_state_enum.error.value
        # working_sub_process
        elif self.process_state == self.process_state_enum.working_sub_process.value:
            self.sub_process_instance.do_update()
            if self.sub_process_instance.do_check_completion() == True:
                self.sub_process_instance.do_print_log()
                success = self.sub_process_instance.get_success()
                # print("task 레벨에서 sub process success {}".format(success))
                if success == True:
                    self.process_state = self.process_state_enum.complete_sub_process.value# 서브 프로세스의 종료가 확인되면 complete_sub_process 상태로 이동
                    # print("{} : complete_sub_process".format(self.get_sub_action_type(self.request, self.sequence_id)))
                else:
                    self.process_state = self.process_state_enum.error.value
                    # print("{} : error".format(self.get_sub_action_type(self.request, self.sequence_id)))
            ...
        # complete_sub_process
        elif self.process_state == self.process_state_enum.complete_sub_process.value:
            # 서브 프로세스가 종료되면 sequence_id를 1 씩 증가됨
            self.sequence_id = self.sequence_id + 1
            # 다음 서브프로세스를 실행할지, task를 종료할지 결정
            flag_termination = self.do_check_sequence_termination()
            # 시퀀스의 종료가 확인되면 task를 종료하는 단계로 넘어간다.
            if flag_termination == True:
                self.process_state = self.process_state_enum.complete_task.value
            else:
                if self.get_sub_action_type(self.request, self.sequence_id) == "detect":
                    self.process_state = self.process_state_enum.wait.value
                    self.flag_sub_precess_completed_time = time.time_ns()
                else:
                    self.process_state = self.process_state_enum.request_sub_process.value
        # complete_task
        elif self.process_state == self.process_state_enum.complete_task.value:
            self.process_state = self.process_state_enum.reset.value
            self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.complete.value)
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
            ...
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            print("reset")
            # 각종 변수 및 상태를 초기화 한 후 ready 상태로 전이
            self.process_state = self.process_state_enum.ready.value
            self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.ready.value)# 로봇의 상태를 ready으로 변경
        # error
        elif self.process_state == self.process_state_enum.error.value:
            self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.error.value)
            # self.process_state_move_control = self.process_state_enum.error.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = False
                self.result = None
        # halt
        elif self.process_state == self.process_state_enum.halt.value:
            self.robot_worker_property.set_state(self.robot_worker_property.job_state_enum.halt.value)
            ...

    def do_check_sequence_termination(self):
        termination_rtn:bool = False
        
        sub_action_type = self.get_sub_action_type(self.request, self.sequence_id)
        if sub_action_type == "terminate":
            termination_rtn = True
        return termination_rtn
    
    def do_check_completion(self):
        complete_bool_rtn = False
        if self.process_state == self.process_state_enum.ready.value or self.process_state == self.process_state_enum.error.value:
            # 모든 동작이 종료 및 정리되어서 ready 상태로 돌아 왔는지 확인
            # 혹은 error로 인하여 작업이 중단 되었는지 여부를 확인
            if self.flag_job_set == True:# 같은 ready 상태더라도 작업이 걸려있는 상태인지 확인
                if self.flag_job_completed == True:# 작업이 완료되었는지 여부 확인
                    complete_bool_rtn = True
                    self.flag_job_set = False
                    self.flag_job_completed = False
                    if self.process_state == self.process_state_enum.error.value:
                        self.process_state = self.process_state_enum.halt.value
        if self.process_state == self.process_state_enum.halt.value:
            complete_bool_rtn = True
            self.success = False
            self.result = None
        return complete_bool_rtn

    def do_reset_state(self):
        self.process_state == self.process_state_enum.ready.value
# <test 코드>--------------------------------------------------------------------------

def get_gripper_info_from_json(id_number_arg, file_path_arg:str='data/gripper.json'):
    id_number = str(id_number_arg)
    try:
        with open(file_path_arg, 'r') as f:
            data = json.load(f)
            if id_number in data:
                print("<test01>")
                return data[id_number]["data"]
            else:
                print("<test02>")
                return None
    except FileNotFoundError:
        print(f"File '{file_path_arg}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON from file '{file_path_arg}'.")
        return None

def main():
    # manipulation_task_instance = ManipulationTask()
    # data = manipulation_task_instance.get_gripper_info_from_json()
    data = get_gripper_info_from_json(1)
    print(type(data))
    print(data)
    print(data["position"])
    print(data["max_effort"])

if __name__ == "__main__":
    main()